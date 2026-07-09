from django.core.exceptions import ValidationError
from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta

CONFIRM_WINDOW_MINUTES = 60
TURN_LOCK_MINUTES = 15
SESSION_MAX_DURATION_MINUTES = 120


class Circle(models.Model):

    class Status(models.TextChoices):
        ACTIVE = 'active', 'نشطة'
        PAUSED = 'paused', 'متوقفة'
        INACTIVE = 'inactive', 'منتهية'

    class Gender(models.TextChoices):
        MALE = 'male', 'ذكر'
        FEMALE = 'female', 'أنثى'

    class CircleType(models.TextChoices):
        AHKAM = 'ahkam', 'أحكام'
        HIFD = 'hifd', 'حفظ'
        MURAJAA = 'murajaa', 'مراجعة'

    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='teaching_circles'
    )
    students = models.ManyToManyField(
        settings.AUTH_USER_MODEL, through='CircleEnrollment',
        related_name='enrolled_circles'
    )
    name = models.CharField(max_length=255)
    description = models.TextField("الوصف", blank=True)
    # HAF-16: circle-level surah_range removed — each student tracks their own
    # position via MemorizationRecord; a shared free-text range was misleading.
    location = models.CharField(max_length=255, blank=True)
    gender = models.CharField(max_length=10, choices=Gender.choices, default=Gender.MALE)
    circle_type = models.CharField(
        "نوع الحلقة", max_length=20, choices=CircleType.choices, default=CircleType.HIFD,
    )
    max_students = models.PositiveIntegerField(default=30)
    schedule = models.CharField(max_length=255, blank=True)
    schedule_days = models.JSONField("أيام الحلقة", default=list, blank=True)
    schedule_time = models.TimeField("وقت الحلقة", null=True, blank=True)
    batch = models.ForeignKey(
        "accounts.Batch", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="circles", verbose_name="الدفعة",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_active(self):
        return self.status == self.Status.ACTIVE

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class CircleEnrollment(models.Model):

    class Status(models.TextChoices):
        PENDING = 'pending', 'قيد الانتظار'
        ACTIVE = 'active', 'نشط'
        INACTIVE = 'inactive', 'منتهي'
        DROPPED = 'dropped', 'منسحب'

    circle = models.ForeignKey(Circle, on_delete=models.CASCADE, related_name='enrollments')
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='enrollments'
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    enrolled_at = models.DateTimeField(auto_now_add=True)
    left_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ المغادرة")
    current_surah = models.ForeignKey(
        'references.Surah', on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="السورة الحالية"
    )

    class Meta:
        unique_together = ('circle', 'student')
        indexes = [
            # L12: dashboards and reports filter enrollments by
            # (student, status) and (circle, status) on nearly every page.
            models.Index(fields=["student", "status"]),
            models.Index(fields=["circle", "status"]),
        ]

    def __str__(self):
        return f"{self.student.full_name_ar} ← {self.circle.name}"

    # ------------------------------------------------------------------
    # Behavior methods
    # ------------------------------------------------------------------

    @staticmethod
    def _check_batch_match(student, circle):
        """Students may only enroll in circles of their own دفعة. Either side
        being unassigned (NULL) passes — legacy data has no batch."""
        if (
            circle.batch_id and student.batch_id
            and circle.batch_id != student.batch_id
        ):
            raise ValidationError("الطالب والحلقة في دفعتين مختلفتين")

    def clean(self):
        self._check_batch_match(self.student, self.circle)

    @classmethod
    def enroll(cls, student, circle):
        """Create a new enrollment. If one exists (e.g. dropped), reactivates
        it instead of creating a duplicate."""
        cls._check_batch_match(student, circle)
        existing = cls.objects.filter(student=student, circle=circle).first()
        if existing:
            if existing.status == cls.Status.ACTIVE:
                raise ValidationError("الطالب مسجل بالفعل في هذه الحلقة")
            existing.status = cls.Status.ACTIVE
            existing.left_at = None
            existing.save(update_fields=["status", "left_at"])
            return existing
        return cls.objects.create(student=student, circle=circle)

    def activate(self):
        if self.status != self.Status.PENDING:
            raise ValidationError("يمكن تفعيل التسجيلات قيد الانتظار فقط")
        self.status = self.Status.ACTIVE
        self.left_at = None
        self.save(update_fields=["status", "left_at"])

    def drop(self):
        if self.status in (self.Status.DROPPED, self.Status.INACTIVE):
            raise ValidationError("التسجيل منتهٍ أو منسحب بالفعل")
        self.status = self.Status.DROPPED
        self.left_at = timezone.now()
        self.save(update_fields=["status", "left_at"])

    def mark_inactive(self):
        if self.status != self.Status.ACTIVE:
            raise ValidationError("يمكن إنهاء التسجيلات النشطة فقط")
        self.status = self.Status.INACTIVE
        self.left_at = timezone.now()
        self.save(update_fields=["status", "left_at"])

    def refresh_current_surah(self):
        """Recompute the denormalized `current_surah` from the student's
        frontier MemorizationRecord (HAF-08). The column used to be set by
        hand and drifted from real progress; it is now a cache kept in sync
        whenever memorization advances. Readers/reports keep using the column."""
        from apps.memorization.models import MemorizationRecord
        from apps.references.models import Ayah

        rec = (
            MemorizationRecord.objects
            .filter(student_id=self.student_id)
            .exclude(status=MemorizationRecord.Status.NOT_MEMORIZED)
            .order_by("-rub__number")
            .first()
        )
        if rec is None:
            return
        surah_id = (
            Ayah.objects.filter(rub_id=rec.rub_id)
            .order_by("-surah_id", "-number_in_surah")
            .values_list("surah_id", flat=True)
            .first()
        )
        if surah_id and self.current_surah_id != surah_id:
            self.current_surah_id = surah_id
            self.save(update_fields=["current_surah"])


class SessionStudentNote(models.Model):
    session = models.ForeignKey("Session", on_delete=models.CASCADE, related_name="student_notes")
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="session_notes",
    )
    note = models.TextField("الملاحظة")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "ملاحظة طالب في حصة"
        verbose_name_plural = "ملاحظات الطلاب في الحصص"
        unique_together = ("session", "student")

    def __str__(self):
        return f"{self.student.full_name_ar} ← {self.session}"


class Session(models.Model):

    class Status(models.TextChoices):
        DRAFT = "draft", "مسودة"
        SCHEDULED = "scheduled", "مجدولة"
        CONFIRMATION_OPEN = "confirmation_open", "فتح التأكيد"
        TURN_TAKING_OPEN = "turn_taking_open", "فتح الأدوار"
        LIVE = "live", "جارية"
        ENDED = "ended", "منتهية"

    class Type(models.TextChoices):
        IN_PERSON = "in_person", "حضوري"
        ONLINE = "online", "عن بُعد"

    class Platform(models.TextChoices):
        ZOOM = "zoom", "Zoom"
        GOOGLE_MEET = "google_meet", "Google Meet"
        TEAMS = "teams", "Microsoft Teams"
        WHATSAPP = "whatsapp", "WhatsApp"
        TELEGRAM = "telegram", "Telegram"
        OTHER = "other", "أخرى"

    class MeetingSource(models.TextChoices):
        # HAF-09: default online sessions to the teacher's permanent, JWT-secured
        # classroom room instead of a link re-pasted every session.
        CLASSROOM = "classroom", "قاعة المعلم الدائمة"
        EXTERNAL = "external", "رابط خارجي"

    circle = models.ForeignKey(Circle, on_delete=models.CASCADE, related_name='sessions')
    session_date = models.DateField()
    session_time = models.TimeField("وقت الحصة", null=True, blank=True)
    start_time = models.DateTimeField("وقت البدء", null=True, blank=True)
    status = models.CharField(
        max_length=30, choices=Status.choices, default=Status.DRAFT,
        verbose_name="حالة الحصة",
    )
    location = models.CharField("مكان الحصة", max_length=255, blank=True)
    session_type = models.CharField(
        max_length=20, choices=Type.choices, default=Type.IN_PERSON,
        verbose_name="نوع الحصة",
    )
    meeting_source = models.CharField(
        max_length=20, choices=MeetingSource.choices, default=MeetingSource.CLASSROOM,
        verbose_name="مصدر رابط الاجتماع",
    )
    meeting_url = models.URLField("رابط الاجتماع", max_length=500, blank=True)
    meeting_platform = models.CharField(
        max_length=20, choices=Platform.choices, blank=True,
        verbose_name="منصة الاجتماع",
    )
    meeting_id = models.CharField("معرف الاجتماع", max_length=100, blank=True)
    meeting_password = models.CharField("كلمة مرور الاجتماع", max_length=100, blank=True)
    recording_url = models.URLField("رابط التسجيل", max_length=500, blank=True)
    duration_minutes = models.PositiveIntegerField("المدة (دقائق)", null=True, blank=True)
    notes = models.TextField("ملاحظات", blank=True)
    turns_closed = models.BooleanField("إغلاق التسجيل في الأدوار", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('circle', 'session_date')
        verbose_name = "حصة"
        verbose_name_plural = "الحصص"
        indexes = [
            # HAF-24: dashboards filter a circle's sessions by status.
            models.Index(fields=["circle", "status"]),
            # L13: upcoming/past session lists query by date range.
            models.Index(fields=["session_date"]),
        ]

    def __str__(self):
        label = f"{self.circle.name} — {self.session_date}"
        if self.session_time:
            label += f" {self.session_time.strftime('%H:%M')}"
        return label

    @property
    def is_online(self):
        return self.session_type == self.Type.ONLINE

    def effective_meeting_url(self):
        """The link students actually join (HAF-09). Classroom-source online
        sessions resolve to the circle teacher's permanent room; external
        sessions use the manually entered URL. In-person sessions have none."""
        if not self.is_online:
            return ""
        if self.meeting_source == self.MeetingSource.EXTERNAL:
            return self.meeting_url
        teacher = self.circle.teacher
        if teacher is None:
            return self.meeting_url
        from django.urls import reverse
        from apps.classrooms.models import TeacherRoom
        room = TeacherRoom.objects.filter(teacher=teacher).only("slug").first()
        if room:
            return reverse("classrooms:join", kwargs={"slug": room.slug})
        return self.meeting_url

    @property
    def meeting_platform_display(self):
        return dict(self.Platform.choices).get(self.meeting_platform, self.meeting_platform)

    @property
    def is_unlocked(self):
        if self.turns_closed:
            return False
        if self.session_date and self.session_date >= timezone.localdate():
            return True
        return False


class SessionRescheduleRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "قيد الانتظار"
        APPROVED = "approved", "مقبول"
        REJECTED = "rejected", "مرفوض"

    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name="reschedule_requests")
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reschedule_requests"
    )
    proposed_date = models.DateField("التاريخ المقترح")
    proposed_time = models.TimeField("الوقت المقترح", null=True, blank=True)
    reason = models.TextField("سبب التعديل", blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reviewed_reschedules",
    )
    rejection_reason = models.TextField("سبب الرفض", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "طلب تعديل موعد حصة"
        verbose_name_plural = "طلبات تعديل موعد الحصص"
        ordering = ["-created_at"]

    def __str__(self):
        return f"تعديل {self.session} ← {self.proposed_date}"

    def validate_relationships(self):
        """Rule 2 integrity: a *student* requester must be actively enrolled
        in the session's circle. Staff requesters (teacher/supervisor/admin)
        pass — substitutes and admins legitimately reschedule sessions of
        circles they don't own."""
        from django.core.exceptions import ValidationError

        requester = self.requested_by
        if requester.role != "student":
            return
        if not CircleEnrollment.objects.filter(
            circle=self.session.circle,
            student=requester,
            status=CircleEnrollment.Status.ACTIVE,
        ).exists():
            raise ValidationError(
                "لا يمكن إنشاء الطلب: الطالب غير مسجل تسجيلاً نشطاً في حلقة هذه الحصة"
            )

    def clean(self):
        super().clean()
        if self.pk is None:
            self.validate_relationships()

    # ------------------------------------------------------------------
    # Section A — status transitions live on the model. Approving a
    # reschedule also applies the proposed date/time to the session;
    # that side-effect is part of the transition, not view code.
    # ------------------------------------------------------------------

    def can_be_responded_by(self, user) -> bool:
        from apps.accounts.models import User as AccUser
        if user.role in (AccUser.Role.MAIN_ADMIN, AccUser.Role.SUB_ADMIN):
            return True
        return user.role == AccUser.Role.TEACHER and self.session.circle.teacher_id == user.id

    def _check_respondable(self, by):
        from django.core.exceptions import ValidationError
        if self.status != self.Status.PENDING:
            raise ValidationError("تمت معالجة الطلب مسبقاً")
        if not self.can_be_responded_by(by):
            raise ValidationError("لا تملك صلاحية الرد على هذا الطلب")

    def approve(self, by):
        self._check_respondable(by)
        self.status = self.Status.APPROVED
        self.reviewed_by = by
        self.session.session_date = self.proposed_date
        update_fields = ["session_date"]
        if self.proposed_time:
            self.session.session_time = self.proposed_time
            update_fields.append("session_time")
        self.session.save(update_fields=update_fields)
        self.save(update_fields=["status", "reviewed_by", "updated_at"])
        return self

    def reject(self, by, reason=""):
        self._check_respondable(by)
        self.status = self.Status.REJECTED
        self.reviewed_by = by
        self.rejection_reason = reason or ""
        self.save(update_fields=["status", "reviewed_by", "rejection_reason", "updated_at"])
        return self


class SessionTurn(models.Model):
    session = models.ForeignKey(
        Session, on_delete=models.CASCADE, related_name="turns"
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="session_turns",
    )
    turn_number = models.PositiveIntegerField("رقم الدور")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("session", "turn_number")
        ordering = ["turn_number"]
        verbose_name = "دور تسميع"
        verbose_name_plural = "أدوار التسميع"

    def __str__(self):
        return f"{self.student.full_name_ar} — {self.session} (#{self.turn_number})"


class SessionLessonToggle(models.Model):
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name="lesson_toggles")
    surah = models.ForeignKey(
        "references.Surah", on_delete=models.CASCADE, related_name="lesson_toggles"
    )
    ayah_from = models.IntegerField("من الآية", null=True, blank=True)
    ayah_to = models.IntegerField("إلى الآية", null=True, blank=True)
    is_active = models.BooleanField(default=True, verbose_name="مفعل")
    toggled_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "تبديل درس"
        verbose_name_plural = "تبديلات الدروس"
        unique_together = ("session", "surah")

    def __str__(self):
        return f"{self.surah.name_ar} {'مفعل' if self.is_active else 'معطل'} ({self.session})"

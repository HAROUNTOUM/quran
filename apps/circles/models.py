from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta


class Circle(models.Model):

    class Status(models.TextChoices):
        ACTIVE = 'active', 'نشطة'
        PAUSED = 'paused', 'متوقفة'
        INACTIVE = 'inactive', 'منتهية'

    class Gender(models.TextChoices):
        MALE = 'male', 'ذكر'
        FEMALE = 'female', 'أنثى'

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
    surah_range = models.CharField("نطاق السور", max_length=255, blank=True)
    location = models.CharField(max_length=255, blank=True)
    gender = models.CharField(max_length=10, choices=Gender.choices, default=Gender.MALE)
    max_students = models.PositiveIntegerField(default=30)
    schedule = models.CharField(max_length=255, blank=True)
    schedule_days = models.JSONField("أيام الحلقة", default=list, blank=True)
    schedule_time = models.TimeField("وقت الحلقة", null=True, blank=True)
    batch_number = models.PositiveIntegerField("رقم الدفعة", null=True, blank=True)
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

    def __str__(self):
        return f"{self.student.full_name_ar} ← {self.circle.name}"


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

    circle = models.ForeignKey(Circle, on_delete=models.CASCADE, related_name='sessions')
    session_date = models.DateField()
    session_time = models.TimeField("وقت الحصة", null=True, blank=True)
    location = models.CharField("مكان الحصة", max_length=255, blank=True)
    session_type = models.CharField(
        max_length=20, choices=Type.choices, default=Type.IN_PERSON,
        verbose_name="نوع الحصة",
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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('circle', 'session_date')
        verbose_name = "حصة"
        verbose_name_plural = "الحصص"

    def __str__(self):
        label = f"{self.circle.name} — {self.session_date}"
        if self.session_time:
            label += f" {self.session_time.strftime('%H:%M')}"
        return label

    @property
    def is_online(self):
        return self.session_type == self.Type.ONLINE

    @property
    def meeting_platform_display(self):
        return dict(self.Platform.choices).get(self.meeting_platform, self.meeting_platform)

    @property
    def is_unlocked(self):
        if not self.session_date:
            return False
        start_time = self.session_time or self.circle.schedule_time or timezone.datetime.min.time()
        session_start = timezone.datetime.combine(
            self.session_date, start_time
        ).replace(tzinfo=timezone.get_current_timezone())
        now = timezone.now()
        delta = session_start - now
        session_duration = timedelta(minutes=self.duration_minutes or 60)
        return -session_duration <= delta <= timedelta(minutes=15)


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

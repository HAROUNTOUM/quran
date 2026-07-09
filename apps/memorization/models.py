"""Memorization domain models.

CANONICAL MODELS (HAF-01) — read/write these:
  • MemorizationRecord — the single source of truth for a student's position
    and spaced-repetition state, keyed by Rub (ربع الحزب). Surah/ayah are
    derived from the rub, never stored. All new memorization progress flows
    through here (StudyTask.validate() bridges into it).
  • ReviewHistory     — append-only log of every SRS evaluation.
  • ProgressLog       — append-only per-session recitation log (what happened
    in a given session); complements, does not duplicate, MemorizationRecord.
  • StudyTask         — assigned work; completes *into* a MemorizationRecord.

DEPRECATED — do not add new writers:
  • MemorizationProgress — the pre-SRS, enrollment-scoped, free ayah-range
    tracker. Still read by legacy dashboards/reports/API for historical data.
    Retirement requires a data-migration that maps each row's ayah range onto
    the rubs it covers and folds it into MemorizationRecord; tracked as a
    follow-up (not a same-pass change — it needs a backfill + read-path swap
    across api/serializers.py, reports/views.py and the accounts dashboards).
"""
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from datetime import date, timedelta
from django.utils import timezone

from apps.accounts.models import User


class ReviewRequestQuerySet(models.QuerySet):
    def pending(self):
        return self.filter(status=ReviewRequest.Status.PENDING)

    def overdue(self):
        cutoff = timezone.now() - timedelta(days=ReviewRequest.overdue_after_days())
        return self.pending().filter(created_at__lt=cutoff)

    def for_teacher(self, teacher):
        return self.filter(circle__teacher=teacher)


class ReviewRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "قيد الانتظار"
        APPROVED = "approved", "مقبول"
        REJECTED = "rejected", "مرفوض"

    class Type(models.TextChoices):
        # HAF: مراجعة merged into تسميع — a single private-session request type.
        RECITATION = "recitation", "تسميع"
        QUESTION = "question", "سؤال للمعلم"

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="review_requests",
    )
    circle = models.ForeignKey(
        "circles.Circle", on_delete=models.CASCADE,
        related_name="review_requests",
    )
    type = models.CharField(max_length=20, choices=Type.choices, verbose_name="نوع الطلب")
    surah = models.ForeignKey(
        "references.Surah", on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="السورة",
    )
    ayah_from = models.IntegerField("من الآية", null=True, blank=True)
    ayah_to = models.IntegerField("إلى الآية", null=True, blank=True)
    notes = models.TextField("ملاحظات الطالب", blank=True)
    response = models.TextField("رد المعلم", blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reviewed_requests",
    )
    rejection_reason = models.TextField("سبب الرفض", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    preferred_days = models.JSONField("الأيام المفضلة", default=list, blank=True)
    preferred_times = models.JSONField("الأوقات المفضلة", default=list, blank=True)
    scheduled_date = models.DateField("تاريخ المراجعة", null=True, blank=True)
    scheduled_time = models.TimeField("وقت المراجعة", null=True, blank=True)
    meeting_url = models.URLField("رابط الاجتماع", max_length=500, blank=True)
    meeting_platform = models.CharField(
        "منصة الاجتماع", max_length=20, blank=True,
        choices=[
            ("zoom", "Zoom"), ("google_meet", "Google Meet"),
            ("teams", "Microsoft Teams"), ("whatsapp", "WhatsApp"),
            ("telegram", "Telegram"), ("other", "أخرى"),
        ],
    )

    class Meta:
        verbose_name = "طلب مراجعة/تسميع"
        verbose_name_plural = "طلبات المراجعة والتسميع"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_type_display()} — {self.student.full_name_ar}"

    def validate_relationships(self):
        """Rule 2 integrity: the request must reference a student actively
        enrolled in the circle it targets. Called from clean() and enforced
        at creation by a pre_save signal (backstop for programmatic creates
        that bypass forms)."""
        from django.core.exceptions import ValidationError
        from apps.circles.models import CircleEnrollment

        if not CircleEnrollment.objects.filter(
            circle_id=self.circle_id,
            student_id=self.student_id,
            status=CircleEnrollment.Status.ACTIVE,
        ).exists():
            raise ValidationError(
                "لا يمكن إنشاء الطلب: الطالب غير مسجل تسجيلاً نشطاً في هذه الحلقة"
            )

    def clean(self):
        super().clean()
        # Only at creation — legacy requests stay editable (approve/reject)
        # even if the student has since left the circle.
        if self.pk is None:
            self.validate_relationships()

    # ------------------------------------------------------------------
    # Section A — the Request model owns validation, status transitions
    # and overdue detection. Views (web + API) delegate here.
    # ------------------------------------------------------------------

    objects = ReviewRequestQuerySet.as_manager()

    @staticmethod
    def overdue_after_days() -> int:
        try:
            from apps.usersettings.services import get_system_setting
            return int(get_system_setting("request_overdue_days"))
        except Exception:
            return 3

    def can_be_responded_by(self, user) -> bool:
        """Only the circle's own teacher (or admin/supervisor) may respond."""
        if user.role in (User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN):
            return True
        return user.role == "teacher" and self.circle.teacher_id == user.id

    def _check_respondable(self, by):
        from django.core.exceptions import ValidationError
        if self.status != self.Status.PENDING:
            raise ValidationError("تمت معالجة الطلب مسبقاً")
        if not self.can_be_responded_by(by):
            raise ValidationError("لا تملك صلاحية الرد على هذا الطلب")

    def approve(self, by, scheduled_date=None, scheduled_time=None,
                meeting_url="", meeting_platform=""):
        from django.core.exceptions import ValidationError
        self._check_respondable(by)
        valid_platforms = {c[0] for c in self._meta.get_field("meeting_platform").choices}
        if meeting_platform and meeting_platform not in valid_platforms:
            raise ValidationError("منصة اجتماع غير صالحة")
        self.status = self.Status.APPROVED
        self.reviewed_by = by
        self.scheduled_date = scheduled_date or None
        self.scheduled_time = scheduled_time or None
        self.meeting_url = meeting_url or ""
        self.meeting_platform = meeting_platform or ""
        self.save(update_fields=[
            "status", "reviewed_by", "scheduled_date", "scheduled_time",
            "meeting_url", "meeting_platform", "updated_at",
        ])
        # A تسميع approval spawns a private 1-on-1 session (link/time/reminder/
        # marking) between the student and the approving teacher.
        if self.type == self.Type.RECITATION:
            PrivateSession.create_from_request(self, by)
        return self

    def reject(self, by, reason=""):
        self._check_respondable(by)
        self.status = self.Status.REJECTED
        self.reviewed_by = by
        self.rejection_reason = reason or ""
        self.save(update_fields=["status", "reviewed_by", "rejection_reason", "updated_at"])
        return self

    def answer(self, by, response_text):
        """Teacher answers a student's سؤال للمعلم. Unlike review/recitation, a
        question isn't scheduled — it's resolved with a written reply. Marks the
        ticket APPROVED (resolved) and stores the answer."""
        from django.core.exceptions import ValidationError
        self._check_respondable(by)
        if self.type != self.Type.QUESTION:
            raise ValidationError("هذا الإجراء مخصص لأسئلة الطلاب فقط")
        text = (response_text or "").strip()
        if not text:
            raise ValidationError("يرجى كتابة الرد على السؤال")
        self.status = self.Status.APPROVED
        self.reviewed_by = by
        self.response = text
        self.save(update_fields=["status", "reviewed_by", "response", "updated_at"])
        return self

    @property
    def is_overdue(self) -> bool:
        if self.status != self.Status.PENDING:
            return False
        return self.created_at < timezone.now() - timedelta(days=self.overdue_after_days())


class PrivateSession(models.Model):
    """A private 1-on-1 session between a student and their teacher, spawned when
    the teacher approves a تسميع (recitation) request. Behaves like a normal
    session — it carries a meeting link, a time, reminders, and teacher results
    marking — but it is private to the two of them (not a circle-wide session)."""

    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "مجدولة"
        COMPLETED = "completed", "مكتملة"
        CANCELLED = "cancelled", "ملغاة"

    source_request = models.OneToOneField(
        "ReviewRequest", on_delete=models.CASCADE, related_name="private_session",
        null=True, blank=True, verbose_name="الطلب المصدر",
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="private_sessions_taught", verbose_name="المعلم",
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="private_sessions", verbose_name="الطالب",
    )
    circle = models.ForeignKey(
        "circles.Circle", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="private_sessions", verbose_name="الحلقة",
    )
    scheduled_date = models.DateField("التاريخ", null=True, blank=True)
    scheduled_time = models.TimeField("الوقت", null=True, blank=True)
    meeting_url = models.URLField("رابط الاجتماع", max_length=500, blank=True)
    meeting_platform = models.CharField(
        "منصة الاجتماع", max_length=20, blank=True,
        choices=[
            ("zoom", "Zoom"), ("google_meet", "Google Meet"),
            ("teams", "Microsoft Teams"), ("whatsapp", "WhatsApp"),
            ("telegram", "Telegram"), ("other", "أخرى"),
        ],
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SCHEDULED)
    student_notes = models.TextField("طلب الطالب", blank=True)
    result_mark = models.CharField("التقييم", max_length=50, blank=True)
    result_notes = models.TextField("ملاحظات المعلم", blank=True)
    reminder_sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "جلسة خاصة"
        verbose_name_plural = "الجلسات الخاصة"
        ordering = ["-scheduled_date", "-created_at"]
        indexes = [models.Index(fields=["student", "status"])]

    def __str__(self):
        return f"جلسة خاصة — {self.student.full_name_ar} ({self.scheduled_date})"

    def effective_meeting_url(self):
        """The link the student actually joins. Mirrors
        `circles.Session.effective_meeting_url()`: use the explicit
        `meeting_url` if set, otherwise fall back to the teacher's permanent
        classroom room so an approved session is never blank."""
        if self.meeting_url:
            return self.meeting_url
        if self.teacher_id is None:
            return ""
        from django.urls import reverse
        from apps.classrooms.models import TeacherRoom
        room = TeacherRoom.objects.filter(teacher_id=self.teacher_id).only("slug").first()
        if room:
            return reverse("classrooms:join", kwargs={"slug": room.slug})
        return ""

    @classmethod
    def create_from_request(cls, review_request, teacher):
        """Create (or refresh) the private session for an approved تسميع request
        and notify the student with the link + time (the confirmation reminder)."""
        session, _created = cls.objects.update_or_create(
            source_request=review_request,
            defaults={
                "teacher": teacher,
                "student": review_request.student,
                "circle": review_request.circle,
                "scheduled_date": review_request.scheduled_date,
                "scheduled_time": review_request.scheduled_time,
                "meeting_url": review_request.meeting_url,
                "meeting_platform": review_request.meeting_platform,
                "student_notes": review_request.notes,
                "status": cls.Status.SCHEDULED,
            },
        )
        session._notify_scheduled()
        return session

    @staticmethod
    def _fmt_time(t):
        """Format a time that may still be a raw HH:MM string (fresh from a POST)
        or a proper time object (reloaded from the DB)."""
        if not t:
            return ""
        return t.strftime("%H:%M") if hasattr(t, "strftime") else str(t)

    def _notify_scheduled(self):
        from apps.notifications.services import notify
        when = ""
        if self.scheduled_date:
            when = f" — {self.scheduled_date}"
            if self.scheduled_time:
                when += f" {self._fmt_time(self.scheduled_time)}"
        notify(
            recipient=self.student,
            type="review_request",
            title="تم تحديد جلسة تسميع خاصة",
            message=f"حدّد لك معلمك جلسة تسميع خاصة{when}",
            link="/dashboard/student/private-sessions/",
        )

    def mark_result(self, by, result_mark, result_notes=""):
        """Teacher records the outcome of the private session (marking)."""
        from django.core.exceptions import ValidationError
        if by.role not in (User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN) and by.id != self.teacher_id:
            raise ValidationError("لا تملك صلاحية تقييم هذه الجلسة")
        self.result_mark = (result_mark or "").strip()
        self.result_notes = (result_notes or "").strip()
        self.status = self.Status.COMPLETED
        self.save(update_fields=["result_mark", "result_notes", "status", "updated_at"])
        from apps.notifications.services import notify
        notify(
            recipient=self.student,
            type="review_request",
            title="تم تقييم جلستك الخاصة",
            message="سجّل معلمك نتيجة جلسة التسميع الخاصة بك",
            link="/dashboard/student/private-sessions/",
        )
        return self

    def send_reminder(self):
        """Notify the student of an upcoming private session. Called by the
        `send_session_reminders` command; idempotent per session."""
        from apps.notifications.services import notify
        when = ""
        if self.scheduled_time:
            when = f" الساعة {self._fmt_time(self.scheduled_time)}"
        notify(
            recipient=self.student,
            type="review_request",
            title="تذكير: جلسة تسميع خاصة",
            message=f"لديك جلسة تسميع خاصة مع معلمك{when}",
            link="/dashboard/student/private-sessions/",
        )
        self.reminder_sent_at = timezone.now()
        self.save(update_fields=["reminder_sent_at", "updated_at"])


class MemorizationProgressQuerySet(models.QuerySet):
    def for_student(self, student):
        return self.filter(enrollment__student=student)

    def for_teacher(self, teacher):
        return self.filter(enrollment__circle__teacher=teacher)

    def for_period(self, start, end):
        return self.filter(created_at__gte=start, created_at__lte=end)

    def hifz_only(self):
        return self.filter(type=MemorizationProgress.Type.HIFZ)

    def murajaa_only(self):
        return self.filter(type=MemorizationProgress.Type.MURAJAA)

    def total_ayahs(self):
        return self.aggregate(total=Sum("ayah_to") - Sum("ayah_from") + Count("id"))["total"] or 0

    def type_breakdown(self):
        return self.values("type").annotate(
            total=Count("id"),
            ayahs=Sum("ayah_to") - Sum("ayah_from") + Count("id"),
        )

    def status_breakdown(self):
        return self.values("status").annotate(count=Count("id"))

    def mastered(self):
        return self.filter(status=MemorizationProgress.Status.MASTERED)

    def completion_rate(self):
        total = self.count()
        if total == 0:
            return 0.0
        mastered = self.mastered().count()
        return round(mastered / total * 100, 1)


class MemorizationProgress(models.Model):
    """DEPRECATED (HAF-01) — legacy enrollment-scoped tracker. Read-only for
    historical data; new progress goes to MemorizationRecord. See module docstring."""

    class Type(models.TextChoices):
        HIFZ = 'hifz', 'حفظ جديد'
        MURAJAA = 'murajaa', 'مراجعة'

    class Status(models.TextChoices):
        MEMORIZING = 'memorizing', 'في طور الحفظ'
        REVIEWED = 'reviewed', 'مراجع'
        TESTED = 'tested', 'مختبر'
        MASTERED = 'mastered', 'متقن'
        WEAK = 'weak', 'ضعيف'

    enrollment = models.ForeignKey(
        'circles.CircleEnrollment', on_delete=models.CASCADE,
        related_name='memorization_progress'
    )
    type = models.CharField(
        max_length=20, choices=Type.choices, default=Type.HIFZ,
        verbose_name='النوع'
    )
    surah = models.ForeignKey(
        'references.Surah', on_delete=models.RESTRICT,
        related_name='progress_records'
    )
    ayah_from = models.IntegerField()
    ayah_to = models.IntegerField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.MEMORIZING)
    revision_count = models.IntegerField(default=0, verbose_name='عدد مرات المراجعة')
    last_revised_at = models.DateTimeField(null=True, blank=True, verbose_name='آخر مراجعة')
    tested_at = models.DateTimeField(null=True, blank=True)
    tested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = MemorizationProgressQuerySet.as_manager()

    class Meta:
        verbose_name = 'تقدم حفظ/مراجعة'
        verbose_name_plural = 'تقدم الحفظ والمراجعة'

    def __str__(self):
        return f'{self.get_type_display()} — سورة {self.surah.name_ar} ({self.ayah_from}-{self.ayah_to})'


class ProgressLogQuerySet(models.QuerySet):
    def for_student(self, student):
        return self.filter(student=student)

    def for_teacher(self, teacher):
        return self.filter(session__circle__teacher=teacher)

    def for_period(self, start, end):
        return self.filter(created_at__gte=start, created_at__lte=end)

    def hifdh(self):
        return self.filter(log_category=ProgressLog.Category.HIFDH)

    def murajaah(self):
        return self.filter(log_category=ProgressLog.Category.MURAJAAH)

    def total_pages(self):
        return self.aggregate(total=models.Sum("completed_pages"))["total"] or 0

    def category_breakdown(self):
        return self.values("log_category").annotate(
            count=models.Count("id"),
            pages=models.Sum("completed_pages"),
        )

    def grade_distribution(self):
        return self.values("evaluation_grade").annotate(count=models.Count("id"))

    def grade_avg(self):
        mapping = {"A+": 4.3, "A": 4.0, "B": 3.0, "C": 2.0, "D": 1.0, "ممتاز": 4.0, "جيد جداً": 3.0, "جيد": 2.0, "ضعيف": 1.0}
        grades = self.exclude(evaluation_grade="").values_list("evaluation_grade", flat=True)
        if not grades:
            return 0.0
        numeric = [mapping.get(g, 2.0) for g in grades]
        return round(sum(numeric) / len(numeric), 1)


class ProgressLog(models.Model):
    class Category(models.TextChoices):
        # The recorded session type: memorization, review, or recitation.
        HIFDH = "HIFDH", "حفظ جديد"
        MURAJAAH = "MURAJAAH", "مراجعة"
        RECITATION = "RECITATION", "تلاوة"

    class Grade(models.TextChoices):
        A_PLUS = "A+", "A+"
        A = "A", "A"
        B = "B", "B"
        C = "C", "C"
        D = "D", "D"
        EXCELLENT = "ممتاز", "ممتاز"
        VERY_GOOD = "جيد جداً", "جيد جداً"
        GOOD = "جيد", "جيد"
        WEAK = "ضعيف", "ضعيف"

    session = models.ForeignKey(
        "circles.Session", on_delete=models.CASCADE,
        related_name="progress_logs",
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="progress_logs",
    )
    log_category = models.CharField(
        max_length=20, choices=Category.choices, verbose_name="نوع التسجيل",
    )
    surah = models.ForeignKey(
        "references.Surah", on_delete=models.RESTRICT,
        verbose_name="السورة",
    )
    start_ayah = models.IntegerField("من الآية")
    end_ayah = models.IntegerField("إلى الآية")
    completed_pages = models.DecimalField(
        "عدد الصفحات", max_digits=5, decimal_places=2, null=True, blank=True,
    )
    evaluation_grade = models.CharField(
        max_length=10, choices=Grade.choices, blank=True, verbose_name="الدرجة التقديرية",
    )
    points = models.DecimalField(
        "النقطة من 20", max_digits=4, decimal_places=1, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(20)],
    )
    teacher_notes = models.TextField("ملاحظات المعلم", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ProgressLogQuerySet.as_manager()

    class Meta:
        verbose_name = "سجل تقدم"
        verbose_name_plural = "سجلات التقدم"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_log_category_display()} — {self.student.full_name_ar}"


class StudentAchievement(models.Model):
    student = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="achievement",
    )
    total_hifdh_ayahs = models.IntegerField("إجمالي آيات الحفظ", default=0)
    total_murajaah_ayahs = models.IntegerField("إجمالي آيات المراجعة", default=0)
    # Progress in the platform tracking unit (thumn = 1/8 hizb), resolved
    # against real Warsh boundaries — distinct athman covered per category.
    total_hifdh_thumns = models.IntegerField("إجمالي أثمان الحفظ", default=0)
    total_murajaah_thumns = models.IntegerField("إجمالي أثمان المراجعة", default=0)
    total_hifdh_pages = models.DecimalField(
        "إجمالي صفحات الحفظ", max_digits=7, decimal_places=2, default=0,
    )
    total_murajaah_pages = models.DecimalField(
        "إجمالي صفحات المراجعة", max_digits=7, decimal_places=2, default=0,
    )
    completed_juz = models.IntegerField("الأجزاء المنجزة", default=0)
    current_juz = models.IntegerField("الجزء الحالي", default=1)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "إنجاز طالب"
        verbose_name_plural = "إنجازات الطلاب"

    def __str__(self):
        return f"إنجاز {self.student.full_name_ar}"


class RecitationGrade(models.Model):
    session = models.ForeignKey(
        'circles.Session', on_delete=models.CASCADE,
        related_name='recitation_grades'
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='recitation_grades'
    )
    criterion = models.ForeignKey(
        'references.EvaluationCriterion', on_delete=models.RESTRICT,
        related_name='grades'
    )
    score = models.FloatField()
    max_score = models.FloatField(default=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'درجة تلاوة'
        verbose_name_plural = 'درجات التلاوة'

    def __str__(self):
        return f'{self.student.full_name_ar} — {self.criterion.name_ar}: {self.score}/{self.max_score}'


class MemorizationRecordQuerySet(models.QuerySet):
    def for_student(self, student):
        return self.filter(student=student)

    def due(self, student, on_date=None):
        """Records whose review is due on or before `on_date` (default today),
        overdue first — this IS the daily review plan (no persisted DailyPlan)."""
        on_date = on_date or timezone.localdate()
        return (
            self.filter(student=student, next_review_date__isnull=False,
                        next_review_date__lte=on_date)
            .exclude(status=MemorizationRecord.Status.NOT_MEMORIZED)
            .select_related("rub__hizb__juz")
            .order_by("next_review_date", "rub__number")
        )

    def memorized(self, student):
        return self.filter(student=student).exclude(
            status=MemorizationRecord.Status.NOT_MEMORIZED
        )


class MemorizationRecord(models.Model):
    """A student's memorization state for one Rub (ربع الحزب). The Rub FK is the
    single source of truth for position — surah/ayah are derived, never stored."""

    class Status(models.TextChoices):
        NOT_MEMORIZED = "NOT_MEMORIZED", "لم يُحفظ"
        IN_PROGRESS = "IN_PROGRESS", "قيد الحفظ"
        MEMORIZED = "MEMORIZED", "محفوظ"
        NEEDS_REVIEW = "NEEDS_REVIEW", "يحتاج مراجعة"
        WEAK = "WEAK", "ضعيف"
        MASTERED = "MASTERED", "متقن"

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="memorization_records",
    )
    rub = models.ForeignKey(
        "references.Rub", on_delete=models.PROTECT,
        related_name="memorization_records", verbose_name="الربع",
    )
    circle = models.ForeignKey(
        "circles.Circle", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="memorization_records",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.NOT_MEMORIZED,
    )
    memorized_at = models.DateTimeField(null=True, blank=True)
    last_reviewed_at = models.DateTimeField(null=True, blank=True)
    next_review_date = models.DateField(null=True, blank=True)
    review_interval_days = models.IntegerField(default=0)
    review_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = MemorizationRecordQuerySet.as_manager()

    class Meta:
        verbose_name = "سجل حفظ"
        verbose_name_plural = "سجلات الحفظ"
        ordering = ["student", "rub__number"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "rub"], name="uniq_memorization_student_rub"
            ),
        ]
        indexes = [
            models.Index(fields=["student", "next_review_date"]),
            models.Index(fields=["student", "status"]),
        ]

    def __str__(self):
        return f"{self.student.full_name_ar} — {self.rub} ({self.get_status_display()})"

    @classmethod
    def record_for(cls, student, rub, circle=None):
        """Get or create the (student, rub) record. `rub` may be a Rub or its number."""
        from apps.references.models import Rub

        if not isinstance(rub, Rub):
            rub = Rub.objects.get(number=rub)
        record, _ = cls.objects.get_or_create(
            student=student, rub=rub, defaults={"circle": circle},
        )
        return record

    @property
    def is_due(self):
        return (
            self.next_review_date is not None
            and self.next_review_date <= timezone.localdate()
            and self.status != self.Status.NOT_MEMORIZED
        )

    # ── Transitions (fat model) ─────────────────────────────────────────
    def mark_memorized(self, by=None):
        """Student records having memorized this rub. Schedules the first review."""
        from . import review_engine

        if self.status == self.Status.NOT_MEMORIZED:
            self.status = self.Status.MEMORIZED
        if self.memorized_at is None:
            self.memorized_at = timezone.now()
        interval = review_engine.first_interval_days()
        self.review_interval_days = interval
        self.next_review_date = review_engine.next_review_date(
            timezone.localdate(), interval
        )
        self.save(update_fields=[
            "status", "memorized_at", "review_interval_days",
            "next_review_date", "updated_at",
        ])
        self._sync_current_surah()

    def _sync_current_surah(self):
        """Keep the denormalized CircleEnrollment.current_surah in step with
        the student's real frontier (HAF-08)."""
        from apps.circles.models import CircleEnrollment
        qs = CircleEnrollment.objects.filter(
            student_id=self.student_id, status=CircleEnrollment.Status.ACTIVE,
        )
        if self.circle_id:
            qs = qs.filter(circle_id=self.circle_id)
        for enrollment in qs:
            enrollment.refresh_current_surah()

    def evaluate(self, by, evaluation, mistakes_count=0, notes="", session=None):
        """Record a teacher evaluation of a review, append history, and reschedule.
        `by` must teach this student (enforced) or be staff."""
        from django.core.exceptions import ValidationError
        from django.db import transaction
        from . import review_engine

        if evaluation not in review_engine.EVALUATION_MULTIPLIERS:
            raise ValidationError("تقييم غير صالح")
        if by is not None and getattr(by, "role", None) == "teacher":
            if not by.teaches_student(self.student):
                raise ValidationError("لا يمكنك تقييم هذا الطالب")

        prev_status = self.status
        prev_interval = self.review_interval_days
        new_interval = review_engine.calculate_next_interval(
            prev_interval, evaluation, mistakes_count
        )
        new_status = review_engine.status_after_evaluation(evaluation, prev_status)

        with transaction.atomic():
            self.review_interval_days = new_interval
            self.review_count += 1
            self.last_reviewed_at = timezone.now()
            self.next_review_date = review_engine.next_review_date(
                timezone.localdate(), new_interval
            )
            self.status = new_status
            if self.memorized_at is None:
                self.memorized_at = timezone.now()
            self.save(update_fields=[
                "review_interval_days", "review_count", "last_reviewed_at",
                "next_review_date", "status", "memorized_at", "updated_at",
            ])
            history = ReviewHistory.objects.create(
                record=self, reviewer=by, evaluation=evaluation,
                mistakes_count=mistakes_count or 0, teacher_notes=notes or "",
                previous_interval=prev_interval, new_interval=new_interval,
                previous_status=prev_status, new_status=new_status,
                session=session,
            )
        return history


class ReviewHistory(models.Model):
    """Append-only log of every review evaluation. Never updated or deleted."""

    record = models.ForeignKey(
        MemorizationRecord, on_delete=models.CASCADE, related_name="history",
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="given_review_evaluations",
    )
    evaluation = models.CharField(max_length=20, verbose_name="التقييم")
    mistakes_count = models.IntegerField(default=0, verbose_name="عدد الأخطاء")
    teacher_notes = models.TextField(blank=True, verbose_name="ملاحظات")
    previous_interval = models.IntegerField(default=0)
    new_interval = models.IntegerField(default=0)
    previous_status = models.CharField(max_length=20, blank=True)
    new_status = models.CharField(max_length=20, blank=True)
    session = models.ForeignKey(
        "circles.Session", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="review_evaluations",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "سجل مراجعة"
        verbose_name_plural = "سجل المراجعات"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.record.student.full_name_ar} — {self.evaluation} ({self.created_at:%Y-%m-%d})"


class StudyTaskQuerySet(models.QuerySet):
    def for_student(self, student):
        return self.filter(student=student)

    def for_teacher(self, teacher):
        return self.filter(assigned_by=teacher)

    def pending(self):
        return self.filter(status=StudyTask.Status.PENDING)

    def done(self):
        return self.filter(status=StudyTask.Status.DONE)

    def validated(self):
        return self.filter(status=StudyTask.Status.VALIDATED)

    def overdue(self):
        """Pending tasks whose due date has passed."""
        return self.pending().filter(
            due_date__isnull=False, due_date__lt=timezone.localdate()
        )


class StudyTask(models.Model):
    class TaskType(models.TextChoices):
        HIFZ = 'hifz', 'حفظ جديد'
        MURAJAA = 'murajaa', 'مراجعة'
        RECITATION = 'recitation', 'تلاوة'

    class Status(models.TextChoices):
        PENDING = 'pending', 'قيد الانتظار'
        DONE = 'done', 'تم الإنجاز'
        VALIDATED = 'validated', 'تم التحقق'
        REJECTED = 'rejected', 'مرفوض'

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='study_tasks', verbose_name='الطالب',
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='assigned_tasks',
        verbose_name='المسند من',
    )
    circle = models.ForeignKey(
        'circles.Circle', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='study_tasks',
        verbose_name='الحلقة',
    )
    session = models.ForeignKey(
        'circles.Session', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='study_tasks',
        verbose_name='الحصة المرتبطة',
        help_text='الحصة التي أُسندت المهمة عقبها',
    )
    due_date = models.DateField('تاريخ الاستحقاق', null=True, blank=True)
    task_type = models.CharField(
        max_length=20, choices=TaskType.choices, verbose_name='نوع المهمة',
    )
    surah = models.ForeignKey(
        'references.Surah', on_delete=models.RESTRICT,
        verbose_name='السورة',
    )
    ayah_from = models.IntegerField(verbose_name='من الآية')
    ayah_to = models.IntegerField(verbose_name='إلى الآية')
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING,
        verbose_name='الحالة',
    )
    rejection_reason = models.TextField(blank=True, verbose_name='سبب الرفض')
    notes = models.TextField(blank=True, verbose_name='ملاحظات')
    validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='validated_tasks',
        verbose_name='تم التحقق بواسطة',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    validated_at = models.DateTimeField(null=True, blank=True)

    objects = StudyTaskQuerySet.as_manager()

    class Meta:
        verbose_name = 'مهمة حفظ/مراجعة'
        verbose_name_plural = 'مهام الحفظ والمراجعة'
        ordering = ['-created_at']
        indexes = [
            # L13: task lists always filter by (student, status).
            models.Index(fields=["student", "status"]),
        ]

    def __str__(self):
        return f'{self.get_task_type_display()} — {self.surah.name_ar} ({self.ayah_from}-{self.ayah_to})'

    @property
    def is_overdue(self) -> bool:
        return (
            self.status == self.Status.PENDING
            and self.due_date is not None
            and self.due_date < timezone.localdate()
        )

    # ── Validation (HAF-03: the same unbounded-ayah bug the QuranSelector
    # fixed for review requests — enforced here at the model level so admin,
    # API and programmatic writes cannot store an impossible range) ─────────
    def clean(self):
        super().clean()
        from apps.references.utils import validate_ayah_range
        if self.surah_id and self.ayah_from is not None and self.ayah_to is not None:
            validate_ayah_range(self.surah_id, self.ayah_from, self.ayah_to)

    def save(self, *args, **kwargs):
        # Validate the ayah range whenever a save touches the content fields
        # (creation, or an edit of surah/ayah). Status-only saves that pass an
        # explicit update_fields skip it, so transitions stay cheap.
        update_fields = kwargs.get("update_fields")
        content_fields = {"surah", "surah_id", "ayah_from", "ayah_to"}
        touches_content = update_fields is None or bool(content_fields & set(update_fields))
        if touches_content and self.surah_id and self.ayah_from is not None and self.ayah_to is not None:
            from apps.references.utils import validate_ayah_range
            validate_ayah_range(self.surah_id, self.ayah_from, self.ayah_to)
        super().save(*args, **kwargs)

    # ── Creation (fat model: validation + permission + notification live here,
    # never re-implemented per view) ────────────────────────────────────────
    @classmethod
    def assign(cls, student, assigned_by, task_type, surah, ayah_from, ayah_to,
               circle=None, notes="", due_date=None, session=None):
        from django.core.exceptions import ValidationError
        from apps.references.utils import validate_ayah_range

        if assigned_by is not None and getattr(assigned_by, "role", None) == "teacher":
            if not assigned_by.teaches_student(student):
                raise ValidationError("لا يمكنك إسناد مهام لهذا الطالب")
        surah_pk = getattr(surah, "pk", surah)
        ayah_from, ayah_to = validate_ayah_range(surah_pk, ayah_from, ayah_to)
        task = cls.objects.create(
            student=student, assigned_by=assigned_by, task_type=task_type,
            surah_id=surah_pk, ayah_from=ayah_from, ayah_to=ayah_to,
            circle=circle, notes=notes or "",
            due_date=due_date or None, session=session,
        )
        task._notify_assigned()
        return task

    def update_details(self, by, task_type, surah, ayah_from, ayah_to,
                       circle=None, notes="", due_date=None, session=None):
        from django.core.exceptions import ValidationError
        from apps.references.utils import validate_ayah_range

        if by is not None and getattr(by, "role", None) == "teacher":
            if not by.teaches_student(self.student):
                raise ValidationError("لا يمكنك تعديل مهام هذا الطالب")
        surah_pk = getattr(surah, "pk", surah)
        ayah_from, ayah_to = validate_ayah_range(surah_pk, ayah_from, ayah_to)
        self.task_type = task_type
        self.surah_id = surah_pk
        self.ayah_from = ayah_from
        self.ayah_to = ayah_to
        self.circle = circle
        self.notes = notes or ""
        self.due_date = due_date or None
        if session is not None:
            self.session = session
        self.assigned_by = by
        self.save(update_fields=[
            "task_type", "surah_id", "ayah_from", "ayah_to",
            "circle_id", "notes", "due_date", "session_id",
            "assigned_by", "updated_at",
        ])
        return self

    # ── Transitions ─────────────────────────────────────────────────────────
    def mark_done(self, by=None):
        from django.core.exceptions import ValidationError
        from django.utils import timezone

        if self.status != self.Status.PENDING:
            raise ValidationError("لا يمكن إنجاز إلا مهمة قيد الانتظار")
        self.status = self.Status.DONE
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'completed_at', 'updated_at'])
        self._notify_done()
        return self

    def validate(self, by, rejection_reason=''):
        """Teacher accepts or rejects a completed task. Enforces that `by`
        teaches this student (HAF-07), that the task is DONE (state guard),
        records who validated, and — on acceptance of a hifz task — advances
        the student's MemorizationRecord for every covered rub (HAF-21)."""
        from django.core.exceptions import ValidationError
        from django.db import transaction
        from django.utils import timezone

        if self.status != self.Status.DONE:
            raise ValidationError("لا يمكن التحقق إلا من مهمة تم إنجازها")
        if by is not None and getattr(by, "role", None) == "teacher":
            if not by.teaches_student(self.student):
                raise ValidationError("لا يمكنك التحقق من مهام هذا الطالب")

        with transaction.atomic():
            self.status = self.Status.REJECTED if rejection_reason else self.Status.VALIDATED
            self.rejection_reason = rejection_reason or ""
            self.validated_by = by if getattr(by, "pk", None) else None
            self.validated_at = timezone.now()
            self.save(update_fields=[
                'status', 'rejection_reason', 'validated_by',
                'validated_at', 'updated_at',
            ])
            if self.status == self.Status.VALIDATED and self.task_type == self.TaskType.HIFZ:
                self._apply_to_memorization(by)
        self._notify_validation()
        return self

    # ── HAF-01/HAF-21 bridge: a validated hifz task feeds the canonical
    # MemorizationRecord (the single source of truth for position) ──────────
    def covered_rubs(self):
        from apps.references.models import Rub
        return Rub.objects.filter(
            ayahs__surah_id=self.surah_id,
            ayahs__number_in_surah__gte=self.ayah_from,
            ayahs__number_in_surah__lte=self.ayah_to,
        ).distinct()

    def _apply_to_memorization(self, by):
        for rub in self.covered_rubs():
            record = MemorizationRecord.record_for(self.student, rub, circle=self.circle)
            if record.status == MemorizationRecord.Status.NOT_MEMORIZED:
                record.mark_memorized(by=by)

    # ── Notifications (all via the single notify() service) ─────────────────
    def _notify_assigned(self):
        from apps.notifications.services import notify
        from apps.notifications.models import Notification
        notify(
            self.student, Notification.Type.TASK_ASSIGNED, "مهمة حفظ جديدة",
            f"تم إسناد مهمة {self.get_task_type_display()} لك: "
            f"{self.surah.name_ar} ({self.ayah_from}-{self.ayah_to})",
            link="/dashboard/student/tasks/",
        )

    def _notify_done(self):
        from apps.notifications.services import notify
        from apps.notifications.models import Notification
        if self.assigned_by_id:
            notify(
                self.assigned_by, Notification.Type.TASK_ASSIGNED, "تم إنجاز مهمة",
                f"أنجز الطالب {self.student.full_name_ar} المهمة: "
                f"{self.surah.name_ar} ({self.ayah_from}-{self.ayah_to})",
                link=f"/dashboard/teacher/tasks/{self.pk}/validate/",
            )

    def _notify_validation(self):
        from apps.notifications.services import notify
        from apps.notifications.models import Notification
        if self.status == self.Status.VALIDATED:
            notify(
                self.student, Notification.Type.TASK_VALIDATED, "تم اعتماد المهمة",
                f"تم اعتماد مهمتك: {self.surah.name_ar} ({self.ayah_from}-{self.ayah_to})",
                link="/dashboard/student/tasks/",
            )
        else:
            notify(
                self.student, Notification.Type.TASK_VALIDATED, "لم يتم اعتماد المهمة",
                f"لم يتم اعتماد مهمتك: {self.surah.name_ar} "
                f"({self.ayah_from}-{self.ayah_to}) — {self.rejection_reason or 'بدون سبب'}",
                link="/dashboard/student/tasks/",
            )

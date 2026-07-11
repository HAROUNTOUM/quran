from datetime import date, timedelta

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

from apps.core.models import UUIDModel, TimeStampedModel


class Batch(TimeStampedModel):

    class Status(models.TextChoices):
        ACTIVE = "active", "نشطة"
        INACTIVE = "inactive", "غير نشطة"
        ARCHIVED = "archived", "مؤرشفة"

    name = models.CharField("اسم الدفعة", max_length=255)
    number = models.PositiveIntegerField("رقم الدفعة", null=True, blank=True, unique=True)
    year = models.CharField("السنة", max_length=20, blank=True)
    description = models.TextField("الوصف", blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE,
        verbose_name="الحالة",
    )
    start_date = models.DateField("تاريخ البداية", null=True, blank=True)
    end_date = models.DateField("تاريخ النهاية", null=True, blank=True)
    sub_admin = models.ForeignKey(
        "User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="managed_batch", verbose_name="المشرف",
    )
    sub_admins = models.ManyToManyField(
        "User", blank=True, related_name="managed_batches",
        verbose_name="المشرفون",
    )
    created_by = models.ForeignKey(
        "User", on_delete=models.CASCADE, related_name="created_batches",
        verbose_name="تم الإنشاء بواسطة",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "دفعة"
        verbose_name_plural = "الدفعات"
        constraints = [
            models.UniqueConstraint(
                fields=["name", "year"], name="unique_batch_name_per_year",
            ),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError(
                {"end_date": "تاريخ النهاية يجب أن يكون بعد تاريخ البداية"}
            )


class User(AbstractUser, UUIDModel, TimeStampedModel):

    class Role(models.TextChoices):
        MAIN_ADMIN = "admin", "مشرف عام"
        SUB_ADMIN = "supervisor", "مشرف"
        TEACHER = "teacher", "معلم"
        STUDENT = "student", "طالب"

    class ApprovalStatus(models.TextChoices):
        PENDING = "pending", "قيد الاعتماد"
        APPROVED = "approved", "معتمد"
        REJECTED = "rejected", "مرفوض"

    role = models.CharField(
        max_length=20, choices=Role.choices, default=Role.STUDENT
    )
    full_name_ar = models.CharField("الاسم الكامل", max_length=150)
    phone = models.CharField("الهاتف", max_length=30, blank=True)
    gender = models.CharField("الجنس", max_length=10, blank=True)
    is_approved = models.CharField(
        "حالة الاعتماد",
        max_length=20,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.PENDING,
    )
    rejection_reason = models.TextField("سبب الرفض", blank=True)
    is_email_verified = models.BooleanField(default=False)
    email_verification_token = models.CharField(
        max_length=64, blank=True, null=True
    )

    batch = models.ForeignKey(
        Batch, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="users", verbose_name="الدفعة",
    )

    specialization = models.CharField("التخصص", max_length=100, blank=True)
    state = models.CharField("الولاية", max_length=100, blank=True)
    level = models.CharField("المستوى", max_length=100, blank=True)
    memorization_amount = models.CharField("مقدار الحفظ", max_length=100, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.full_name_ar} ({self.get_role_display()})"

    @property
    def is_active_approved(self):
        return self.is_active and self.is_approved == self.ApprovalStatus.APPROVED

    # ------------------------------------------------------------------
    # Rule 2 — relationship integrity: every user traces back to students.
    # These are the canonical queries the permission layer checks against;
    # they self-limit by role (wrong-role callers just get empty querysets).
    # ------------------------------------------------------------------

    def get_assigned_students(self):
        """Teacher → distinct students actively enrolled in circles they teach."""
        return User.objects.filter(
            role=User.Role.STUDENT,
            enrollments__status="active",
            enrollments__circle__teacher=self,
        ).distinct()

    def get_assigned_teachers(self):
        """Student → distinct teachers of circles they are actively enrolled in."""
        return User.objects.filter(
            role=User.Role.TEACHER,
            teaching_circles__enrollments__student=self,
            teaching_circles__enrollments__status="active",
        ).distinct()

    def teaches_student(self, student) -> bool:
        """Is this user the teacher of `student` via an active enrollment?

        The single source of truth used by IsTeacherOfStudent (API) and
        teacher_of_student_required (dashboard). Never bypassed by URL checks.
        """
        if self.role != User.Role.TEACHER or student is None:
            return False
        from apps.circles.models import CircleEnrollment
        return CircleEnrollment.objects.filter(
            circle__teacher=self,
            student=student,
            status=CircleEnrollment.Status.ACTIVE,
        ).exists()

    def studies_with_teacher(self, teacher) -> bool:
        """Symmetric convenience: is this student actively enrolled with `teacher`?"""
        if self.role != User.Role.STUDENT or teacher is None:
            return False
        return teacher.teaches_student(self) if teacher.role == User.Role.TEACHER else False

    # ------------------------------------------------------------------
    # Section A — Student domain methods (fat models, thin views).
    # ------------------------------------------------------------------

    def submit_support_request(self, title, body, type="other", priority="normal"):
        """Validated support-request submission (delegates to the Request model)."""
        from apps.requests.models import SupportRequest
        return SupportRequest.submit(self, title, body, type=type, priority=priority)

    def submit_review_request(self, circle, type, surah=None, ayah_from=None,
                              ayah_to=None, notes="", preferred_days=None,
                              preferred_times=None):
        """Validated review/recitation request. Accepts model instances or
        raw pks (web forms post ids). Enrollment integrity is enforced by
        the ReviewRequest pre_save signal (Phase 1)."""
        from django.core.exceptions import ValidationError
        from apps.memorization.models import ReviewRequest

        if not circle:
            raise ValidationError("يرجى اختيار الحلقة")
        if type not in ReviewRequest.Type.values:
            raise ValidationError("نوع طلب غير صالح")

        def _to_int(value, label):
            if value in (None, ""):
                return None
            try:
                return int(value)
            except (TypeError, ValueError):
                raise ValidationError(f"قيمة غير صالحة: {label}")

        ayah_from = _to_int(ayah_from, "من الآية")
        ayah_to = _to_int(ayah_to, "إلى الآية")
        surah_pk = getattr(surah, "pk", surah) or None
        if surah_pk and ayah_from and ayah_to:
            # Enforce the surah's real ayah_count (single source of truth)
            from apps.references.utils import validate_ayah_range
            ayah_from, ayah_to = validate_ayah_range(surah_pk, ayah_from, ayah_to)
        elif ayah_from and ayah_to and ayah_from > ayah_to:
            raise ValidationError("بداية الآية يجب أن تكون أقل من أو تساوي نهايتها")

        return ReviewRequest.objects.create(
            student=self,
            circle_id=getattr(circle, "pk", circle),
            type=type,
            surah_id=surah_pk,
            ayah_from=ayah_from, ayah_to=ayah_to,
            notes=notes or "",
            preferred_days=preferred_days or [],
            preferred_times=preferred_times or [],
        )

    def get_support_requests(self, status=None, type=None):
        from apps.requests.models import SupportRequest
        qs = SupportRequest.objects.for_user(self)
        if status:
            qs = qs.filter(status=status)
        if type:
            qs = qs.filter(type=type)
        return qs

    def attendance_stats(self) -> dict:
        """Single-query attendance breakdown: present/absent/excused/total/rate."""
        from django.db.models import Count, Q
        from apps.attendance.models import Attendance

        stats = Attendance.objects.filter(student=self).aggregate(
            total=Count("id"),
            present=Count("id", filter=Q(status=Attendance.Status.PRESENT)),
            absent=Count("id", filter=Q(status__in=[
                Attendance.Status.ABSENT_UNJUSTIFIED, Attendance.Status.ABSENT,
            ])),
            excused=Count("id", filter=Q(status=Attendance.Status.ABSENT_JUSTIFIED)),
        )
        total = stats["total"] or 0
        stats["rate"] = round((stats["present"] or 0) / total * 100, 1) if total else 0
        return stats

    def attendance_percentage(self) -> float:
        return self.attendance_stats()["rate"]

    def grade_average(self, method=None):
        """Average recitation grade. Method comes from the admin system
        setting `grade_calculation_method` unless overridden:
        - simple_average: mean of raw scores
        - normalized_percent: sum(score)/sum(max_score) * 100
        Returns None when the student has no grades yet."""
        from django.db.models import Avg, Sum
        from apps.memorization.models import RecitationGrade

        if method is None:
            try:
                from apps.usersettings.services import get_system_setting
                method = get_system_setting("grade_calculation_method")
            except Exception:
                method = "simple_average"

        qs = RecitationGrade.objects.filter(student=self)
        if method == "normalized_percent":
            agg = qs.aggregate(s=Sum("score"), m=Sum("max_score"))
            if not agg["m"]:
                return None
            return round(agg["s"] / agg["m"] * 100, 1)
        avg = qs.aggregate(a=Avg("score"))["a"]
        return round(avg, 1) if avg is not None else None

    # ------------------------------------------------------------------
    # Section A — Teacher domain methods.
    # ------------------------------------------------------------------

    def get_or_create_room(self):
        """The teacher's permanent classroom (Section C) — created once,
        reused forever. Only meaningful for teachers."""
        from django.core.exceptions import ValidationError
        from apps.classrooms.models import TeacherRoom
        if self.role != User.Role.TEACHER:
            raise ValidationError("القاعات الدائمة للمعلمين فقط")
        return TeacherRoom.get_or_create_for(self)

    def get_pending_review_requests(self):
        from apps.memorization.models import ReviewRequest
        return ReviewRequest.objects.for_teacher(self).pending().select_related(
            "student", "circle", "surah",
        )

    def get_pending_reschedule_requests(self):
        from apps.circles.models import SessionRescheduleRequest
        return SessionRescheduleRequest.objects.filter(
            session__circle__teacher=self,
            status=SessionRescheduleRequest.Status.PENDING,
        ).select_related("session__circle", "requested_by")

    def get_roster(self, circle=None):
        """Active enrollments across this teacher's circles (classroom roster)."""
        from apps.circles.models import CircleEnrollment
        qs = CircleEnrollment.objects.filter(
            circle__teacher=self,
            status=CircleEnrollment.Status.ACTIVE,
        ).select_related("student", "circle", "current_surah")
        if circle is not None:
            qs = qs.filter(circle=circle)
        return qs

    def respond_to_review_request(self, review_request, action, **kwargs):
        """Thin authority wrapper — validation and transition live on the model."""
        from django.core.exceptions import ValidationError
        if action == "approve":
            return review_request.approve(by=self, **kwargs)
        if action == "reject":
            return review_request.reject(by=self, reason=kwargs.get("reason", ""))
        if action == "answer":
            return review_request.answer(by=self, response_text=kwargs.get("response", ""))
        raise ValidationError("إجراء غير معروف")


class StudentCard(UUIDModel, TimeStampedModel):
    student = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="card",
        verbose_name="الطالب", limit_choices_to={"role": User.Role.STUDENT}
    )
    card_number = models.CharField("رقم البطاقة", max_length=30, unique=True)
    qr_code_data = models.TextField("بيانات QR")

    class Meta:
        verbose_name = "بطاقة إدلاء"
        verbose_name_plural = "بطاقات الإدلاء"

    def __str__(self):
        return f"{self.card_number} — {self.student.full_name_ar}"


class TeacherAbsence(models.Model):

    class Status(models.TextChoices):
        PENDING = "pending", "قيد الانتظار"
        APPROVED = "approved", "مقبول"
        REJECTED = "rejected", "مرفوض"

    teacher = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="absence_requests",
        verbose_name="المعلم", limit_choices_to={"role": User.Role.TEACHER},
    )
    start_date = models.DateField("تاريخ البداية")
    end_date = models.DateField("تاريخ النهاية")
    reason = models.TextField("سبب الغياب")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING,
        verbose_name="الحالة",
    )
    rejection_reason = models.TextField("سبب الرفض", blank=True)
    substitute_teacher = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="substitute_absences", verbose_name="المعلم البديل",
        limit_choices_to={"role": User.Role.TEACHER},
    )
    processed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="processed_absences", verbose_name="تمت المعالجة بواسطة",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "طلب غياب"
        verbose_name_plural = "طلبات الغياب"

    def __str__(self):
        return f"{self.teacher.full_name_ar} — {self.start_date} إلى {self.end_date}"

    @property
    def duration_days(self):
        return (self.end_date - self.start_date).days + 1

    @property
    def circles(self):
        return self.teacher.teaching_circles.filter(status="active")

    @property
    def is_active_substitution(self):
        return self.status == self.Status.APPROVED and self.start_date <= date.today() <= self.end_date


class TeacherSubstitution(models.Model):
    absence = models.ForeignKey(
        TeacherAbsence, on_delete=models.CASCADE, related_name="substitutions",
        verbose_name="طلب الغياب",
    )
    circle = models.ForeignKey(
        "circles.Circle", on_delete=models.CASCADE, related_name="substitutions",
        verbose_name="الحلقة",
    )
    substitute_teacher = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="substitution_duties", verbose_name="المعلم البديل",
        limit_choices_to={"role": User.Role.TEACHER},
    )
    notes = models.TextField("ملاحظات", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "تعويض معلم"
        verbose_name_plural = "تعويضات المعلمين"
        unique_together = ("absence", "circle")

    def __str__(self):
        return f"{self.circle.name} ← {self.substitute_teacher.full_name_ar if self.substitute_teacher else '—'}"

    def get_status_display(self):
        return self.absence.get_status_display()


class SessionSubstitution(models.Model):
    substitution = models.ForeignKey(
        TeacherSubstitution, on_delete=models.CASCADE, related_name="session_substitutions",
        verbose_name="التعويض",
    )
    session = models.ForeignKey(
        "circles.Session", on_delete=models.CASCADE, related_name="substitutions",
        verbose_name="الحصة",
    )
    substitute_teacher = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="substituted_sessions", verbose_name="المعلم البديل",
        limit_choices_to={"role": User.Role.TEACHER},
    )
    status = models.CharField(
        max_length=20,
        choices=[("pending", "قيد الانتظار"), ("conducted", "تمت"), ("cancelled", "ملغاة")],
        default="pending", verbose_name="الحالة",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "تعويض حصة"
        verbose_name_plural = "تعويضات الحصص"

    def __str__(self):
        return f"{self.session} ← {self.substitute_teacher.full_name_ar if self.substitute_teacher else '—'}"


class PasswordResetCode(models.Model):
    email = models.EmailField()
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)

    class Meta:
        verbose_name = "رمز استعادة كلمة المرور"
        verbose_name_plural = "رموز استعادة كلمة المرور"

    def __str__(self):
        return f"{self.email} — {self.code}"

    @property
    def is_expired(self):
        return timezone.now() > self.created_at + timedelta(minutes=30)

    @staticmethod
    def generate_code():
        import secrets
        return f"{secrets.randbelow(1000000):06d}"

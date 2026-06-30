from datetime import date

from django.contrib.auth.models import AbstractUser
from django.db import models

from apps.core.models import UUIDModel, TimeStampedModel


class User(AbstractUser, UUIDModel, TimeStampedModel):

    class Role(models.TextChoices):
        ADMIN = "admin", "مشرف عام"
        SUPERVISOR = "supervisor", "مشرف"
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

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.full_name_ar} ({self.get_role_display()})"

    @property
    def is_active_approved(self):
        return self.is_active and self.is_approved == self.ApprovalStatus.APPROVED


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

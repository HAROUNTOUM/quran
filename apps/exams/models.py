import json
from datetime import date

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Exam(models.Model):

    class Status(models.TextChoices):
        DRAFT = "draft", "مسودة"
        PUBLISHED = "published", "منشور"
        GRADING = "grading", "جاري التصحيح"
        PENDING_APPROVAL = "pending_approval", "بانتظار الاعتماد"
        COMPLETED = "completed", "مكتمل"
        ARCHIVED = "archived", "مؤرشف"

    EXAM_TYPES = [
        ("monthly", "امتحان شهري"),
        ("quarterly", "امتحان فصلي"),
        ("final", "امتحان نهائي"),
        ("quiz", "اختبار قصير"),
        ("oral", "اختبار شفهي"),
    ]

    title = models.CharField(max_length=255, verbose_name="عنوان الامتحان")
    description = models.TextField(blank=True, verbose_name="الوصف")
    exam_type = models.CharField(
        max_length=30, choices=EXAM_TYPES, default="monthly", verbose_name="نوع الامتحان"
    )
    exam_code = models.CharField(
        max_length=50, unique=True, blank=True, verbose_name="رمز الامتحان"
    )
    circle = models.ForeignKey(
        "circles.Circle", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="exams", verbose_name="الحلقة",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="created_exams", verbose_name="المنشئ",
    )
    assigned_teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="assigned_exams", verbose_name="المعلم المسند",
        limit_choices_to={"role": "teacher"},
    )
    exam_date = models.DateField(default=date.today, verbose_name="تاريخ الامتحان")
    max_marks = models.FloatField(default=100, verbose_name="الدرجة القصوى")
    pass_percentage = models.FloatField(default=50, verbose_name="نسبة النجاح")
    status = models.CharField(
        max_length=30, choices=Status.choices, default=Status.DRAFT,
        verbose_name="الحالة",
    )
    auto_publish = models.BooleanField(default=False, verbose_name="نشر تلقائي")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-exam_date", "-created_at"]
        verbose_name = "امتحان"
        verbose_name_plural = "الامتحانات"

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.exam_code and not self.pk:
            prefix = "EX"
            date_str = self.exam_date.strftime("%Y%m%d")
            last_today = Exam.objects.filter(exam_date=self.exam_date).count()
            self.exam_code = f"{prefix}-{date_str}-{last_today + 1:04d}"
        super().save(*args, **kwargs)

    def student_count(self):
        return self.marks.count()

    def average_marks(self):
        agg = self.marks.aggregate(avg=models.Avg("marks_obtained"))
        return round(agg["avg"] or 0, 1)

    def pass_count(self):
        return self.marks.filter(is_passed=True).count()

    def fail_count(self):
        return self.marks.filter(is_passed=False).count()

    def approval_progress(self):
        counts = self.marks.values("status").annotate(cnt=models.Count("id"))
        result = {"approved": 0, "pending": 0, "rejected": 0, "total": 0}
        for c in counts:
            result[c["status"]] = c["cnt"]
        result["total"] = sum(result.values())
        return result


class ExamMark(models.Model):

    class Status(models.TextChoices):
        PENDING = "pending", "قيد الانتظار"
        APPROVED = "approved", "معتمد"
        REJECTED = "rejected", "مرفوض"

    exam = models.ForeignKey(
        Exam, on_delete=models.CASCADE, related_name="marks",
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="exam_marks",
    )
    marks_obtained = models.FloatField(
        validators=[MinValueValidator(0)],
        verbose_name="الدرجة المحصلة",
    )
    percentage = models.FloatField(verbose_name="النسبة المئوية", editable=False)
    grade = models.CharField(max_length=10, verbose_name="التقدير", editable=False)
    is_passed = models.BooleanField(verbose_name="ناجح", editable=False)
    teacher_notes = models.TextField(blank=True, verbose_name="ملاحظات المعلم")
    private_notes = models.TextField(blank=True, verbose_name="ملاحظات خاصة")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING,
        verbose_name="حالة الاعتماد",
    )
    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="entered_marks", verbose_name="مدخل الدرجة",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="approved_marks", verbose_name="معتمد بواسطة",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["exam", "student"]
        verbose_name = "درجة امتحان"
        verbose_name_plural = "درجات الامتحانات"

    def __str__(self):
        return f"{self.student.full_name_ar} — {self.exam.title}: {self.percentage}%"

    def save(self, *args, **kwargs):
        max_marks = self.exam.max_marks
        pass_pct = self.exam.pass_percentage
        self.percentage = round(
            (self.marks_obtained / max_marks) * 100, 2
        ) if max_marks > 0 else 0
        self.is_passed = self.percentage >= pass_pct
        self.grade = self._calculate_grade(self.percentage)
        super().save(*args, **kwargs)

    @staticmethod
    def _calculate_grade(percentage):
        if percentage >= 90:
            return "A"
        elif percentage >= 80:
            return "B"
        elif percentage >= 70:
            return "C"
        elif percentage >= 60:
            return "D"
        elif percentage >= 50:
            return "E"
        return "F"


class ExamNotification(models.Model):

    class Type(models.TextChoices):
        EXAM_PUBLISHED = "exam_published", "نشر امتحان"
        MARKS_ENTERED = "marks_entered", "إدخال درجات"
        SUBMITTED_FOR_APPROVAL = "submitted_approval", "تقديم للاعتماد"
        MARKS_APPROVED = "marks_approved", "اعتماد درجات"
        MARKS_REJECTED = "marks_rejected", "رفض درجات"
        REMINDER = "reminder", "تذكير"

    class SentVia(models.TextChoices):
        IN_APP = "in_app", "داخل التطبيق"
        EMAIL = "email", "بريد إلكتروني"
        BOTH = "both", "كلاهما"

    exam = models.ForeignKey(
        Exam, on_delete=models.CASCADE, related_name="notifications",
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="exam_notifications",
    )
    type = models.CharField(max_length=30, choices=Type.choices, verbose_name="النوع")
    sent_via = models.CharField(
        max_length=20, choices=SentVia.choices, default=SentVia.IN_APP,
        verbose_name="وسيلة الإرسال",
    )
    title = models.CharField(max_length=255, verbose_name="العنوان")
    message = models.TextField(verbose_name="الرسالة")
    link = models.CharField(max_length=500, blank=True, verbose_name="الرابط")
    is_read = models.BooleanField(default=False, verbose_name="مقروء")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "إشعار امتحان"
        verbose_name_plural = "إشعارات الامتحانات"

    def __str__(self):
        return f"{self.get_type_display()}: {self.title}"


class ExamApprovalHistory(models.Model):

    class Action(models.TextChoices):
        CREATED = "created", "إنشاء"
        PUBLISHED = "published", "نشر"
        MARKS_ENTERED = "marks_entered", "إدخال درجات"
        SUBMITTED = "submitted", "تقديم للاعتماد"
        APPROVED = "approved", "اعتماد"
        REJECTED = "rejected", "رفض"
        COMPLETED = "completed", "إكمال"
        ARCHIVED = "archived", "أرشفة"

    exam = models.ForeignKey(
        Exam, on_delete=models.CASCADE, related_name="approval_history",
    )
    action = models.CharField(
        max_length=30, choices=Action.choices, verbose_name="الإجراء",
    )
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="exam_actions", verbose_name="المنفذ",
    )
    reason = models.TextField(blank=True, verbose_name="السبب")
    marks_snapshot = models.JSONField(
        null=True, blank=True, verbose_name="لقطة الدرجات",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "سجل اعتماد امتحان"
        verbose_name_plural = "سجل اعتماد الامتحانات"

    def __str__(self):
        return f"{self.get_action_display()} — {self.exam.title}"

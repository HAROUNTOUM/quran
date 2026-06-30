from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from datetime import date
from django.utils import timezone


class ReviewRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "قيد الانتظار"
        APPROVED = "approved", "مقبول"
        REJECTED = "rejected", "مرفوض"

    class Type(models.TextChoices):
        REVIEW = "review", "طلب مراجعة"
        RECITATION = "recitation", "طلب تسميع"

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
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reviewed_requests",
    )
    rejection_reason = models.TextField("سبب الرفض", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "طلب مراجعة/تسميع"
        verbose_name_plural = "طلبات المراجعة والتسميع"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_type_display()} — {self.student.full_name_ar}"


class MemorizationProgress(models.Model):
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

    class Meta:
        verbose_name = 'تقدم حفظ/مراجعة'
        verbose_name_plural = 'تقدم الحفظ والمراجعة'

    def __str__(self):
        return f'{self.get_type_display()} — سورة {self.surah.name_ar} ({self.ayah_from}-{self.ayah_to})'


class ProgressLog(models.Model):
    class Category(models.TextChoices):
        HIFDH = "HIFDH", "تسميع جديد"
        MURAJAAH = "MURAJAAH", "مراجعة"

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
    teacher_notes = models.TextField("ملاحظات المعلم", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

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

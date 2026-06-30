from django.conf import settings
from django.db import models


class CertificateSeq(models.Model):
    date = models.DateField("التاريخ", unique=True)
    counter = models.PositiveIntegerField("العدد", default=0)

    class Meta:
        verbose_name = "تسلسل شهادات"
        verbose_name_plural = "تسلسل الشهادات"


class CertificateTemplate(models.Model):
    CATEGORY_CHOICES = [
        ("hifz", "شهادة حفظ"),
        ("murajaa", "شهادة مراجعة"),
        ("exam", "شهادة امتحان"),
        ("completion", "شهادة إتمام"),
        ("distinction", "شهادة تميز"),
    ]

    name = models.CharField("اسم القالب", max_length=255)
    category = models.CharField("الفئة", max_length=30, choices=CATEGORY_CHOICES)
    background_image = models.ImageField("صورة الخلفية", upload_to="certificate_templates/", blank=True)
    header_text = models.TextField("النص العلوي", default="بسم الله الرحمن الرحيم")
    body_template = models.TextField("قالب النص", help_text="استخدم {student_name}, {circle_name}, {date}, {details}")
    footer_text = models.TextField("النص السفلي", blank=True)
    is_active = models.BooleanField("مفعل", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["category", "name"]
        verbose_name = "قالب شهادة"
        verbose_name_plural = "قوالب الشهادات"

    def __str__(self):
        return self.name


class Certificate(models.Model):
    STATUS_CHOICES = [
        ("draft", "مسودة"),
        ("pending_upload", "بانتظار رفع الملف"),
        ("issued", "صادرة"),
        ("revoked", "ملغاة"),
    ]

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="certificates", verbose_name="الطالب",
        limit_choices_to={"role": "student"},
    )
    template = models.ForeignKey(
        CertificateTemplate, on_delete=models.PROTECT,
        related_name="certificates", verbose_name="القالب",
    )
    certificate_number = models.CharField("رقم الشهادة", max_length=50, unique=True)
    issue_date = models.DateField("تاريخ الإصدار", auto_now_add=True)
    status = models.CharField("الحالة", max_length=20, choices=STATUS_CHOICES, default="draft")
    details = models.TextField("تفاصيل", blank=True)
    pdf_file = models.FileField("ملف PDF", upload_to="certificates/", blank=True)
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="issued_certificates", verbose_name="صادر عن",
    )
    metadata = models.JSONField("بيانات إضافية", default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-issue_date"]
        verbose_name = "شهادة"
        verbose_name_plural = "الشهادات"

    def __str__(self):
        return f"{self.certificate_number} — {self.student.full_name_ar}"

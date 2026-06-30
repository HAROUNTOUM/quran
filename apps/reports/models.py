from django.conf import settings
from django.db import models


class SavedReport(models.Model):
    REPORT_TYPES = [
        ("attendance", "تقرير الحضور"),
        ("grades", "تقرير الدرجات"),
        ("hifz", "تقرير الحفظ"),
        ("murajaa", "تقرير المراجعة"),
        ("circles", "تقرير الحلقات"),
        ("teachers", "تقرير المعلمين"),
    ]

    FORMAT_CHOICES = [
        ("pdf", "PDF"),
        ("excel", "Excel"),
    ]

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="saved_reports", verbose_name="المنشئ",
    )
    title = models.CharField("عنوان التقرير", max_length=255)
    report_type = models.CharField("نوع التقرير", max_length=30, choices=REPORT_TYPES)
    circle = models.ForeignKey(
        "circles.Circle", on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="الحلقة",
    )
    format = models.CharField("الصيغة", max_length=10, choices=FORMAT_CHOICES, default="pdf")
    is_scheduled = models.BooleanField("مجددول", default=False)
    schedule_cron = models.CharField("جدولة (Cron)", max_length=100, blank=True)
    last_generated = models.DateTimeField("آخر توليد", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "تقرير محفوظ"
        verbose_name_plural = "التقارير المحفوظة"

    def __str__(self):
        return self.title

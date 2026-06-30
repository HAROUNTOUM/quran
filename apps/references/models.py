from django.db import models


class Surah(models.Model):
    class RevelationType(models.TextChoices):
        MAKKI = 'makki', 'مكية'
        MADANI = 'madani', 'مدنية'

    name_ar = models.CharField(max_length=100)
    name_en = models.CharField(max_length=100)
    ayah_count = models.IntegerField()
    revelation_type = models.CharField(max_length=10, choices=RevelationType.choices)

    class Meta:
        ordering = ['id']
        verbose_name = 'سورة'
        verbose_name_plural = 'السور'

    def __str__(self):
        return self.name_ar


class Juz(models.Model):
    number = models.IntegerField(unique=True, verbose_name="رقم الجزء")
    ayah_count = models.IntegerField(verbose_name="عدد الآيات")

    class Meta:
        ordering = ['number']
        verbose_name = 'جزء'
        verbose_name_plural = 'الأجزاء'

    def __str__(self):
        return f"الجزء {self.number}"

    def quarter_ayah_count(self):
        return self.ayah_count / 8


class EvaluationCriterion(models.Model):
    name_ar = models.CharField(max_length=100, verbose_name="اسم المعيار")
    weight = models.FloatField(default=1.0, verbose_name="الوزن")
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'معيار تقييم'
        verbose_name_plural = 'معايير التقييم'

    def __str__(self):
        return self.name_ar

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


class Hizb(models.Model):
    """One of the 60 ahzab. Two per juz."""
    number = models.IntegerField(unique=True, verbose_name="رقم الحزب")  # 1–60
    juz = models.ForeignKey(Juz, on_delete=models.CASCADE, related_name="hizbs")
    number_in_juz = models.IntegerField(verbose_name="ترتيبه في الجزء")  # 1–2

    class Meta:
        ordering = ["number"]
        verbose_name = "حزب"
        verbose_name_plural = "الأحزاب"

    def __str__(self):
        return f"الحزب {self.number}"


class Rub(models.Model):
    """Rub' al-hizb (ربع الحزب) — one of the 240 quarter-hizb divisions marked in
    the mushaf. This is the atomic memorization/review unit for the SRS engine."""
    number = models.IntegerField(unique=True, verbose_name="رقم الربع")  # 1–240
    hizb = models.ForeignKey(Hizb, on_delete=models.CASCADE, related_name="rubs")
    number_in_hizb = models.IntegerField(verbose_name="ترتيبه في الحزب")  # 1–4

    class Meta:
        ordering = ["number"]
        verbose_name = "ربع"
        verbose_name_plural = "الأرباع"

    def __str__(self):
        return f"الربع {self.number}"

    @property
    def juz(self):
        return self.hizb.juz

    def ayah_bounds(self):
        """(first_ayah, last_ayah) for this rub, or (None, None) if unseeded."""
        first = self.ayahs.order_by("surah_id", "number_in_surah").first()
        last = self.ayahs.order_by("surah_id", "number_in_surah").last()
        return first, last

    def label(self):
        """Human label like 'الربع 5 — البقرة 142-152'."""
        first, last = self.ayah_bounds()
        if not first:
            return f"الربع {self.number}"
        if first.surah_id == last.surah_id:
            span = f"{first.surah.name_ar} {first.number_in_surah}-{last.number_in_surah}"
        else:
            span = f"{first.surah.name_ar} {first.number_in_surah} — {last.surah.name_ar} {last.number_in_surah}"
        return f"الربع {self.number} — {span}"


class Thumn(models.Model):
    """Thumn al-hizb (ثُمن الحزب) — one of the 480 eighth-hizb divisions, per the
    Warsh mushaf. Finer than Rub (each rub = 2 thumns); stores the *start*
    boundary (page + first ayah) so selectors and progress views can show real
    mushaf positions instead of arithmetic estimates (L14)."""
    number = models.IntegerField(unique=True, verbose_name="رقم الثمن")  # 1–480
    rub = models.ForeignKey(Rub, on_delete=models.CASCADE, related_name="thumns")
    number_in_hizb = models.IntegerField(verbose_name="ترتيبه في الحزب")  # 1–8
    page = models.IntegerField(verbose_name="صفحة البداية")  # Warsh mushaf page
    start_surah = models.ForeignKey(
        Surah, on_delete=models.CASCADE, related_name="thumn_starts",
        verbose_name="سورة البداية",
    )
    start_ayah_number = models.IntegerField(verbose_name="آية البداية")
    ayah_id_global = models.IntegerField(
        unique=True, verbose_name="رقم الآية الكلي (ورش)",
        help_text="ترقيم متسلسل للآيات في مصحف ورش",
    )

    class Meta:
        ordering = ["number"]
        verbose_name = "ثمن"
        verbose_name_plural = "الأثمان"

    def __str__(self):
        return f"الثمن {self.number}"

    @property
    def hizb(self):
        return self.rub.hizb

    @property
    def juz(self):
        return self.rub.hizb.juz

    def label(self):
        """Human label like 'الثمن 5 — البقرة 43 (ص 7)'."""
        return (
            f"الثمن {self.number} — {self.start_surah.name_ar} "
            f"{self.start_ayah_number} (ص {self.page})"
        )


class Ayah(models.Model):
    """A single verse. Structural position (juz/hizb) is reached by traversal
    ayah.rub.hizb.juz — no denormalized numbers, single source of truth."""
    surah = models.ForeignKey(Surah, on_delete=models.CASCADE, related_name="ayahs")
    number_in_surah = models.IntegerField(verbose_name="رقم الآية في السورة")
    rub = models.ForeignKey(Rub, on_delete=models.CASCADE, related_name="ayahs")
    page = models.IntegerField(verbose_name="رقم الصفحة")  # 1–604 (Madani mushaf)
    text_uthmani = models.TextField(verbose_name="النص العثماني")
    text_normalized = models.TextField(
        verbose_name="النص المجرد", blank=True,
        help_text="نص بدون تشكيل للبحث",
    )
    sajdah = models.BooleanField(default=False, verbose_name="سجدة")

    class Meta:
        ordering = ["surah_id", "number_in_surah"]
        verbose_name = "آية"
        verbose_name_plural = "الآيات"
        constraints = [
            models.UniqueConstraint(
                fields=["surah", "number_in_surah"], name="uniq_ayah_surah_number"
            ),
        ]
        indexes = [
            models.Index(fields=["page"]),
            models.Index(fields=["rub"]),
        ]

    def __str__(self):
        return f"{self.surah.name_ar} {self.number_in_surah}"

    @property
    def verse_key(self):
        return f"{self.surah_id}:{self.number_in_surah}"


class EvaluationCriterion(models.Model):
    name_ar = models.CharField(max_length=100, verbose_name="اسم المعيار")
    weight = models.FloatField(default=1.0, verbose_name="الوزن")
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'معيار تقييم'
        verbose_name_plural = 'معايير التقييم'

    def __str__(self):
        return self.name_ar

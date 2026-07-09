from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase

from apps.references.models import Ayah, Hizb, Juz, Rub, Surah
from apps.references.utils import (
    normalize_arabic,
    rubs_in,
    validate_ayah_range,
)


class QuranNormalizeTest(TestCase):
    def test_strips_diacritics(self):
        self.assertEqual(normalize_arabic("بِسْمِ ٱللَّهِ"), "بسم الله")

    def test_folds_alef_variants(self):
        self.assertEqual(normalize_arabic("إنّ أحمد آمن"), "ان احمد امن")

    def test_empty(self):
        self.assertEqual(normalize_arabic(""), "")
        self.assertEqual(normalize_arabic(None), "")


class QuranHierarchySeedTest(TestCase):
    """Full seed from the static dataset, then assert structural invariants."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_quran")

    def test_counts(self):
        self.assertEqual(Surah.objects.count(), 114)
        self.assertEqual(Juz.objects.count(), 30)
        self.assertEqual(Hizb.objects.count(), 60)
        self.assertEqual(Rub.objects.count(), 240)
        self.assertEqual(Ayah.objects.count(), 6236)

    def test_each_rub_in_one_hizb_each_hizb_in_one_juz(self):
        self.assertEqual(Hizb.objects.filter(juz__isnull=True).count(), 0)
        self.assertEqual(Rub.objects.filter(hizb__isnull=True).count(), 0)
        # 4 rubs per hizb, 2 hizbs per juz
        for hizb in Hizb.objects.all():
            self.assertEqual(hizb.rubs.count(), 4)
        for juz in Juz.objects.all():
            self.assertEqual(juz.hizbs.count(), 2)

    def test_known_boundaries(self):
        # Authoritative: Juz 2 begins at Al-Baqarah 142
        a = Ayah.objects.get(surah_id=2, number_in_surah=142)
        self.assertEqual(a.rub.hizb.juz.number, 2)
        # Al-Fatiha 1 is juz 1 / hizb 1 / rub 1 / page 1
        f = Ayah.objects.get(surah_id=1, number_in_surah=1)
        self.assertEqual((f.rub.hizb.juz.number, f.rub.hizb.number, f.rub.number, f.page),
                         (1, 1, 1, 1))

    def test_pages_span_full_mushaf(self):
        pages = set(Ayah.objects.values_list("page", flat=True))
        self.assertEqual(min(pages), 1)
        self.assertEqual(max(pages), 604)

    def test_normalized_text_populated(self):
        self.assertFalse(Ayah.objects.filter(text_normalized="").exists())

    def test_rubs_in_juz(self):
        self.assertEqual(rubs_in(Juz.objects.get(number=1)).count(), 8)
        self.assertEqual(rubs_in(Hizb.objects.get(number=1)).count(), 4)

    def test_idempotent_reseed(self):
        call_command("seed_quran")
        self.assertEqual(Ayah.objects.count(), 6236)
        self.assertEqual(Rub.objects.count(), 240)


class ValidateAyahRangeTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.surah = Surah.objects.create(
            id=112, name_ar="الإخلاص", name_en="Al-Ikhlas",
            ayah_count=4, revelation_type="makki",
        )

    def test_valid_range(self):
        self.assertEqual(validate_ayah_range(self.surah, 1, 4), (1, 4))

    def test_accepts_pk(self):
        self.assertEqual(validate_ayah_range(112, 2, 3), (2, 3))

    def test_rejects_beyond_count(self):
        with self.assertRaises(ValidationError):
            validate_ayah_range(self.surah, 1, 5)

    def test_rejects_reversed(self):
        with self.assertRaises(ValidationError):
            validate_ayah_range(self.surah, 3, 1)

    def test_rejects_zero(self):
        with self.assertRaises(ValidationError):
            validate_ayah_range(self.surah, 0, 2)

    def test_rejects_non_numeric(self):
        with self.assertRaises(ValidationError):
            validate_ayah_range(self.surah, "x", 2)


class ThumnUnitHelpersTest(TestCase):
    """The platform tracking unit: thumn/hizb conversions resolved against the
    real Warsh thumn boundaries (not ayah-count arithmetic)."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_quran")
        call_command("seed_thumns")

    def test_whole_quran_is_480_thumns(self):
        from apps.references.utils import count_thumns
        ranges = [(s.id, 1, s.ayah_count) for s in Surah.objects.all()]
        self.assertEqual(count_thumns(ranges), 480)

    def test_fatiha_is_first_thumn(self):
        from apps.references.utils import thumn_span
        self.assertEqual(thumn_span(1, 1, 7), (1, 1))

    def test_overlapping_ranges_count_once(self):
        from apps.references.utils import count_thumns
        once = count_thumns([(2, 1, 100)])
        twice = count_thumns([(2, 1, 100), (2, 50, 100)])
        self.assertEqual(once, twice)

    def test_thumns_to_hizb(self):
        from apps.references.utils import thumns_to_hizb
        self.assertEqual(thumns_to_hizb(0), (0, 0))
        self.assertEqual(thumns_to_hizb(8), (1, 0))
        self.assertEqual(thumns_to_hizb(21), (2, 5))

    def test_format_hizb_thumn(self):
        from apps.references.utils import format_hizb_thumn
        self.assertEqual(format_hizb_thumn(0), "0")
        self.assertIn("حزب", format_hizb_thumn(8))
        label = format_hizb_thumn(9)
        self.assertIn("حزب", label)
        self.assertIn("ثمن", label)

    def test_fallback_estimate_without_thumn_data(self):
        from apps.references.models import Thumn
        from apps.references.utils import count_thumns
        Thumn.objects.all().delete()
        # ~130 ayahs ≈ 10 thumns by the 6236/480 estimate
        self.assertEqual(count_thumns([(2, 1, 130)]), 10)

    def test_ayah_range_bounds(self):
        from apps.references.utils import ayah_range_bounds
        bounds = ayah_range_bounds([(2, 5, 100), (1, 1, 7), (3, 1, 50)])
        self.assertEqual(bounds, ((1, 1), (3, 50)))

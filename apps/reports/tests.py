from datetime import date

from django.core.management import call_command
from django.test import TestCase

from apps.accounts.models import User
from apps.circles.models import Circle, CircleEnrollment, Session
from apps.memorization.models import MemorizationProgress, ProgressLog
from apps.references.models import Surah


def _csv_rows(response):
    """Parse the streamed CSV into a list of cell lists (header first).
    CSVRenderer replaces in-cell commas with Arabic commas, so a plain
    split is unambiguous."""
    body = b"".join(response.streaming_content).decode("utf-8-sig")
    return [line.split(",") for line in body.strip().split("\n")]


class ProgressCategoryExportTest(TestCase):
    """hifz/murajaa CSV exports must read the canonical ProgressLog — the
    table session reports and StudentAchievement are built from — never the
    deprecated MemorizationProgress tracker."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_quran")
        call_command("seed_thumns")
        cls.teacher = User.objects.create_user(
            username="t@test.com", email="t@test.com", password="x",
            full_name_ar="معلم", role=User.Role.TEACHER,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        cls.other_teacher = User.objects.create_user(
            username="t2@test.com", email="t2@test.com", password="x",
            full_name_ar="معلم آخر", role=User.Role.TEACHER,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        cls.staff = User.objects.create_user(
            username="a@test.com", email="a@test.com", password="x",
            full_name_ar="مدير", role=User.Role.MAIN_ADMIN,
            is_approved=User.ApprovalStatus.APPROVED, is_staff=True,
        )
        cls.student = User.objects.create_user(
            username="s@test.com", email="s@test.com", password="x",
            full_name_ar="طالب الحفظ", role=User.Role.STUDENT,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        cls.circle = Circle.objects.create(
            name="حلقة", teacher=cls.teacher, status=Circle.Status.ACTIVE,
        )
        cls.enrollment = CircleEnrollment.objects.create(
            circle=cls.circle, student=cls.student,
            status=CircleEnrollment.Status.ACTIVE,
        )
        cls.session = Session.objects.create(
            circle=cls.circle, session_date=date.today(),
        )
        cls.baqara = Surah.objects.get(pk=2)
        cls.hifdh_log = ProgressLog.objects.create(
            session=cls.session, student=cls.student,
            log_category=ProgressLog.Category.HIFDH,
            surah=cls.baqara, start_ayah=1, end_ayah=25, points=18,
            evaluation_grade="ممتاز",
        )
        cls.murajaah_log = ProgressLog.objects.create(
            session=cls.session, student=cls.student,
            log_category=ProgressLog.Category.MURAJAAH,
            surah=cls.baqara, start_ayah=26, end_ayah=50, points=15,
        )
        # A legacy row that must NOT feed the exports.
        MemorizationProgress.objects.create(
            enrollment=cls.enrollment, type=MemorizationProgress.Type.HIFZ,
            surah=cls.baqara, ayah_from=200, ayah_to=286,
        )

    def _export(self, report_type, login_as="a@test.com", **params):
        self.client.login(username=login_as, password="x")
        return self.client.get(
            "/dashboard/reports/csv/", {"type": report_type, **params}
        )

    def _export_rows(self, report_type, login_as="a@test.com", **params):
        resp = self._export(report_type, login_as=login_as, **params)
        self.assertEqual(resp.status_code, 200)
        return _csv_rows(resp)

    # Columns: 0 student, 1 from-surah, 2 from-ayah, 3 to-surah, 4 to-ayah,
    # 5 thumn span, 6 hizb/thumn amount, 7 points, 8 grade, 9 circle, 10 date

    def test_hifz_export_reads_progress_log(self):
        rows = self._export_rows("hifz")
        self.assertEqual(len(rows), 2)  # header + the one HIFDH log only
        row = rows[1]
        self.assertEqual(row[0], "طالب الحفظ")
        self.assertEqual((row[2], row[4]), ("1", "25"))
        self.assertEqual(row[7], "18.0")
        self.assertEqual(row[8], "ممتاز")
        self.assertEqual(row[9], "حلقة")
        # legacy MemorizationProgress range (200-286) must not leak in
        self.assertNotIn("200", [c for r in rows for c in r])

    def test_murajaa_export_reads_progress_log(self):
        rows = self._export_rows("murajaa")
        self.assertEqual(len(rows), 2)
        row = rows[1]
        self.assertEqual((row[2], row[4]), ("26", "50"))
        self.assertEqual(row[7], "15.0")
        self.assertNotIn("200", [c for r in rows for c in r])

    def test_thumn_columns_populated_from_seeded_boundaries(self):
        row = self._export_rows("hifz")[1]
        self.assertNotEqual(row[5], "")  # thumn span
        self.assertNotEqual(row[6], "")  # hizb/thumn amount

    def test_non_staff_teacher_scoped_to_own_circles(self):
        rows = self._export_rows("hifz", login_as="t2@test.com")
        self.assertEqual(len(rows), 1)  # header only
        own = self._export_rows("hifz", login_as="t@test.com")
        self.assertEqual(len(own), 2)

    def test_end_date_includes_rows_created_that_day(self):
        # created_at is a datetime after midnight; a date-picker end=today
        # must still include today's logs (regression: created_at__lte lost them).
        today = date.today().isoformat()
        rows = self._export_rows("hifz", start=today, end=today)
        self.assertEqual(len(rows), 2)

    def test_malformed_date_returns_400(self):
        self.assertEqual(self._export("hifz", end="not-a-date").status_code, 400)
        self.assertEqual(self._export("hifz", start="2026-02-30").status_code, 400)

    def test_unknown_type_returns_400_and_empty_defaults_to_attendance(self):
        self.assertEqual(self._export("bogus").status_code, 400)
        resp = self._export("")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("attendance.csv", resp["Content-Disposition"])

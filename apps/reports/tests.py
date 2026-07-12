from datetime import date

from django.core.management import call_command
from django.test import TestCase

from apps.accounts.models import User
from apps.circles.models import Circle, CircleEnrollment, Session
from apps.memorization.models import MemorizationProgress, ProgressLog
from apps.references.models import Surah


def _csv_body(response):
    return b"".join(response.streaming_content).decode("utf-8-sig")


class ProgressCategoryExportTest(TestCase):
    """hifz/murajaa CSV exports must read the canonical ProgressLog — the same
    table session reports and StudentAchievement are built from — not the
    deprecated, writer-less MemorizationProgress table."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_quran")
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
        )
        cls.murajaah_log = ProgressLog.objects.create(
            session=cls.session, student=cls.student,
            log_category=ProgressLog.Category.MURAJAAH,
            surah=cls.baqara, start_ayah=26, end_ayah=50, points=15,
        )
        # A legacy row that must NOT feed the exports anymore.
        MemorizationProgress.objects.create(
            enrollment=cls.enrollment, type=MemorizationProgress.Type.HIFZ,
            surah=cls.baqara, ayah_from=200, ayah_to=286,
        )

    def _export(self, report_type, login_as="a@test.com"):
        self.client.login(username=login_as, password="x")
        resp = self.client.get("/dashboard/reports/csv/", {"type": report_type})
        self.assertEqual(resp.status_code, 200)
        return _csv_body(resp)

    def test_hifz_export_reads_progress_log(self):
        body = self._export("hifz")
        self.assertIn("طالب الحفظ", body)
        self.assertIn("18", body)          # points /20 from the HIFDH log
        self.assertNotIn("200", body)      # legacy MemorizationProgress row excluded

    def test_hifz_export_excludes_other_categories(self):
        body = self._export("hifz")
        self.assertNotIn("15.0", body)  # murajaah log's points absent

    def test_murajaa_export_reads_progress_log(self):
        body = self._export("murajaa")
        self.assertIn("طالب الحفظ", body)
        self.assertIn("26", body)
        self.assertNotIn("200", body)

    def test_non_staff_teacher_scoped_to_own_circles(self):
        body = self._export("hifz", login_as="t2@test.com")
        self.assertNotIn("طالب الحفظ", body)
        own = self._export("hifz", login_as="t@test.com")
        self.assertIn("طالب الحفظ", own)

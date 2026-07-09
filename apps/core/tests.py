"""Tests for cross-cutting middleware (HAF-05 feature-flag enforcement)
and the settings UI (HAF-06)."""
from django.test import TestCase, Client

from apps.accounts.models import User
from apps.usersettings.models import SystemSettings, UserSettings


class FeatureFlagMiddlewareTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username="a@test.com", email="a@test.com", password="x",
            full_name_ar="مشرف", role=User.Role.MAIN_ADMIN,
            is_approved=User.ApprovalStatus.APPROVED, is_staff=True,
        )
        cls.student = User.objects.create_user(
            username="s@test.com", email="s@test.com", password="x",
            full_name_ar="طالب", role=User.Role.STUDENT,
            is_approved=User.ApprovalStatus.APPROVED,
        )

    def _disable(self, feature):
        store = SystemSettings.load()
        store.data[f"feature_{feature}_enabled"] = False
        store.save(update_fields=["data"])

    def test_disabled_module_redirects_non_admin(self):
        self._disable("exams")
        c = Client()
        c.force_login(self.student)
        resp = c.get("/dashboard/student/exams/")
        self.assertEqual(resp.status_code, 302)  # bounced to dashboard

    def test_admin_bypasses_disabled_module(self):
        self._disable("exams")
        c = Client()
        c.force_login(self.admin)
        resp = c.get("/dashboard/exams/")
        # Admin is never blocked by the flag (may 200 or hit its own redirects,
        # but never the feature-flag bounce to the dashboard root).
        self.assertNotEqual(resp.get("Location", ""), "/dashboard/")

    def test_enabled_module_is_reachable(self):
        # exams enabled by default → student results page is not flag-blocked
        c = Client()
        c.force_login(self.student)
        resp = c.get("/dashboard/student/exams/")
        self.assertNotEqual(
            (resp.status_code, resp.get("Location", "")), (302, "/dashboard/")
        )


class SettingsUITest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username="a@test.com", email="a@test.com", password="x",
            full_name_ar="مشرف", role=User.Role.MAIN_ADMIN,
            is_approved=User.ApprovalStatus.APPROVED, is_staff=True,
        )
        cls.student = User.objects.create_user(
            username="s@test.com", email="s@test.com", password="x",
            full_name_ar="طالب", role=User.Role.STUDENT,
            is_approved=User.ApprovalStatus.APPROVED,
        )

    def test_student_can_save_own_setting(self):
        c = Client()
        c.force_login(self.student)
        resp = c.post("/dashboard/settings/", {
            "scope": "user",
            "email_digest_frequency": "daily",
            # notify_channel_inapp checkbox omitted -> becomes False
        })
        self.assertEqual(resp.status_code, 302)
        us = UserSettings.objects.get(user=self.student)
        self.assertEqual(us.get("email_digest_frequency"), "daily")
        self.assertFalse(us.get("notify_channel_inapp"))

    def test_student_cannot_write_system_scope(self):
        c = Client()
        c.force_login(self.student)
        c.post("/dashboard/settings/", {"scope": "system", "maintenance_mode": "on"})
        # unchanged — students may not touch system settings
        self.assertFalse(SystemSettings.load().get("maintenance_mode"))

    def test_admin_saves_system_setting_and_audits(self):
        from apps.usersettings.models import SettingsChangeHistory
        c = Client()
        c.force_login(self.admin)
        resp = c.post("/dashboard/settings/", {
            "scope": "system",
            "feature_exams_enabled": "on",
            "max_students_per_teacher": "42",
            "grade_calculation_method": "simple_average",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(SystemSettings.load().get("max_students_per_teacher"), 42)
        self.assertTrue(SettingsChangeHistory.objects.filter(key="max_students_per_teacher").exists())

    def test_invalid_int_is_rejected(self):
        c = Client()
        c.force_login(self.admin)
        c.post("/dashboard/settings/", {
            "scope": "system", "max_students_per_teacher": "9999",  # > max 200
        })
        self.assertNotEqual(SystemSettings.load().get("max_students_per_teacher"), 9999)


class SessionIdleTimeoutTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.student = User.objects.create_user(
            username="s@test.com", email="s@test.com", password="x",
            full_name_ar="طالب", role=User.Role.STUDENT,
            is_approved=User.ApprovalStatus.APPROVED,
        )

    def test_idle_session_is_logged_out(self):
        import time
        c = Client()
        c.force_login(self.student)
        # First request seeds _last_activity
        c.get("/dashboard/")
        # Backdate activity well beyond the timeout window
        session = c.session
        session["_last_activity"] = int(time.time()) - 60 * 60 * 24
        session.save()
        resp = c.get("/dashboard/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp.get("Location", ""))

    def test_active_session_survives(self):
        c = Client()
        c.force_login(self.student)
        c.get("/dashboard/")
        resp = c.get("/dashboard/")
        # not bounced to login
        self.assertNotIn("/login/", resp.get("Location", ""))


class UIRenderSmokeTest(TestCase):
    """UI-consolidation render smoke (Step 2): the request-workspace pages and
    their shared tab bar render without template errors for a student."""

    @classmethod
    def setUpTestData(cls):
        cls.student = User.objects.create_user(
            username="s@test.com", email="s@test.com", password="x",
            full_name_ar="طالب", role=User.Role.STUDENT,
            is_approved=User.ApprovalStatus.APPROVED,
        )

    def setUp(self):
        self.c = Client()
        self.c.force_login(self.student)

    def test_requests_workspace_pages_render(self):
        for url in ("/dashboard/student/requests/",
                    "/dashboard/student/review-requests/"):
            resp = self.c.get(url)
            self.assertEqual(resp.status_code, 200, url)
            # shared workspace tabs present
            self.assertContains(resp, "أسئلة المعلم")
            self.assertContains(resp, "الدعم والبلاغات")

    def test_workspace_pages_render_with_tabs(self):
        # Every consolidated student workspace page renders (empty data) and
        # carries its workspace tab bar, and the trimmed sidebar renders.
        for url in ("/dashboard/",
                    "/dashboard/progress/", "/dashboard/estimator/",
                    "/dashboard/student/memorization/", "/dashboard/student/tasks/",
                    "/dashboard/student/stats/", "/dashboard/student/attendance/",
                    "/dashboard/student/justifications/"):
            resp = self.c.get(url)
            self.assertIn(resp.status_code, (200, 302), url)
            if resp.status_code == 200:
                # trimmed sidebar workspace entry present
                self.assertContains(resp, "الحفظ والحضور")


class TeacherWorkspaceRenderTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.teacher = User.objects.create_user(
            username="t@test.com", email="t@test.com", password="x",
            full_name_ar="معلم", role=User.Role.TEACHER,
            is_approved=User.ApprovalStatus.APPROVED,
        )

    def test_teacher_request_workspace_and_trimmed_sidebar_render(self):
        c = Client()
        c.force_login(self.teacher)
        for url in ("/dashboard/teacher/review-requests/",
                    "/dashboard/teacher/reschedule-requests/",
                    "/dashboard/teacher/requests/"):
            resp = c.get(url)
            self.assertEqual(resp.status_code, 200, url)
            self.assertContains(resp, "تعديل المواعيد")  # shared tab bar
            self.assertContains(resp, "الدعم والبلاغات")

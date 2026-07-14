from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.accounts.models import User
from apps.usersettings import registry
from apps.usersettings.models import (
    SettingsChangeHistory, SystemSettings, UserSettings,
)
from apps.usersettings.services import get_system_setting, get_user_setting


def make_user(role, i=0):
    return User.objects.create_user(
        username=f"{role}{i}@test.tld", email=f"{role}{i}@test.tld",
        password="x", role=role, full_name_ar=f"{role} {i}",
    )


class RegistryTests(TestCase):
    def test_unknown_key_rejected(self):
        with self.assertRaises(ValidationError):
            registry.get_spec("nope")

    def test_bool_coercion(self):
        spec = registry.get_spec("auto_recording")
        self.assertIs(registry.clean_value(spec, "true"), True)
        self.assertIs(registry.clean_value(spec, "off"), False)
        with self.assertRaises(ValidationError):
            registry.clean_value(spec, "maybe")

    def test_int_range(self):
        spec = registry.get_spec("max_participants")
        self.assertEqual(registry.clean_value(spec, "50"), 50)
        with self.assertRaises(ValidationError):
            registry.clean_value(spec, 0)
        with self.assertRaises(ValidationError):
            registry.clean_value(spec, 999)

    def test_choice(self):
        spec = registry.get_spec("email_digest_frequency")
        self.assertEqual(registry.clean_value(spec, "daily"), "daily")
        with self.assertRaises(ValidationError):
            registry.clean_value(spec, "hourly")

    def test_date(self):
        spec = registry.get_spec("academic_term_start")
        self.assertEqual(registry.clean_value(spec, "2026-09-01"), "2026-09-01")
        self.assertIsNone(registry.clean_value(spec, ""))
        with self.assertRaises(ValidationError):
            registry.clean_value(spec, "not-a-date")

    def test_role_scoping(self):
        teacher_keys = {s.key for s in registry.specs_for_role("teacher")}
        student_keys = {s.key for s in registry.specs_for_role("student")}
        self.assertIn("default_grading_scale", teacher_keys)
        self.assertNotIn("default_grading_scale", student_keys)
        self.assertIn("notify_channel_inapp", student_keys)
        # system scope only reachable by admin
        self.assertEqual(registry.specs_for_role("teacher", registry.SYSTEM_SCOPE), [])
        admin_sys = {s.key for s in registry.specs_for_role("admin", registry.SYSTEM_SCOPE)}
        self.assertIn("maintenance_mode", admin_sys)


class UserSettingsTests(TestCase):
    def setUp(self):
        self.teacher = make_user("teacher")
        self.student = make_user("student")
        self.admin = make_user("admin")

    def test_signal_autocreates_settings(self):
        self.assertTrue(UserSettings.objects.filter(user=self.teacher).exists())

    def test_set_validates_and_logs(self):
        us = self.teacher.settings
        us.set("max_participants", "25", changed_by=self.teacher)
        self.assertEqual(us.get("max_participants"), 25)
        row = SettingsChangeHistory.objects.get(user=self.teacher, key="max_participants")
        self.assertEqual(row.old_value, 30)
        self.assertEqual(row.new_value, 25)
        self.assertFalse(row.is_critical)

    def test_noop_write_skips_history(self):
        us = self.teacher.settings
        us.set("max_participants", 30, changed_by=self.teacher)  # equals default
        self.assertFalse(SettingsChangeHistory.objects.filter(key="max_participants").exists())

    def test_wrong_role_rejected(self):
        with self.assertRaises(ValidationError):
            self.student.settings.set("max_participants", 10, changed_by=self.student)

    def test_system_key_rejected_on_user_store(self):
        with self.assertRaises(ValidationError):
            self.admin.settings.set("maintenance_mode", True, changed_by=self.admin)

    def test_as_dict_merges_defaults(self):
        us = self.student.settings
        us.set("email_digest_frequency", "daily", changed_by=self.student)
        effective = us.as_dict()
        self.assertEqual(effective["email_digest_frequency"], "daily")
        self.assertEqual(effective["notify_channel_inapp"], True)  # untouched default
        self.assertNotIn("max_participants", effective)  # teacher-only key hidden

    def test_reset_to_defaults_logs(self):
        us = self.teacher.settings
        us.set("auto_recording", True, changed_by=self.teacher)
        us.reset_to_defaults(changed_by=self.admin)
        self.assertEqual(us.get("auto_recording"), False)
        self.assertEqual(
            SettingsChangeHistory.objects.filter(user=self.teacher, key="auto_recording").count(),
            2,  # the set + the reset
        )

    def test_bulk_push(self):
        t2 = make_user("teacher", 2)
        updated = UserSettings.bulk_push("teacher", "require_attendance_confirmation", False, changed_by=self.admin)
        self.assertEqual(updated, 2)
        for teacher in (self.teacher, t2):  # re-fetch: bulk_push wrote via fresh instances
            fresh = UserSettings.objects.get(user=teacher)
            self.assertEqual(fresh.get("require_attendance_confirmation"), False)
        self.assertEqual(
            SettingsChangeHistory.objects.filter(key="require_attendance_confirmation").count(), 2,
        )
        with self.assertRaises(ValidationError):
            UserSettings.bulk_push("student", "max_participants", 10, changed_by=self.admin)


class SystemSettingsTests(TestCase):
    def setUp(self):
        self.admin = make_user("admin")
        self.teacher = make_user("teacher")

    def test_defaults_via_service(self):
        self.assertEqual(get_system_setting("request_overdue_days"), 3)
        self.assertFalse(get_system_setting("maintenance_mode"))

    def test_admin_set_and_history(self):
        store = SystemSettings.load()
        store.set("maintenance_mode", "true", changed_by=self.admin)
        self.assertTrue(get_system_setting("maintenance_mode"))
        row = SettingsChangeHistory.objects.get(key="maintenance_mode")
        self.assertIsNone(row.user)
        self.assertTrue(row.is_critical)
        self.assertEqual(row.changed_by, self.admin)

    def test_non_admin_rejected(self):
        store = SystemSettings.load()
        with self.assertRaises(ValidationError):
            store.set("maintenance_mode", True, changed_by=self.teacher)

    def test_get_user_setting_service(self):
        self.assertEqual(get_user_setting(self.teacher, "default_grading_scale"), "out_of_20")
        self.teacher.settings.set("default_grading_scale", "percent", changed_by=self.teacher)
        self.teacher.refresh_from_db()
        self.assertEqual(get_user_setting(self.teacher, "default_grading_scale"), "percent")


class SettingsGmailCardTests(TestCase):
    """The الإعدادات page offers the Google connection to admins/sub-admins."""

    def test_sub_admin_sees_google_connect_card(self):
        from django.urls import reverse
        from apps.accounts.models import User
        sub = User.objects.create_user(
            username="set_sub@test.com", email="set_sub@test.com", password="x",
            full_name_ar="مشرف", role=User.Role.SUB_ADMIN,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        self.client.force_login(sub)
        r = self.client.get(reverse("usersettings:home"))
        self.assertContains(r, "الحسابات المرتبطة")

    def test_student_does_not_see_google_card(self):
        from django.urls import reverse
        from apps.accounts.models import User
        student = User.objects.create_user(
            username="set_st@test.com", email="set_st@test.com", password="x",
            full_name_ar="طالب", role=User.Role.STUDENT,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        self.client.force_login(student)
        r = self.client.get(reverse("usersettings:home"))
        self.assertNotContains(r, "الحسابات المرتبطة")

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.circles.models import Circle, CircleEnrollment
from apps.emailcenter import services
from apps.emailcenter.models import Audience, EmailCampaign, EmailCategory, EmailLog
from apps.usersettings.models import SystemSettings


def _user(email, role, name):
    return User.objects.create_user(
        username=email, email=email, password="x",
        full_name_ar=name, role=role,
        is_approved=User.ApprovalStatus.APPROVED,
    )


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class DeliveryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = _user("a@t.com", User.Role.MAIN_ADMIN, "الأدمن")
        cls.student = _user("s@t.com", User.Role.STUDENT, "الطالب")

    def setUp(self):
        mail.outbox = []

    def test_broadcast_sends_and_logs(self):
        sent, failed, skipped = services.deliver(
            EmailCategory.BROADCAST, "عنوان", "emails/broadcast.html",
            {"subject": "عنوان", "body": "متن", "site_name": "الطبيب الحافظ"},
            [self.admin, self.student],
        )
        self.assertEqual((sent, failed, skipped), (2, 0, 0))
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(EmailLog.objects.filter(status="sent").count(), 2)

    def test_gated_category_skips_when_disabled(self):
        SystemSettings.load().set("automail_approvals", False, changed_by=self.admin)
        sent, failed, skipped = services.deliver(
            EmailCategory.APPROVAL, "اعتماد", "emails/broadcast.html",
            {"subject": "x", "body": "y", "site_name": "z"}, [self.student],
        )
        self.assertEqual((sent, failed, skipped), (0, 0, 1))
        self.assertEqual(len(mail.outbox), 0)
        self.assertTrue(EmailLog.objects.filter(status="skipped").exists())

    def test_master_switch_disables_all_auto_mail(self):
        SystemSettings.load().set("automail_enabled", False, changed_by=self.admin)
        sent, _f, skipped = services.deliver(
            EmailCategory.CERTIFICATE, "شهادة", "emails/broadcast.html",
            {"subject": "x", "body": "y", "site_name": "z"}, [self.student],
        )
        self.assertEqual((sent, skipped), (0, 1))

    def test_broadcast_ignores_toggles(self):
        SystemSettings.load().set("automail_enabled", False, changed_by=self.admin)
        sent, _f, _s = services.deliver(
            EmailCategory.BROADCAST, "x", "emails/broadcast.html",
            {"subject": "x", "body": "y", "site_name": "z"}, [self.student],
        )
        self.assertEqual(sent, 1)


class RecipientResolutionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = _user("a@t.com", User.Role.MAIN_ADMIN, "الأدمن")
        cls.teacher = _user("t@t.com", User.Role.TEACHER, "الأستاذ")
        cls.s1 = _user("s1@t.com", User.Role.STUDENT, "طالب ١")
        cls.s2 = _user("s2@t.com", User.Role.STUDENT, "طالب ٢")
        cls.circle = Circle.objects.create(name="حلقة", teacher=cls.teacher)
        CircleEnrollment.objects.create(
            circle=cls.circle, student=cls.s1,
            status=CircleEnrollment.Status.ACTIVE,
        )

    def _campaign(self, **kw):
        return EmailCampaign(subject="s", body="b", created_by=self.admin, **kw)

    def test_all_audience(self):
        emails = set(services.resolve_recipients(
            self._campaign(audience=Audience.ALL)).values_list("email", flat=True))
        self.assertEqual(len(emails), 4)

    def test_role_audience(self):
        c = self._campaign(audience=Audience.ROLE, audience_role=User.Role.STUDENT)
        emails = set(services.resolve_recipients(c).values_list("email", flat=True))
        self.assertEqual(emails, {"s1@t.com", "s2@t.com"})

    def test_circle_audience_active_only(self):
        c = self._campaign(audience=Audience.CIRCLE, audience_circle=self.circle)
        emails = set(services.resolve_recipients(c).values_list("email", flat=True))
        self.assertEqual(emails, {"s1@t.com"})

    def test_excludes_users_without_email(self):
        self.s2.email = ""
        self.s2.save(update_fields=["email"])
        c = self._campaign(audience=Audience.ROLE, audience_role=User.Role.STUDENT)
        emails = set(services.resolve_recipients(c).values_list("email", flat=True))
        self.assertEqual(emails, {"s1@t.com"})


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class CampaignViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = _user("a@t.com", User.Role.MAIN_ADMIN, "الأدمن")
        cls.supervisor = _user("sup@t.com", User.Role.SUB_ADMIN, "مشرف")
        cls.student = _user("s@t.com", User.Role.STUDENT, "الطالب")

    def setUp(self):
        mail.outbox = []

    def test_compose_requires_admin(self):
        self.client.force_login(self.supervisor)
        self.assertEqual(self.client.get(reverse("emailcenter:compose")).status_code, 403)

    def test_compose_sends_campaign_inline(self):
        self.client.force_login(self.admin)
        resp = self.client.post(reverse("emailcenter:compose"), {
            "subject": "مرحبا", "body": "نص الرسالة", "audience": Audience.ALL,
        })
        self.assertRedirects(resp, reverse("emailcenter:campaigns"))
        campaign = EmailCampaign.objects.get()
        self.assertEqual(campaign.status, EmailCampaign.Status.SENT)
        self.assertEqual(campaign.sent_count, 3)
        self.assertEqual(len(mail.outbox), 3)

    def test_controls_persist_toggles(self):
        self.client.force_login(self.admin)
        # No checkboxes submitted -> everything off.
        resp = self.client.post(reverse("emailcenter:controls"), {})
        self.assertRedirects(resp, reverse("emailcenter:controls"))
        store = SystemSettings.load()
        self.assertFalse(store.get("automail_enabled"))
        self.assertFalse(store.get("automail_reminders"))

    def test_controls_enable_selected(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("emailcenter:controls"), {
            "automail_enabled": "on", "automail_approvals": "on",
        })
        store = SystemSettings.load()
        self.assertTrue(store.get("automail_enabled"))
        self.assertTrue(store.get("automail_approvals"))
        self.assertFalse(store.get("automail_updates"))

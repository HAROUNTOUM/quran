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

    def test_compose_sends_campaign(self):
        # queue_campaign sends on a daemon thread; run it inline so the
        # assertions below are deterministic (no worker needed in prod).
        from unittest.mock import patch

        class InlineThread:
            def __init__(self, target=None, daemon=None):
                self._target = target
            def start(self):
                self._target()

        self.client.force_login(self.admin)
        with patch("apps.emailcenter.services.threading.Thread", InlineThread):
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


class GmailSenderTests(TestCase):
    """Admins/sub-admins connect their Gmail via OAuth; campaigns can send
    through it as the from-address."""

    def setUp(self):
        from apps.accounts.models import User
        self.admin = User.objects.create_user(
            username="gm_admin@test.com", email="gm_admin@test.com", password="x",
            full_name_ar="مدير", role=User.Role.MAIN_ADMIN,
            is_approved=User.ApprovalStatus.APPROVED, is_staff=True,
        )
        self.sub = User.objects.create_user(
            username="gm_sub@test.com", email="gm_sub@test.com", password="x",
            full_name_ar="مشرف", role=User.Role.SUB_ADMIN,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        self.student = User.objects.create_user(
            username="gm_st@test.com", email="gm_st@test.com", password="x",
            full_name_ar="طالب", role=User.Role.STUDENT,
            is_approved=User.ApprovalStatus.APPROVED,
        )

    def test_refresh_token_signing_roundtrip(self):
        from apps.emailcenter.models import GmailAccount
        acc = GmailAccount(user=self.admin, email="a@gmail.com")
        acc.set_refresh_token("1//secret-token")
        acc.save()
        acc.refresh_from_db()
        self.assertEqual(acc.get_refresh_token(), "1//secret-token")
        self.assertNotIn("secret-token", acc.refresh_token_signed.split(":")[0])

    def test_students_cannot_access_gmail_pages(self):
        self.client.force_login(self.student)
        r = self.client.get(reverse("emailcenter:gmail_settings"))
        self.assertEqual(r.status_code, 403)

    def test_sub_admin_can_open_settings_and_connect_redirects_to_google(self):
        from unittest.mock import patch
        self.client.force_login(self.sub)
        self.assertEqual(self.client.get(reverse("emailcenter:gmail_settings")).status_code, 200)
        with patch("django.conf.settings.GOOGLE_OAUTH_CLIENT_ID", "cid"), \
             patch("django.conf.settings.GOOGLE_OAUTH_CLIENT_SECRET", "sec"):
            r = self.client.get(reverse("emailcenter:gmail_connect"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("accounts.google.com", r["Location"])
        self.assertIn("gmail.send", r["Location"])

    def test_callback_creates_account(self):
        from unittest.mock import patch
        from apps.emailcenter import gmail as gmail_svc
        from apps.emailcenter.models import GmailAccount
        self.client.force_login(self.sub)
        session = self.client.session
        session[gmail_svc.STATE_SESSION_KEY] = "st4te"
        session.save()
        with patch.object(gmail_svc, "exchange_code", return_value={
                "access_token": "at", "refresh_token": "rt", "expires_in": 3600}), \
             patch.object(gmail_svc, "fetch_email", return_value="sub@gmail.com"):
            r = self.client.get(
                reverse("emailcenter:gmail_callback"), {"code": "c0de", "state": "st4te"}
            )
        self.assertEqual(r.status_code, 302)
        acc = GmailAccount.objects.get(user=self.sub)
        self.assertEqual(acc.email, "sub@gmail.com")
        self.assertEqual(acc.get_refresh_token(), "rt")

    def test_callback_rejects_bad_state(self):
        from apps.emailcenter.models import GmailAccount
        self.client.force_login(self.sub)
        r = self.client.get(reverse("emailcenter:gmail_callback"), {"code": "x", "state": "wrong"})
        self.assertEqual(r.status_code, 302)
        self.assertFalse(GmailAccount.objects.exists())

    def test_campaign_sends_via_connected_gmail(self):
        from unittest.mock import patch
        from apps.emailcenter import services
        from apps.emailcenter.models import EmailCampaign, EmailLog, GmailAccount, Audience
        acc = GmailAccount(user=self.admin, email="a@gmail.com")
        acc.set_refresh_token("rt")
        acc.save()
        campaign = EmailCampaign.objects.create(
            subject="اختبار", body="مرحبا", audience=Audience.USER,
            audience_user=self.student, created_by=self.admin, sender_account=acc,
        )
        with patch("apps.emailcenter.gmail.send_gmail", return_value=True) as mock_send, \
             patch("apps.emailcenter.gmail.ensure_access_token", return_value="tok"):
            services.send_campaign(campaign.pk)
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, EmailCampaign.Status.SENT)
        self.assertEqual(mock_send.call_count, 1)
        self.assertEqual(mock_send.call_args[0][0], acc)  # sent AS the Gmail account
        self.assertEqual(EmailLog.objects.filter(status=EmailLog.Status.SENT).count(), 1)

    def test_campaign_fails_loudly_when_gmail_auth_broken(self):
        """A chosen sender is never silently replaced: auth failure at send
        time fails the whole campaign with a clear per-recipient error."""
        from unittest.mock import patch
        import requests as _requests
        from apps.emailcenter import services
        from apps.emailcenter.models import EmailCampaign, EmailLog, GmailAccount, Audience
        acc = GmailAccount(user=self.admin, email="a@gmail.com")
        acc.set_refresh_token("rt")
        acc.save()
        campaign = EmailCampaign.objects.create(
            subject="اختبار", body="مرحبا", audience=Audience.USER,
            audience_user=self.student, created_by=self.admin, sender_account=acc,
        )
        with patch("apps.emailcenter.gmail.ensure_access_token",
                   side_effect=_requests.HTTPError("invalid_grant")):
            services.send_campaign(campaign.pk)
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, EmailCampaign.Status.FAILED)
        log = EmailLog.objects.get()
        self.assertEqual(log.status, EmailLog.Status.FAILED)
        self.assertIn("Gmail", log.error)

    def test_compose_gmail_sender_without_account_shows_error(self):
        from apps.emailcenter.models import EmailCampaign
        self.client.force_login(self.admin)
        r = self.client.post(reverse("emailcenter:compose"), {
            "subject": "س", "body": "ن", "audience": "all", "sender": "gmail",
        })
        self.assertEqual(r.status_code, 200)  # re-rendered with error
        self.assertFalse(EmailCampaign.objects.exists())

    def test_disconnect_deletes_account_and_requires_post(self):
        from apps.emailcenter.models import GmailAccount
        acc = GmailAccount(user=self.sub, email="s@gmail.com")
        acc.set_refresh_token("rt")
        acc.save()
        self.client.force_login(self.sub)
        self.client.get(reverse("emailcenter:gmail_disconnect"))
        self.assertTrue(GmailAccount.objects.exists())  # GET is a no-op
        self.client.post(reverse("emailcenter:gmail_disconnect"))
        self.assertFalse(GmailAccount.objects.exists())

    def test_ensure_access_token_refresh_and_cache(self):
        from unittest.mock import patch, MagicMock
        from django.utils import timezone
        from datetime import timedelta
        from apps.emailcenter import gmail as gmail_svc
        from apps.emailcenter.models import GmailAccount
        acc = GmailAccount(user=self.admin, email="a@gmail.com")
        acc.set_refresh_token("rt")
        acc.save()
        # expired -> refresh call persists a new token
        ok = MagicMock(status_code=200)
        ok.json.return_value = {"access_token": "fresh", "expires_in": 3600}
        with patch("apps.emailcenter.gmail.requests.post", return_value=ok) as mock_post:
            token = gmail_svc.ensure_access_token(acc)
        self.assertEqual(token, "fresh")
        self.assertEqual(mock_post.call_count, 1)
        acc.refresh_from_db()
        self.assertEqual(acc.access_token, "fresh")
        self.assertGreater(acc.access_token_expires_at, timezone.now() + timedelta(minutes=30))
        # still valid -> no HTTP call
        with patch("apps.emailcenter.gmail.requests.post") as mock_post:
            token = gmail_svc.ensure_access_token(acc)
        self.assertEqual(token, "fresh")
        mock_post.assert_not_called()

    def test_send_gmail_returns_false_and_logs_on_http_error(self):
        from unittest.mock import patch, MagicMock
        import requests as _requests
        from apps.emailcenter import gmail as gmail_svc
        from apps.emailcenter.models import GmailAccount
        from django.utils import timezone
        from datetime import timedelta
        acc = GmailAccount(user=self.admin, email="a@gmail.com",
                           access_token="tok")
        acc.set_refresh_token("rt")
        acc.access_token_expires_at = timezone.now() + timedelta(hours=1)
        acc.save()
        bad = MagicMock(status_code=403, text='{"error":"forbidden"}')
        bad.raise_for_status.side_effect = _requests.HTTPError("403")
        with patch("apps.emailcenter.gmail.requests.post", return_value=bad):
            with self.assertLogs("apps.emailcenter.gmail", level="ERROR"):
                self.assertFalse(gmail_svc.send_gmail(acc, "س", "<b>ن</b>", "x@y.com"))

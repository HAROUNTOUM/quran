from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.webinars.models import Webinar


def make_user(role, i=0):
    return User.objects.create_user(
        username=f"{role}{i}@webinars.tld", email=f"{role}{i}@webinars.tld",
        password="x", role=role, full_name_ar=f"{role} {i}",
        is_approved=User.ApprovalStatus.APPROVED,
    )


class WebinarModelTests(TestCase):
    def setUp(self):
        self.admin = make_user("admin", 0)
        self.teacher = make_user("teacher", 0)
        self.student = make_user("student", 0)

    def _webinar(self, **kwargs):
        defaults = dict(
            title="ندوة اختبار", scheduled_at=timezone.now() + timezone.timedelta(hours=1),
            created_by=self.admin,
        )
        defaults.update(kwargs)
        return Webinar.objects.create(**defaults)

    def test_default_status_is_scheduled(self):
        w = self._webinar()
        self.assertEqual(w.status, Webinar.Status.SCHEDULED)

    def test_lifecycle_start_end_replay(self):
        w = self._webinar()
        w.start(by=self.admin)
        self.assertEqual(w.status, Webinar.Status.LIVE)
        self.assertIsNotNone(w.started_at)

        w.end(by=self.admin)
        self.assertEqual(w.status, Webinar.Status.ENDED)
        self.assertIsNotNone(w.ended_at)

        w.stream_url = "https://youtube.com/watch?v=abcd123"
        w.save()
        w.enable_replay(by=self.admin)
        self.assertEqual(w.status, Webinar.Status.REPLAY)

    def test_start_validates_permission(self):
        w = self._webinar()
        with self.assertRaises(ValidationError):
            w.start(by=self.teacher)

    def test_start_validates_status(self):
        w = self._webinar()
        w.start(by=self.admin)
        with self.assertRaises(ValidationError):
            w.start(by=self.admin)  # already live

    def test_end_validates_not_live(self):
        w = self._webinar()
        with self.assertRaises(ValidationError):
            w.end(by=self.admin)  # not live yet

    def test_replay_validates_ended(self):
        w = self._webinar()
        with self.assertRaises(ValidationError):
            w.enable_replay(by=self.admin)  # not ended

    def test_replay_validates_stream_url(self):
        w = self._webinar()
        w.start(by=self.admin)
        w.end(by=self.admin)
        with self.assertRaises(ValidationError):
            w.enable_replay(by=self.admin)  # no stream_url

    def test_replay_requires_admin(self):
        w = self._webinar()
        w.start(by=self.admin)
        w.end(by=self.admin)
        w.stream_url = "https://youtube.com/watch?v=x"
        w.save()
        with self.assertRaises(ValidationError):
            w.enable_replay(by=self.teacher)

    def test_is_watchable_live(self):
        w = self._webinar(stream_url="https://youtube.com/watch?v=abc123")
        w.start(by=self.admin)
        self.assertTrue(w.is_watchable)

    def test_is_watchable_replay(self):
        w = self._webinar(stream_url="https://youtube.com/watch?v=abc123")
        w.start(by=self.admin)
        w.end(by=self.admin)
        w.enable_replay(by=self.admin)
        self.assertTrue(w.is_watchable)

    def test_is_not_watchable_scheduled(self):
        w = self._webinar(stream_url="https://youtube.com/watch?v=abc123")
        self.assertFalse(w.is_watchable)

    def test_can_manage_admin_only(self):
        self.assertTrue(Webinar.can_manage(self.admin))
        self.assertFalse(Webinar.can_manage(self.teacher))
        self.assertFalse(Webinar.can_manage(self.student))

    def test_can_join_speaker_room(self):
        w = self._webinar()
        w.co_speakers.add(self.teacher)
        self.assertTrue(w.can_join_speaker_room(self.admin))
        self.assertTrue(w.can_join_speaker_room(self.teacher))
        self.assertFalse(w.can_join_speaker_room(self.student))

    def test_can_view(self):
        w = self._webinar()
        self.assertTrue(w.can_view(self.student))
        w.is_active = False
        w.save()
        self.assertFalse(w.can_view(self.student))

    def test_parse_stream_embed_youtube(self):
        from apps.webinars.models import parse_stream_embed

        embed, chat = parse_stream_embed("https://www.youtube.com/watch?v=abc123def", "example.com")
        self.assertIn("abc123def", embed)
        self.assertIn("abc123def", chat)

        embed, chat = parse_stream_embed("https://youtu.be/xyz789", "example.com")
        self.assertIn("xyz789", embed)

        embed, chat = parse_stream_embed("https://vimeo.com/12345", "example.com")
        self.assertEqual(embed, "https://vimeo.com/12345")
        self.assertIsNone(chat)

    def test_speaker_room_name_unguessable(self):
        w = self._webinar()
        self.assertTrue(w.speaker_room_name.startswith("hafezwebinar-"))
        self.assertGreater(len(w.speaker_room_name), 20)


class WebinarAccessTests(TestCase):
    def setUp(self):
        self.admin = make_user("admin", 0)
        self.teacher = make_user("teacher", 0)
        self.student = make_user("student", 0)
        self.webinar = Webinar.objects.create(
            title="ندوة اختبار", scheduled_at=timezone.now() + timezone.timedelta(hours=1),
            created_by=self.admin,
        )

    def _enable_feature(self):
        from apps.usersettings.models import SystemSettings

        SystemSettings.load().set("feature_webinars_enabled", True, changed_by=self.admin)

    def _disable_feature(self):
        from apps.usersettings.models import SystemSettings

        SystemSettings.load().set("feature_webinars_enabled", False, changed_by=self.admin)

    def login(self, user):
        self.client.force_login(user)

    def test_list_accessible(self):
        self._enable_feature()
        self.login(self.student)
        resp = self.client.get(reverse("webinars:list"))
        self.assertEqual(resp.status_code, 200)

    def test_list_without_feature_redirects_non_admin(self):
        self._disable_feature()
        self.login(self.student)
        resp = self.client.get(reverse("webinars:list"))
        self.assertEqual(resp.status_code, 302)

    def test_list_without_feature_allows_admin(self):
        self._disable_feature()
        self.login(self.admin)
        resp = self.client.get(reverse("webinars:list"))
        self.assertEqual(resp.status_code, 200)

    def test_admin_list_requires_admin(self):
        self.login(self.student)
        resp = self.client.get(reverse("webinars:admin_list"))
        self.assertEqual(resp.status_code, 403)
        self.login(self.admin)
        resp = self.client.get(reverse("webinars:admin_list"))
        self.assertEqual(resp.status_code, 200)

    def test_admin_create_requires_admin(self):
        self.login(self.teacher)
        resp = self.client.get(reverse("webinars:admin_create"))
        self.assertEqual(resp.status_code, 403)

    def test_admin_manage_requires_admin(self):
        self.login(self.teacher)
        resp = self.client.get(reverse("webinars:admin_manage", args=[self.webinar.pk]))
        self.assertEqual(resp.status_code, 403)

    def test_speaker_room_blocks_non_speaker(self):
        self.login(self.student)
        resp = self.client.get(reverse("webinars:speaker_room", args=[self.webinar.pk]))
        self.assertEqual(resp.status_code, 302)

    def test_speaker_room_allows_co_speaker(self):
        self.webinar.co_speakers.add(self.teacher)
        self.login(self.teacher)
        resp = self.client.get(reverse("webinars:speaker_room", args=[self.webinar.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_speaker_room_allows_admin(self):
        self.login(self.admin)
        resp = self.client.get(reverse("webinars:speaker_room", args=[self.webinar.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_watch_accessible_for_authenticated(self):
        self._enable_feature()
        self.login(self.student)
        self.webinar.stream_url = "https://youtube.com/watch?v=xyz"
        self.webinar.save()
        self.webinar.start(by=self.admin)
        resp = self.client.get(reverse("webinars:watch", args=[self.webinar.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_watch_blocked_inactive(self):
        self._enable_feature()
        self.login(self.student)
        self.webinar.is_active = False
        self.webinar.save()
        resp = self.client.get(reverse("webinars:watch", args=[self.webinar.pk]))
        self.assertEqual(resp.status_code, 302)

    def test_watch_blocked_not_watchable(self):
        self._enable_feature()
        self.login(self.student)
        resp = self.client.get(reverse("webinars:watch", args=[self.webinar.pk]))
        self.assertEqual(resp.status_code, 302)

    def test_toggle_feature(self):
        self.login(self.admin)
        resp = self.client.post(reverse("webinars:admin_list"), {"action": "toggle_feature"})
        self.assertEqual(resp.status_code, 200)


class TeacherWebinarsPageTests(TestCase):
    def setUp(self):
        self.admin = make_user("admin", 0)
        self.host_teacher = make_user("teacher", 0)
        self.speaker_teacher = make_user("teacher", 1)
        self.other_teacher = make_user("teacher", 2)

    def _webinar(self, **kwargs):
        defaults = dict(
            title="ندوة", scheduled_at=timezone.now() + timezone.timedelta(hours=1),
            created_by=self.admin,
        )
        defaults.update(kwargs)
        return Webinar.objects.create(**defaults)

    def test_lists_only_host_and_co_speaker_webinars(self):
        hosted = self._webinar(title="مستضافة", created_by=self.host_teacher)
        speaking = self._webinar(title="متحدث فيها")
        speaking.co_speakers.add(self.speaker_teacher)
        unrelated = self._webinar(title="غير متعلقة")

        self.client.force_login(self.host_teacher)
        resp = self.client.get(reverse("accounts:teacher_webinars"))
        self.assertEqual(resp.status_code, 200)
        listed = list(resp.context["webinars"])
        self.assertIn(hosted, listed)
        self.assertNotIn(speaking, listed)
        self.assertNotIn(unrelated, listed)

        self.client.force_login(self.speaker_teacher)
        resp = self.client.get(reverse("accounts:teacher_webinars"))
        listed = list(resp.context["webinars"])
        self.assertEqual(listed, [speaking])

    def test_requires_teacher_role(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("accounts:teacher_webinars"))
        self.assertEqual(resp.status_code, 403)

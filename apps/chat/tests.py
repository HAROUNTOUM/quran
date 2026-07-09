from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.circles.models import Circle, CircleEnrollment
from apps.chat.models import Conversation, Message
from apps.chat.permissions import can_message, messageable_users
from apps.chat.services import create_message, unread_count, mark_read


def _user(email, role, name):
    return User.objects.create_user(
        username=email, email=email, password="x",
        full_name_ar=name, role=role,
        is_approved=User.ApprovalStatus.APPROVED,
    )


class ChatPermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = _user("a@t.com", User.Role.MAIN_ADMIN, "الأدمن")
        cls.teacher = _user("t@t.com", User.Role.TEACHER, "الأستاذ")
        cls.other_teacher = _user("t2@t.com", User.Role.TEACHER, "أستاذ آخر")
        cls.student = _user("s@t.com", User.Role.STUDENT, "الطالب")
        cls.other_student = _user("s2@t.com", User.Role.STUDENT, "طالب آخر")
        circle = Circle.objects.create(name="حلقة", teacher=cls.teacher)
        CircleEnrollment.objects.create(
            circle=circle, student=cls.student,
            status=CircleEnrollment.Status.ACTIVE,
        )

    def test_staff_can_message_anyone(self):
        self.assertTrue(can_message(self.admin, self.student))
        self.assertTrue(can_message(self.student, self.admin))

    def test_teacher_can_message_own_student_only(self):
        self.assertTrue(can_message(self.teacher, self.student))
        self.assertFalse(can_message(self.teacher, self.other_student))

    def test_student_can_message_own_teacher_only(self):
        self.assertTrue(can_message(self.student, self.teacher))
        self.assertFalse(can_message(self.student, self.other_teacher))

    def test_peers_cannot_message(self):
        self.assertFalse(can_message(self.teacher, self.other_teacher))
        self.assertFalse(can_message(self.student, self.other_student))

    def test_cannot_message_self(self):
        self.assertFalse(can_message(self.admin, self.admin))

    def test_messageable_users_excludes_forbidden(self):
        ids = set(messageable_users(self.student).values_list("id", flat=True))
        self.assertIn(self.teacher.id, ids)
        self.assertIn(self.admin.id, ids)
        self.assertNotIn(self.other_teacher.id, ids)
        self.assertNotIn(self.student.id, ids)


class ConversationModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = _user("a@t.com", User.Role.MAIN_ADMIN, "الأدمن")
        cls.student = _user("s@t.com", User.Role.STUDENT, "الطالب")

    def test_get_or_create_is_idempotent(self):
        c1, created1 = Conversation.get_or_create_between(self.admin, self.student)
        c2, created2 = Conversation.get_or_create_between(self.student, self.admin)
        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(c1.pk, c2.pk)
        self.assertEqual(Conversation.objects.count(), 1)

    def test_unread_and_mark_read(self):
        conv, _ = Conversation.get_or_create_between(self.admin, self.student)
        create_message(conv, self.admin, "مرحبا")
        self.assertEqual(unread_count(self.student), 1)
        self.assertEqual(unread_count(self.admin), 0)  # own message
        mark_read(conv, self.student)
        self.assertEqual(unread_count(self.student), 0)

    def test_empty_body_creates_nothing(self):
        conv, _ = Conversation.get_or_create_between(self.admin, self.student)
        self.assertIsNone(create_message(conv, self.admin, "   "))
        self.assertEqual(Message.objects.count(), 0)


class ChatViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = _user("a@t.com", User.Role.MAIN_ADMIN, "الأدمن")
        cls.teacher = _user("t@t.com", User.Role.TEACHER, "الأستاذ")
        cls.student = _user("s@t.com", User.Role.STUDENT, "الطالب")
        cls.other_teacher = _user("t2@t.com", User.Role.TEACHER, "أستاذ آخر")

    def test_inbox_requires_login(self):
        resp = self.client.get(reverse("chat:inbox"))
        self.assertEqual(resp.status_code, 302)

    def test_start_and_send_flow(self):
        self.client.force_login(self.admin)
        resp = self.client.post(reverse("chat:start"), {"user_id": self.student.id})
        conv = Conversation.objects.get()
        self.assertRedirects(resp, reverse("chat:conversation", args=[conv.id]))

        resp = self.client.post(reverse("chat:send", args=[conv.id]), {"body": "سلام"})
        self.assertRedirects(resp, reverse("chat:conversation", args=[conv.id]))
        self.assertEqual(conv.messages.count(), 1)
        self.assertEqual(unread_count(self.student), 1)

    def test_cannot_start_with_forbidden_user(self):
        self.client.force_login(self.teacher)
        resp = self.client.post(reverse("chat:start"), {"user_id": self.other_teacher.id})
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(Conversation.objects.count(), 0)

    def test_cannot_open_others_conversation(self):
        conv, _ = Conversation.get_or_create_between(self.admin, self.student)
        self.client.force_login(self.teacher)
        resp = self.client.get(reverse("chat:conversation", args=[conv.id]))
        self.assertEqual(resp.status_code, 404)

    def test_inbox_marks_active_thread_read(self):
        conv, _ = Conversation.get_or_create_between(self.admin, self.student)
        create_message(conv, self.admin, "رسالة")
        self.client.force_login(self.student)
        self.assertEqual(unread_count(self.student), 1)
        self.client.get(reverse("chat:conversation", args=[conv.id]))
        self.assertEqual(unread_count(self.student), 0)

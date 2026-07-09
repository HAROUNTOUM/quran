from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.circles.models import Circle, CircleEnrollment
from apps.classrooms.models import TeacherRoom


def make_user(role, i=0):
    return User.objects.create_user(
        username=f"{role}{i}@rooms.tld", email=f"{role}{i}@rooms.tld",
        password="x", role=role, full_name_ar=f"{role} {i}",
        is_approved=User.ApprovalStatus.APPROVED,
    )


class TeacherRoomModelTests(TestCase):
    def test_signal_creates_room_for_teacher_only(self):
        teacher = make_user("teacher")
        student = make_user("student")
        self.assertTrue(TeacherRoom.objects.filter(teacher=teacher).exists())
        self.assertFalse(TeacherRoom.objects.filter(teacher=student).exists())

    def test_room_is_permanent_and_idempotent(self):
        teacher = make_user("teacher")
        room1 = teacher.get_or_create_room()
        room2 = teacher.get_or_create_room()
        self.assertEqual(room1.pk, room2.pk)  # one room, forever
        self.assertEqual(TeacherRoom.objects.filter(teacher=teacher).count(), 1)

    def test_get_or_create_room_rejects_non_teachers(self):
        student = make_user("student")
        with self.assertRaises(ValidationError):
            student.get_or_create_room()

    def test_no_name_or_slug_collisions(self):
        rooms = [make_user("teacher", i).room for i in range(1, 31)]
        names = {r.room_name for r in rooms}
        slugs = {r.slug for r in rooms}
        self.assertEqual(len(names), 30)
        self.assertEqual(len(slugs), 30)

    def test_room_name_not_derived_from_teacher(self):
        teacher = make_user("teacher", 99)
        room = teacher.room
        self.assertNotIn(str(teacher.pk), room.room_name)
        self.assertNotIn("teacher", room.room_name.replace("hafezroom", ""))
        self.assertNotEqual(room.slug, room.room_name)

    def test_regenerate_rotates_name_but_keeps_slug(self):
        room = make_user("teacher", 98).room
        old_name, old_slug = room.room_name, room.slug
        room.regenerate_room_name()
        self.assertNotEqual(room.room_name, old_name)
        self.assertEqual(room.slug, old_slug)

    def test_backfill_command(self):
        teacher = make_user("teacher", 50)
        TeacherRoom.objects.filter(teacher=teacher).delete()
        call_command("backfill_teacher_rooms")
        self.assertTrue(TeacherRoom.objects.filter(teacher=teacher).exists())


class RoomAccessTests(TestCase):
    """Section C.8 — the explicitly mandated edge cases."""

    def setUp(self):
        self.teacher = make_user("teacher", 1)
        self.other_teacher = make_user("teacher", 2)
        self.enrolled = make_user("student", 1)
        self.unenrolled = make_user("student", 2)
        self.admin = make_user("admin", 1)
        self.circle = Circle.objects.create(name="حلقة الاختبار", teacher=self.teacher)
        CircleEnrollment.objects.create(
            circle=self.circle, student=self.enrolled,
            status=CircleEnrollment.Status.ACTIVE,
        )
        self.room = self.teacher.room
        self.url = reverse("classrooms:join", args=[self.room.slug])

    def login(self, user):
        self.client.force_login(user)

    def test_anonymous_redirected_to_login(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp.url)

    def test_enrolled_student_can_join(self):
        from django.utils.html import escapejs

        self.login(self.enrolled)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        # The embed writes the room name through |escapejs, which encodes
        # the hyphen as a JS unicode escape, so match the escaped form.
        self.assertContains(resp, escapejs(self.room.room_name))

    def test_unenrolled_student_blocked_despite_knowing_url(self):
        """URL obscurity is never the access mechanism."""
        self.login(self.unenrolled)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)  # friendly redirect, not a render

    def test_owner_joins_independent_of_enrollment_check(self):
        self.login(self.teacher)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

    def test_other_teacher_blocked(self):
        self.login(self.other_teacher)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)

    def test_admin_oversight_allowed(self):
        self.login(self.admin)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

    def test_deactivated_room_unjoinable_for_everyone(self):
        self.room.is_active = False
        self.room.save(update_fields=["is_active"])
        for user in (self.enrolled, self.teacher, self.admin):
            self.login(user)
            resp = self.client.get(self.url)
            self.assertEqual(resp.status_code, 302, f"{user.role} should be blocked")

    def test_deactivated_teacher_makes_room_unjoinable(self):
        self.teacher.is_active = False
        self.teacher.save(update_fields=["is_active"])
        self.login(self.enrolled)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)

    def test_dropped_enrollment_loses_access(self):
        CircleEnrollment.objects.filter(student=self.enrolled).update(
            status=CircleEnrollment.Status.DROPPED,
        )
        self.login(self.enrolled)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)

    def test_student_redirected_to_teacher_room(self):
        self.login(self.enrolled)
        resp = self.client.get(reverse("classrooms:my_classroom"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(self.room.slug, resp.url)

    def test_unenrolled_student_redirected_to_dashboard(self):
        self.login(self.unenrolled)
        resp = self.client.get(reverse("classrooms:my_classroom"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("dashboard", resp.url)

    def test_admin_list_requires_staff_role(self):
        self.login(self.enrolled)
        resp = self.client.get(reverse("classrooms:admin_list"))
        self.assertEqual(resp.status_code, 403)
        self.login(self.admin)
        resp = self.client.get(reverse("classrooms:admin_list"))
        self.assertEqual(resp.status_code, 200)

from datetime import date

from django.http import Http404
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.views import admin_dashboard, profile_edit_view, teacher_session_attendance
from apps.circles.models import Circle, Session
from apps.references.models import EvaluationCriterion


class ProfileEditViewTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username="admin@test.com",
            email="admin@test.com",
            password="test1234",
            full_name_ar="مدير النظام",
            role=User.Role.ADMIN,
            is_approved=User.ApprovalStatus.APPROVED,
            phone="0500000000",
            gender="male",
        )

    def test_authenticated_user_can_open_profile_edit_page(self):
        request = self.factory.get(reverse("accounts:profile_edit"))
        request.user = self.user

        response = profile_edit_view(request)

        self.assertEqual(response.status_code, 200)
        self.assertIn("تعديل الملف الشخصي", response.content.decode())

    def test_user_can_update_own_profile(self):
        request = self.factory.post(reverse("accounts:profile_edit"), {
            "full_name_ar": "مدير محدث",
            "email": "updated@test.com",
            "phone": "0555555555",
            "gender": "female",
        })
        SessionMiddleware(lambda req: None).process_request(request)
        request.session.save()
        request._messages = FallbackStorage(request)
        request.user = self.user

        response = profile_edit_view(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:profile"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.full_name_ar, "مدير محدث")
        self.assertEqual(self.user.email, "updated@test.com")
        self.assertEqual(self.user.username, "updated@test.com")
        self.assertEqual(self.user.phone, "0555555555")
        self.assertEqual(self.user.gender, "female")

    def test_anonymous_user_is_redirected(self):
        request = self.factory.get(reverse("accounts:profile_edit"))
        request.user = AnonymousUser()
        response = profile_edit_view(request)

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)


class AdminDashboardActionTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.admin = User.objects.create_user(
            username="admin@test.com",
            email="admin@test.com",
            password="test1234",
            full_name_ar="مدير النظام",
            role=User.Role.ADMIN,
            is_approved=User.ApprovalStatus.APPROVED,
        )

    def test_admin_dashboard_exposes_crud_action_hub(self):
        request = self.factory.get(reverse("accounts:admin_dashboard"))
        request.user = self.admin

        response = admin_dashboard(request)
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn("إجراءات الإدارة", content)
        self.assertIn("إضافة معلم", content)
        self.assertIn("إنشاء حلقة", content)
        self.assertIn("إعلان جديد", content)
        self.assertIn("إشعار جديد", content)
        self.assertIn(reverse("accounts:admin_teacher_create"), content)
        self.assertIn(reverse("accounts:admin_circle_create"), content)

    def test_admin_dashboard_handles_empty_circle_enrollments(self):
        teacher = User.objects.create_user(
            username="teacher@test.com",
            email="teacher@test.com",
            password="test1234",
            full_name_ar="المعلم",
            role=User.Role.TEACHER,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        Circle.objects.create(
            name="حلقة بدون طلاب",
            teacher=teacher,
            status=Circle.Status.ACTIVE,
        )
        request = self.factory.get(reverse("accounts:admin_dashboard"))
        request.user = self.admin

        response = admin_dashboard(request)

        self.assertEqual(response.status_code, 200)
        self.assertIn("حلقة بدون طلاب", response.content.decode())


class TeacherSessionAttendanceAccessTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.admin = User.objects.create_user(
            username="admin@test.com",
            email="admin@test.com",
            password="test1234",
            full_name_ar="مدير النظام",
            role=User.Role.ADMIN,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        self.teacher = User.objects.create_user(
            username="teacher@test.com",
            email="teacher@test.com",
            password="test1234",
            full_name_ar="المعلم",
            role=User.Role.TEACHER,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        self.other_teacher = User.objects.create_user(
            username="other-teacher@test.com",
            email="other-teacher@test.com",
            password="test1234",
            full_name_ar="معلم آخر",
            role=User.Role.TEACHER,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        self.circle = Circle.objects.create(
            name="حلقة الفجر",
            teacher=self.teacher,
            status=Circle.Status.ACTIVE,
        )
        self.session = Session.objects.create(
            circle=self.circle,
            session_date=date.today(),
        )
        EvaluationCriterion.objects.create(name_ar="التجويد")

    def test_admin_can_open_any_session_attendance_page(self):
        request = self.factory.get(
            reverse("accounts:teacher_session_attendance", args=[self.session.id])
        )
        request.user = self.admin

        response = teacher_session_attendance(request, self.session.id)

        self.assertEqual(response.status_code, 200)
        self.assertIn("تسجيل الحضور والدرجات", response.content.decode())

    def test_teacher_can_open_own_session_attendance_page(self):
        request = self.factory.get(
            reverse("accounts:teacher_session_attendance", args=[self.session.id])
        )
        request.user = self.teacher

        response = teacher_session_attendance(request, self.session.id)

        self.assertEqual(response.status_code, 200)

    def test_teacher_cannot_open_another_teacher_session_attendance_page(self):
        request = self.factory.get(
            reverse("accounts:teacher_session_attendance", args=[self.session.id])
        )
        request.user = self.other_teacher

        with self.assertRaises(Http404):
            teacher_session_attendance(request, self.session.id)

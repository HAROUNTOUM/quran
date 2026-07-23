from datetime import date
from unittest.mock import patch

from django.http import Http404
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Batch, User
from apps.accounts.views import admin_dashboard, profile_edit_view, teacher_session_attendance
from apps.accounts.forms import LoginForm, SignupForm, ApprovalForm
from apps.circles.models import Circle, CircleEnrollment, Session
from apps.references.models import EvaluationCriterion


class SignupFormTests(TestCase):
    def test_gender_field_has_choices(self):
        form = SignupForm()
        self.assertIn(("", "اختر الجنس"), form.fields["gender"].choices)
        self.assertIn(("male", "ذكر"), form.fields["gender"].choices)
        self.assertIn(("female", "أنثى"), form.fields["gender"].choices)

    def test_required_fields_are_marked(self):
        form = SignupForm()
        required = ("full_name_ar", "email", "phone", "gender", "role", "password1", "password2")
        for name in required:
            self.assertTrue(form.fields[name].required, f"{name} should be required")
            self.assertIn("required", form.fields[name].widget.attrs)

    def test_signup_valid_data(self):
        data = {
            "full_name_ar": "أحمد بن محمد",
            "email": "ahmed@test.com",
            "phone": "0555123456",
            "gender": "male",
            "role": "student",
            "password1": "testpass123",
            "password2": "testpass123",
            "pledge": "on",
        }
        form = SignupForm(data)
        self.assertTrue(form.is_valid(), msg=dict(form.errors))

    def test_signup_empty_full_name(self):
        form = SignupForm(data={"full_name_ar": "", "email": "a@b.com", "phone": "0555123456", "gender": "male", "role": "student", "password1": "testpass123", "password2": "testpass123", "pledge": "on"})
        self.assertFalse(form.is_valid())

    def test_signup_duplicate_email(self):
        User.objects.create_user(username="existing@test.com", email="existing@test.com", password="test1234", full_name_ar="موجود")
        form = SignupForm(data={"full_name_ar": "جديد", "email": "existing@test.com", "phone": "0555123456", "gender": "male", "role": "student", "password1": "testpass123", "password2": "testpass123", "pledge": "on"})
        self.assertFalse(form.is_valid())
        self.assertIn("مسجل مسبقاً", str(form.errors))

    def test_signup_short_password(self):
        form = SignupForm(data={"full_name_ar": "أحمد", "email": "a@b.com", "phone": "0555123456", "gender": "male", "role": "student", "password1": "short", "password2": "short", "pledge": "on"})
        self.assertFalse(form.is_valid())
        self.assertIn("8 أحرف", str(form.errors))

    def test_signup_mismatched_passwords(self):
        form = SignupForm(data={"full_name_ar": "أحمد", "email": "a@b.com", "phone": "0555123456", "gender": "male", "role": "student", "password1": "testpass123", "password2": "different", "pledge": "on"})
        self.assertFalse(form.is_valid())
        self.assertIn("غير متطابقتين", str(form.errors))

    def test_signup_short_phone(self):
        form = SignupForm(data={"full_name_ar": "أحمد", "email": "a@b.com", "phone": "123", "gender": "male", "role": "student", "password1": "testpass123", "password2": "testpass123", "pledge": "on"})
        self.assertFalse(form.is_valid())
        self.assertIn("هاتف", str(form.errors))

    def test_signup_email_normalized(self):
        form = SignupForm(data={"full_name_ar": "أحمد", "email": "Test@Example.COM", "phone": "0555123456", "gender": "male", "role": "student", "password1": "testpass123", "password2": "testpass123", "pledge": "on"})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["email"], "test@example.com")

    def test_signup_saves_user(self):
        form = SignupForm(data={"full_name_ar": "أحمد بن محمد", "email": "ahmed@test.com", "phone": "0555123456", "gender": "male", "role": "student", "password1": "testpass123", "password2": "testpass123", "pledge": "on"})
        self.assertTrue(form.is_valid())
        user = form.save()
        self.assertEqual(user.username, "ahmed@test.com")
        self.assertEqual(user.is_approved, User.ApprovalStatus.PENDING)
        self.assertTrue(user.is_active)


class LoginFormTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="student@test.com", email="student@test.com",
            password="testpass123", full_name_ar="طالب",
            role=User.Role.STUDENT, is_approved=User.ApprovalStatus.APPROVED,
        )

    def test_valid_credentials(self):
        self.client.post(reverse("accounts:login"), {"email": "student@test.com", "password": "testpass123"})
        self.assertTrue(self.client.session.get("_auth_user_id"))

    def test_invalid_email(self):
        resp = self.client.post(reverse("accounts:login"), {"email": "wrong@test.com", "password": "testpass123"})
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(resp, "غير مسجل")

    def test_wrong_password(self):
        resp = self.client.post(reverse("accounts:login"), {"email": "student@test.com", "password": "wrong"})
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(resp, "غير صحيحة")

    def test_pending_approval(self):
        self.user.is_approved = User.ApprovalStatus.PENDING
        self.user.save()
        resp = self.client.post(reverse("accounts:login"), {"email": "student@test.com", "password": "testpass123"})
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(resp, "قيد المراجعة", status_code=403)

    def test_rejected_approval(self):
        self.user.is_approved = User.ApprovalStatus.REJECTED
        self.user.rejection_reason = "نقص في البيانات"
        self.user.save()
        resp = self.client.post(reverse("accounts:login"), {"email": "student@test.com", "password": "testpass123"})
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(resp, "نقص في البيانات", status_code=403)

    def test_inactive_user(self):
        self.user.is_active = False
        self.user.save()
        resp = self.client.post(reverse("accounts:login"), {"email": "student@test.com", "password": "testpass123"})
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(resp, "معطّل", status_code=403)


class LogoutTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="student@test.com", email="student@test.com",
            password="testpass123", full_name_ar="طالب",
            role=User.Role.STUDENT, is_approved=User.ApprovalStatus.APPROVED,
        )
        self.client.force_login(self.user)

    def test_logout_get_returns_405(self):
        """logout_view is @require_POST now"""
        resp = self.client.get(reverse("accounts:logout"))
        self.assertEqual(resp.status_code, 405)

    def test_logout_post_succeeds(self):
        resp = self.client.post(reverse("accounts:logout"))
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertRedirects(resp, reverse("accounts:landing"))


class ApprovalEmailTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin@test.com", email="admin@test.com",
            password="test1234", full_name_ar="مدير",
            role=User.Role.MAIN_ADMIN, is_approved=User.ApprovalStatus.APPROVED,
        )
        self.pending_user = User.objects.create_user(
            username="pending@test.com", email="pending@test.com",
            password="test1234", full_name_ar="معلق",
            role=User.Role.STUDENT, is_approved=User.ApprovalStatus.PENDING,
        )
        self.client.force_login(self.admin)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_approve_sends_email(self):
        from django.core.mail import outbox
        self.client.post(
            reverse("accounts:approve_user", args=[self.pending_user.pk]),
            {"action": "approve"},
        )
        self.pending_user.refresh_from_db()
        self.assertEqual(self.pending_user.is_approved, User.ApprovalStatus.APPROVED)
        self.assertEqual(len(outbox), 1)
        self.assertIn("اعتماد حسابك", outbox[0].subject)
        self.assertIn(self.pending_user.email, outbox[0].to)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_reject_sends_email(self):
        from django.core.mail import outbox
        self.client.post(
            reverse("accounts:approve_user", args=[self.pending_user.pk]),
            {"action": "reject", "rejection_reason": "مستندات ناقصة"},
        )
        self.pending_user.refresh_from_db()
        self.assertEqual(self.pending_user.is_approved, User.ApprovalStatus.REJECTED)
        self.assertEqual(len(outbox), 1)
        self.assertIn("انضمامك", outbox[0].subject)
        self.assertIn(self.pending_user.email, outbox[0].to)


class ProfileEditViewTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username="admin@test.com",
            email="admin@test.com",
            password="test1234",
            full_name_ar="مدير النظام",
            role=User.Role.MAIN_ADMIN,
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
            role=User.Role.MAIN_ADMIN,
            is_approved=User.ApprovalStatus.APPROVED,
        )

    def test_admin_dashboard_exposes_crud_action_hub(self):
        request = self.factory.get(reverse("accounts:admin_dashboard"))
        request.user = self.admin

        response = admin_dashboard(request)
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        # Consolidated action hub: one primary create per domain + workspace links.
        self.assertIn("إضافة طالب", content)
        self.assertIn("إنشاء حلقة", content)
        self.assertIn("إعلان جديد", content)
        self.assertIn(reverse("accounts:admin_student_create"), content)
        self.assertIn(reverse("accounts:admin_circle_create"), content)
        self.assertIn(reverse("accounts:admin_announcement_create"), content)

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
            role=User.Role.MAIN_ADMIN,
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
        self.assertIn("تسجيل حضور", response.content.decode())

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


class AdminPrivateSessionsAccessTests(TestCase):
    """The private-sessions oversight page is admin/supervisor only."""

    def setUp(self):
        def mkuser(role, i):
            return User.objects.create_user(
                username=f"{role}{i}@aps.tld", email=f"{role}{i}@aps.tld",
                password="test1234", full_name_ar=f"{role} {i}", role=role,
                is_approved=User.ApprovalStatus.APPROVED,
            )
        self.admin = mkuser(User.Role.MAIN_ADMIN, 0)
        self.supervisor = mkuser(User.Role.SUB_ADMIN, 0)
        self.teacher = mkuser(User.Role.TEACHER, 0)
        self.student = mkuser(User.Role.STUDENT, 0)
        self.url = reverse("accounts:admin_private_sessions")

    def test_admin_and_supervisor_allowed(self):
        for user in (self.admin, self.supervisor):
            self.client.force_login(user)
            resp = self.client.get(self.url)
            self.assertEqual(resp.status_code, 200)

    def test_teacher_and_student_forbidden(self):
        for user in (self.teacher, self.student):
            self.client.force_login(user)
            resp = self.client.get(self.url)
            self.assertEqual(resp.status_code, 403)


class AdminUserEditTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin-edit@test.com",
            email="admin-edit@test.com",
            password="test1234",
            full_name_ar="مدير التحرير",
            role=User.Role.MAIN_ADMIN,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        self.batch = Batch.objects.create(name="دفعة التحرير", created_by=self.admin)
        self.student = User.objects.create_user(
            username="student-edit@test.com",
            email="student-edit@test.com",
            password="test1234",
            full_name_ar="طالب قديم",
            role=User.Role.STUDENT,
            is_approved=User.ApprovalStatus.APPROVED,
            phone="0500000000",
            gender="male",
        )
        self.supervisor = User.objects.create_user(
            username="supervisor-edit@test.com",
            email="supervisor-edit@test.com",
            password="test1234",
            full_name_ar="مشرف قديم",
            role=User.Role.SUB_ADMIN,
            is_approved=User.ApprovalStatus.APPROVED,
            phone="0500000001",
            gender="male",
        )
        self.client.force_login(self.admin)

    def test_admin_can_update_student_profile(self):
        resp = self.client.post(reverse("accounts:admin_student_edit", args=[self.student.pk]), {
            "full_name_ar": "طالب محدث",
            "email": "student-updated@test.com",
            "phone": "0555555555",
            "gender": "female",
            "specialization": "حفظ",
            "state": "الجزائر",
            "level": "متوسط",
            "memorization_amount": "جزءان",
            "batch": self.batch.pk,
            "is_active": "true",
        })

        self.assertRedirects(resp, reverse("accounts:admin_student_detail", args=[self.student.pk]))
        self.student.refresh_from_db()
        self.assertEqual(self.student.full_name_ar, "طالب محدث")
        self.assertEqual(self.student.email, "student-updated@test.com")
        self.assertEqual(self.student.username, "student-updated@test.com")
        self.assertEqual(self.student.batch, self.batch)
        self.assertEqual(self.student.role, User.Role.STUDENT)

    def test_admin_can_update_supervisor_profile(self):
        resp = self.client.post(reverse("accounts:admin_supervisor_edit", args=[self.supervisor.pk]), {
            "full_name_ar": "مشرف محدث",
            "email": "supervisor-updated@test.com",
            "phone": "0555555556",
            "gender": "female",
            "is_active": "true",
        })

        self.assertRedirects(resp, reverse("accounts:admin_supervisors"))
        self.supervisor.refresh_from_db()
        self.assertEqual(self.supervisor.full_name_ar, "مشرف محدث")
        self.assertEqual(self.supervisor.email, "supervisor-updated@test.com")
        self.assertEqual(self.supervisor.username, "supervisor-updated@test.com")
        self.assertEqual(self.supervisor.role, User.Role.SUB_ADMIN)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class PasswordResetFlowTests(TestCase):
    """Regression tests for the code-based reset flow — the entry point used
    to be POST-only, so the login page's link 405'd and reset was unreachable."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="reset@test.com", email="reset@test.com", password="old-pass-123",
            full_name_ar="مستخدم", role=User.Role.STUDENT,
            is_approved=User.ApprovalStatus.APPROVED,
        )

    def test_reset_form_reachable_by_get(self):
        resp = self.client.get(reverse("accounts:password_reset"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "registration/password_reset_form.html")

    def test_unknown_email_not_enumerable(self):
        resp = self.client.post(reverse("accounts:password_reset"), {"email": "nobody@test.com"})
        self.assertRedirects(resp, reverse("accounts:password_reset_verify"))

    def test_full_reset_flow(self):
        from django.core import mail
        from apps.accounts.models import PasswordResetCode

        resp = self.client.post(reverse("accounts:password_reset"), {"email": self.user.email})
        self.assertRedirects(resp, reverse("accounts:password_reset_verify"))
        self.assertEqual(len(mail.outbox), 1)
        code = PasswordResetCode.objects.get(email=self.user.email, is_used=False).code
        self.assertIn(code, mail.outbox[0].body)

        resp = self.client.post(reverse("accounts:password_reset_verify"), {"code": code})
        self.assertRedirects(resp, reverse("accounts:password_reset_set"))

        resp = self.client.post(reverse("accounts:password_reset_set"), {
            "new_password1": "new-pass-456!", "new_password2": "new-pass-456!",
        })
        self.assertRedirects(resp, reverse("accounts:password_reset_complete"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("new-pass-456!"))

    def test_send_failure_is_surfaced_not_swallowed(self):
        with patch("apps.accounts.views.auth.send_password_reset_code", return_value=False):
            resp = self.client.post(reverse("accounts:password_reset"), {"email": self.user.email})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "تعذر إرسال رمز الاستعادة")


@override_settings(
    RATELIMIT_ENABLE=True,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                        "LOCATION": "auth-rl-tests"}},
)
class AuthRateLimitTests(TestCase):
    def test_login_post_throttled_after_limit(self):
        from django.core.cache import cache
        cache.clear()
        url = reverse("accounts:login")
        for _ in range(10):
            resp = self.client.post(url, {"email": "x@test.com", "password": "bad"})
            self.assertEqual(resp.status_code, 200)  # normal error page
        resp = self.client.post(url, {"email": "x@test.com", "password": "bad"})
        self.assertRedirects(resp, url)  # throttled → redirected with message

    def test_get_never_throttled(self):
        from django.core.cache import cache
        cache.clear()
        for _ in range(15):
            resp = self.client.get(reverse("accounts:login"))
            self.assertEqual(resp.status_code, 200)


class SupervisorBoardTests(TestCase):
    """Requirement #3 — the supervisor batch→group follow-up board."""

    def setUp(self):
        from apps.circles.models import CircleEnrollment
        from apps.attendance.models import Attendance
        from apps.accounts.models import Batch

        self.admin = User.objects.create_user(
            username="admin@test.com", email="admin@test.com",
            password="test1234", full_name_ar="المدير",
            role=User.Role.MAIN_ADMIN, is_approved=User.ApprovalStatus.APPROVED,
        )
        self.batch = Batch.objects.create(name="دفعة 1", created_by=self.admin)
        self.supervisor = User.objects.create_user(
            username="sup@test.com", email="sup@test.com",
            password="test1234", full_name_ar="المشرف العام",
            role=User.Role.SUB_ADMIN, is_approved=User.ApprovalStatus.APPROVED,
        )
        self.supervisor.managed_batch.add(self.batch)
        self.teacher = User.objects.create_user(
            username="teach@test.com", email="teach@test.com",
            password="test1234", full_name_ar="الأستاذة فاطمة",
            role=User.Role.TEACHER, is_approved=User.ApprovalStatus.APPROVED,
        )
        self.student = User.objects.create_user(
            username="stud@test.com", email="stud@test.com",
            password="test1234", full_name_ar="الطالبة مريم",
            role=User.Role.STUDENT, is_approved=User.ApprovalStatus.APPROVED,
        )
        self.circle = Circle.objects.create(
            name="فوج الأنصار", teacher=self.teacher, batch=self.batch,
        )
        CircleEnrollment.objects.create(
            circle=self.circle, student=self.student,
            status=CircleEnrollment.Status.ACTIVE,
        )
        self.session = Session.objects.create(
            circle=self.circle, session_date=date.today(),
        )
        Attendance.objects.create(
            session=self.session, student=self.student,
            status=Attendance.Status.PRESENT,
        )

    def test_supervisor_sees_board_with_present_symbol(self):
        self.client.login(username="sup@test.com", password="test1234")
        resp = self.client.get(
            reverse("accounts:supervisor_group_board", args=[self.circle.pk])
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn("الطالبة مريم", body)
        self.assertIn("✅", body)          # PRESENT → attended symbol
        self.assertIn("الأستاذة فاطمة", body)  # teacher name in header

    def test_groups_page_lists_the_batch_group(self):
        self.client.login(username="sup@test.com", password="test1234")
        resp = self.client.get(
            reverse("accounts:supervisor_groups") + f"?batch={self.batch.pk}"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("فوج الأنصار", resp.content.decode())

    def test_student_cannot_access_board(self):
        self.client.login(username="stud@test.com", password="test1234")
        resp = self.client.get(
            reverse("accounts:supervisor_group_board", args=[self.circle.pk])
        )
        self.assertIn(resp.status_code, (302, 403))


class BatchScopingSecurityTests(TestCase):
    """Review fixes C1/C2/H1: sub-admin batch scoping must never fail open
    (zero batches) and must honor every supervised batch (multi-batch)."""

    def setUp(self):
        self.main_admin = User.objects.create_user(
            username="bs_admin@test.com", email="bs_admin@test.com", password="x",
            full_name_ar="مدير", role=User.Role.MAIN_ADMIN,
            is_approved=User.ApprovalStatus.APPROVED, is_staff=True,
        )
        self.batch1 = Batch.objects.create(
            name="دفعة 1", number=1, year=2026, created_by=self.main_admin,
        )
        self.batch2 = Batch.objects.create(
            name="دفعة 2", number=2, year=2026, created_by=self.main_admin,
        )
        self.sub_multi = User.objects.create_user(
            username="bs_multi@test.com", email="bs_multi@test.com", password="x",
            full_name_ar="مشرف متعدد", role=User.Role.SUB_ADMIN,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        self.batch1.sub_admins.add(self.sub_multi)
        self.batch2.sub_admins.add(self.sub_multi)
        self.sub_none = User.objects.create_user(
            username="bs_none@test.com", email="bs_none@test.com", password="x",
            full_name_ar="مشرف بلا دفعة", role=User.Role.SUB_ADMIN,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        self.student_b2 = User.objects.create_user(
            username="bs_s2@test.com", email="bs_s2@test.com", password="x",
            full_name_ar="طالب دفعة 2", role=User.Role.STUDENT,
            is_approved=User.ApprovalStatus.APPROVED, batch=self.batch2,
        )

    def test_zero_batch_sub_admin_cannot_view_or_edit_students(self):
        """Was fail-open: batch=None skipped the guard entirely."""
        self.client.force_login(self.sub_none)
        r = self.client.get(reverse("accounts:admin_student_detail", args=[self.student_b2.pk]))
        self.assertEqual(r.status_code, 403)
        r = self.client.get(reverse("accounts:admin_student_edit", args=[self.student_b2.pk]))
        self.assertEqual(r.status_code, 403)

    def test_multi_batch_sub_admin_reaches_second_batch_student(self):
        """Was wrong-deny: only the 'first' supervised batch passed."""
        self.client.force_login(self.sub_multi)
        r = self.client.get(reverse("accounts:admin_student_detail", args=[self.student_b2.pk]))
        self.assertEqual(r.status_code, 200)
        r = self.client.get(reverse("accounts:admin_student_edit", args=[self.student_b2.pk]))
        self.assertEqual(r.status_code, 200)

    def test_sub_admin_cannot_hijack_member_from_other_batch(self):
        """C1: assign_users must not move users out of foreign batches."""
        self.client.force_login(self.sub_multi)
        # sub_multi supervises batch1; student_b2 belongs to batch2 which
        # sub_multi ALSO supervises — so use a batch they don't supervise.
        batch3 = Batch.objects.create(
            name="دفعة 3", number=3, year=2026, created_by=self.main_admin,
        )
        victim = User.objects.create_user(
            username="bs_v@test.com", email="bs_v@test.com", password="x",
            full_name_ar="طالب دفعة 3", role=User.Role.STUDENT,
            is_approved=User.ApprovalStatus.APPROVED, batch=batch3,
        )
        r = self.client.post(
            reverse("accounts:admin_batch_detail", args=[self.batch1.pk]),
            {"action": "assign_users", "user_ids": [str(victim.pk)]},
        )
        victim.refresh_from_db()
        self.assertEqual(victim.batch_id, batch3.pk, "sub-admin stole a member from another batch")

    def test_sub_admin_can_claim_unassigned_member(self):
        self.client.force_login(self.sub_multi)
        free_agent = User.objects.create_user(
            username="bs_f@test.com", email="bs_f@test.com", password="x",
            full_name_ar="طالب بلا دفعة", role=User.Role.STUDENT,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        self.client.post(
            reverse("accounts:admin_batch_detail", args=[self.batch1.pk]),
            {"action": "assign_users", "user_ids": [str(free_agent.pk)]},
        )
        free_agent.refresh_from_db()
        self.assertEqual(free_agent.batch_id, self.batch1.pk)

    def test_main_admin_can_still_move_members_across_batches(self):
        self.client.force_login(self.main_admin)
        self.client.post(
            reverse("accounts:admin_batch_detail", args=[self.batch1.pk]),
            {"action": "assign_users", "user_ids": [str(self.student_b2.pk)]},
        )
        self.student_b2.refresh_from_db()
        self.assertEqual(self.student_b2.batch_id, self.batch1.pk)

    def test_zero_batch_sub_admin_sees_no_circles(self):
        Circle.objects.create(name="حلقة دفعة 2", batch=self.batch2, status=Circle.Status.ACTIVE)
        self.client.force_login(self.sub_none)
        r = self.client.get(reverse("accounts:admin_circles"))
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "حلقة دفعة 2")

    def test_multi_batch_sub_admin_sees_both_batches_circles(self):
        Circle.objects.create(name="حلقة الدفعة الأولى", batch=self.batch1, status=Circle.Status.ACTIVE)
        Circle.objects.create(name="حلقة الدفعة الثانية", batch=self.batch2, status=Circle.Status.ACTIVE)
        self.client.force_login(self.sub_multi)
        r = self.client.get(reverse("accounts:admin_circles"))
        self.assertContains(r, "حلقة الدفعة الأولى")
        self.assertContains(r, "حلقة الدفعة الثانية")

    def test_enroll_api_batch_mismatch_returns_400(self):
        """H2: was a raw Django ValidationError → 500 through DRF."""
        from apps.circles.models import CircleEnrollment
        circle_b1 = Circle.objects.create(
            name="حلقة الدفعة 1", batch=self.batch1, status=Circle.Status.ACTIVE,
        )
        self.client.force_login(self.main_admin)
        r = self.client.post(
            f"/api/v1/circles/{circle_b1.pk}/enroll/",
            {"student_id": str(self.student_b2.pk)},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400, r.content)
        self.assertFalse(
            CircleEnrollment.objects.filter(circle=circle_b1, student=self.student_b2).exists()
        )


class BatchScopingCoverageTests(TestCase):
    """Close the review's coverage gaps: teacher views, circle detail,
    circle create branching, and null-batch targets."""

    def setUp(self):
        self.main_admin = User.objects.create_user(
            username="bc_admin@test.com", email="bc_admin@test.com", password="x",
            full_name_ar="مدير", role=User.Role.MAIN_ADMIN,
            is_approved=User.ApprovalStatus.APPROVED, is_staff=True,
        )
        self.batch1 = Batch.objects.create(
            name="دفعة أ", number=11, year=2026, created_by=self.main_admin,
        )
        self.batch2 = Batch.objects.create(
            name="دفعة ب", number=12, year=2026, created_by=self.main_admin,
        )
        self.sub_multi = User.objects.create_user(
            username="bc_multi@test.com", email="bc_multi@test.com", password="x",
            full_name_ar="مشرف متعدد", role=User.Role.SUB_ADMIN,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        self.batch1.sub_admins.add(self.sub_multi)
        self.batch2.sub_admins.add(self.sub_multi)
        self.sub_none = User.objects.create_user(
            username="bc_none@test.com", email="bc_none@test.com", password="x",
            full_name_ar="مشرف بلا دفعة", role=User.Role.SUB_ADMIN,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        self.teacher_b2 = User.objects.create_user(
            username="bc_t2@test.com", email="bc_t2@test.com", password="x",
            full_name_ar="معلم دفعة ب", role=User.Role.TEACHER,
            is_approved=User.ApprovalStatus.APPROVED, batch=self.batch2,
        )
        self.circle_b2 = Circle.objects.create(
            name="حلقة دفعة ب", batch=self.batch2, status=Circle.Status.ACTIVE,
        )

    # ── teacher detail/edit mirror the student pair ─────────────────────
    def test_zero_batch_sub_admin_denied_on_teacher_views(self):
        self.client.force_login(self.sub_none)
        r = self.client.get(reverse("accounts:admin_teacher_detail", args=[self.teacher_b2.pk]))
        self.assertEqual(r.status_code, 403)
        r = self.client.get(reverse("accounts:admin_teacher_edit", args=[self.teacher_b2.pk]))
        self.assertEqual(r.status_code, 403)

    def test_multi_batch_sub_admin_reaches_second_batch_teacher(self):
        self.client.force_login(self.sub_multi)
        r = self.client.get(reverse("accounts:admin_teacher_detail", args=[self.teacher_b2.pk]))
        self.assertEqual(r.status_code, 200)
        r = self.client.get(reverse("accounts:admin_teacher_edit", args=[self.teacher_b2.pk]))
        self.assertEqual(r.status_code, 200)

    # ── circle detail object guard ──────────────────────────────────────
    def test_circle_detail_scoping(self):
        self.client.force_login(self.sub_none)
        r = self.client.get(reverse("accounts:admin_circle_detail", args=[self.circle_b2.pk]))
        self.assertEqual(r.status_code, 403)
        self.client.force_login(self.sub_multi)
        r = self.client.get(reverse("accounts:admin_circle_detail", args=[self.circle_b2.pk]))
        self.assertEqual(r.status_code, 200)

    # ── null-batch target: not theirs to touch ──────────────────────────
    def test_null_batch_target_denied_for_sub_admins(self):
        floater = User.objects.create_user(
            username="bc_f@test.com", email="bc_f@test.com", password="x",
            full_name_ar="طالب بلا دفعة", role=User.Role.STUDENT,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        for sub in (self.sub_multi, self.sub_none):
            self.client.force_login(sub)
            r = self.client.get(reverse("accounts:admin_student_detail", args=[floater.pk]))
            self.assertEqual(r.status_code, 403, f"{sub.email} reached a batch-less student")
        self.client.force_login(self.main_admin)
        r = self.client.get(reverse("accounts:admin_student_detail", args=[floater.pk]))
        self.assertEqual(r.status_code, 200)

    # ── circle create branching ─────────────────────────────────────────
    def _create_circle(self, name, batch_field=""):
        return self.client.post(reverse("accounts:admin_circle_create"), {
            "name": name, "gender": "male", "max_students": "20",
            "status": "active", "circle_type": "hifd", "batch": batch_field,
        })

    def test_zero_batch_sub_admin_cannot_create_circle(self):
        self.client.force_login(self.sub_none)
        r = self._create_circle("حلقة يتيمة")
        self.assertEqual(r.status_code, 200)  # re-rendered with errors
        self.assertFalse(Circle.objects.filter(name="حلقة يتيمة").exists())

    def test_multi_batch_sub_admin_picks_second_batch(self):
        self.client.force_login(self.sub_multi)
        self._create_circle("حلقة الاختيار", batch_field=str(self.batch2.pk))
        c = Circle.objects.get(name="حلقة الاختيار")
        self.assertEqual(c.batch_id, self.batch2.pk)

    def test_sub_admin_foreign_batch_falls_back_to_own(self):
        foreign = Batch.objects.create(
            name="دفعة أجنبية", number=13, year=2026, created_by=self.main_admin,
        )
        self.client.force_login(self.sub_multi)
        self._create_circle("حلقة محاولة اختراق", batch_field=str(foreign.pk))
        c = Circle.objects.get(name="حلقة محاولة اختراق")
        self.assertNotEqual(c.batch_id, foreign.pk)
        self.assertIn(c.batch_id, [self.batch1.pk, self.batch2.pk])

    def test_garbage_batch_id_does_not_crash(self):
        self.client.force_login(self.sub_multi)
        r = self._create_circle("حلقة قيمة تالفة", batch_field="not-a-number")
        self.assertIn(r.status_code, (200, 302))
        c = Circle.objects.get(name="حلقة قيمة تالفة")
        self.assertIn(c.batch_id, [self.batch1.pk, self.batch2.pk])


class ExamScopingSecurityTests(TestCase):
    """A sub-admin must not read or re-point exams outside the batches they
    supervise — including exams with no circle (batch-less)."""

    def setUp(self):
        from apps.exams.models import Exam

        self.Exam = Exam
        self.main_admin = User.objects.create_user(
            username="ex_admin@test.com", email="ex_admin@test.com", password="x",
            full_name_ar="مدير", role=User.Role.MAIN_ADMIN,
            is_approved=User.ApprovalStatus.APPROVED, is_staff=True,
        )
        self.batch_own = Batch.objects.create(
            name="دفعتي", number=21, year=2026, created_by=self.main_admin,
        )
        self.batch_foreign = Batch.objects.create(
            name="دفعة أجنبية", number=22, year=2026, created_by=self.main_admin,
        )
        self.sub = User.objects.create_user(
            username="ex_sub@test.com", email="ex_sub@test.com", password="x",
            full_name_ar="مشرف", role=User.Role.SUB_ADMIN,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        self.batch_own.sub_admins.add(self.sub)
        self.circle_own = Circle.objects.create(
            name="حلقتي", batch=self.batch_own, status=Circle.Status.ACTIVE,
        )
        self.circle_foreign = Circle.objects.create(
            name="حلقة أجنبية", batch=self.batch_foreign, status=Circle.Status.ACTIVE,
        )
        self.exam_foreign = Exam.objects.create(
            title="امتحان أجنبي", circle=self.circle_foreign, created_by=self.main_admin,
        )
        self.exam_own = Exam.objects.create(
            title="امتحاني", circle=self.circle_own, created_by=self.main_admin,
        )
        self.exam_no_circle = Exam.objects.create(
            title="امتحان بلا حلقة", circle=None, created_by=self.main_admin,
        )

    def test_sub_admin_cannot_view_foreign_exam(self):
        self.client.force_login(self.sub)
        r = self.client.get(reverse("accounts:admin_exam_detail", args=[self.exam_foreign.pk]))
        self.assertEqual(r.status_code, 403)

    def test_sub_admin_cannot_view_batchless_exam(self):
        self.client.force_login(self.sub)
        r = self.client.get(reverse("accounts:admin_exam_detail", args=[self.exam_no_circle.pk]))
        self.assertEqual(r.status_code, 403)

    def test_main_admin_can_view_batchless_exam(self):
        self.client.force_login(self.main_admin)
        r = self.client.get(reverse("accounts:admin_exam_detail", args=[self.exam_no_circle.pk]))
        self.assertEqual(r.status_code, 200)

    def test_sub_admin_cannot_edit_foreign_exam(self):
        self.client.force_login(self.sub)
        r = self.client.get(reverse("accounts:admin_exam_edit", args=[self.exam_foreign.pk]))
        self.assertEqual(r.status_code, 403)

    # ── self-lockout guard: a sub-admin's exam must carry a circle, else the
    # post-create redirect to the detail page 403s its own creator ─────────
    def test_sub_admin_cannot_create_batchless_exam(self):
        self.client.force_login(self.sub)
        r = self.client.post(reverse("accounts:admin_exam_create"), {
            "title": "امتحان بلا حلقة جديد", "circle": "",
        })
        self.assertEqual(r.status_code, 200)
        self.assertIn("متاح للمشرف العام فقط", r.context["error"])
        self.assertFalse(self.Exam.objects.filter(title="امتحان بلا حلقة جديد").exists())

    def test_sub_admin_creates_exam_in_own_batch_and_can_open_it(self):
        self.client.force_login(self.sub)
        r = self.client.post(reverse("accounts:admin_exam_create"), {
            "title": "امتحان دفعتي", "circle": self.circle_own.pk,
        }, follow=True)
        self.assertEqual(r.status_code, 200)  # detail page renders, no 403
        self.assertTrue(self.Exam.objects.filter(title="امتحان دفعتي").exists())

    def test_sub_admin_cannot_clear_circle_on_edit(self):
        self.client.force_login(self.sub)
        r = self.client.post(reverse("accounts:admin_exam_edit", args=[self.exam_own.pk]), {
            "title": "امتحاني", "circle": "",
        })
        self.assertEqual(r.status_code, 200)
        self.exam_own.refresh_from_db()
        self.assertEqual(self.exam_own.circle_id, self.circle_own.pk)

    def test_main_admin_can_create_batchless_exam(self):
        self.client.force_login(self.main_admin)
        r = self.client.post(reverse("accounts:admin_exam_create"), {
            "title": "امتحان عام جديد", "circle": "",
        }, follow=True)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(self.Exam.objects.filter(title="امتحان عام جديد").exists())

    def test_sub_admin_cannot_repoint_own_exam_to_foreign_circle(self):
        self.client.force_login(self.sub)
        r = self.client.post(
            reverse("accounts:admin_exam_edit", args=[self.exam_own.pk]),
            {
                "title": "امتحاني", "exam_type": "monthly",
                "circle": str(self.circle_foreign.pk),
                "exam_date": "2026-07-11", "max_marks": "100", "pass_percentage": "50",
            },
        )
        self.assertEqual(r.status_code, 200)  # re-rendered with error, not saved
        self.exam_own.refresh_from_db()
        self.assertEqual(self.exam_own.circle_id, self.circle_own.pk)

    def test_sub_admin_create_form_hides_foreign_circle(self):
        self.client.force_login(self.sub)
        r = self.client.get(reverse("accounts:admin_exam_create"))
        self.assertEqual(r.status_code, 200)
        circle_ids = {c.pk for c in r.context["circles"]}
        self.assertIn(self.circle_own.pk, circle_ids)
        self.assertNotIn(self.circle_foreign.pk, circle_ids)

    # ── regression: these write paths raised NameError in the god-file
    #    (service functions were used but never imported) ────────────────
    def test_create_exam_post_succeeds(self):
        self.client.force_login(self.main_admin)
        r = self.client.post(reverse("accounts:admin_exam_create"), {
            "title": "امتحان جديد", "exam_type": "monthly",
            "circle": str(self.circle_own.pk),
            "exam_date": "2026-07-11", "max_marks": "100", "pass_percentage": "50",
        })
        self.assertEqual(r.status_code, 302)
        self.assertTrue(self.Exam.objects.filter(title="امتحان جديد").exists())

    def test_publish_exam_succeeds(self):
        self.client.force_login(self.main_admin)
        r = self.client.post(reverse("accounts:admin_exam_publish", args=[self.exam_own.pk]))
        self.assertEqual(r.status_code, 302)
        self.exam_own.refresh_from_db()
        self.assertEqual(self.exam_own.status, self.Exam.Status.PUBLISHED)

    # ── new guards on the remaining exam actions ────────────────────────
    def test_sub_admin_cannot_delete_foreign_exam(self):
        self.client.force_login(self.sub)
        r = self.client.post(reverse("accounts:admin_exam_delete", args=[self.exam_foreign.pk]))
        self.assertEqual(r.status_code, 403)
        self.assertTrue(self.Exam.objects.filter(pk=self.exam_foreign.pk).exists())

    def test_sub_admin_cannot_publish_foreign_exam(self):
        self.client.force_login(self.sub)
        r = self.client.post(reverse("accounts:admin_exam_publish", args=[self.exam_foreign.pk]))
        self.assertEqual(r.status_code, 403)

    # ── edit save (parse_date happy path) ───────────────────────────────
    def test_admin_exam_edit_saves_valid_changes(self):
        self.client.force_login(self.main_admin)
        r = self.client.post(
            reverse("accounts:admin_exam_edit", args=[self.exam_own.pk]),
            {
                "title": "عنوان محدّث", "exam_type": "final",
                "circle": str(self.circle_own.pk),
                "exam_date": "2026-08-01", "max_marks": "120", "pass_percentage": "60",
            },
        )
        self.assertEqual(r.status_code, 302)
        self.exam_own.refresh_from_db()
        self.assertEqual(self.exam_own.title, "عنوان محدّث")
        self.assertEqual(str(self.exam_own.exam_date), "2026-08-01")
        self.assertEqual(self.exam_own.max_marks, 120)
        self.assertEqual(self.exam_own.pass_percentage, 60)

    # ── malformed input re-renders instead of raising a 500 ─────────────
    def test_admin_exam_create_invalid_date_re_renders(self):
        self.client.force_login(self.main_admin)
        r = self.client.post(reverse("accounts:admin_exam_create"), {
            "title": "امتحان بتاريخ خاطئ", "exam_type": "monthly",
            "circle": str(self.circle_own.pk),
            "exam_date": "2026-13-40", "max_marks": "100", "pass_percentage": "50",
        })
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "تاريخ الامتحان غير صالح")
        self.assertFalse(self.Exam.objects.filter(title="امتحان بتاريخ خاطئ").exists())

    def test_admin_exam_create_invalid_marks_re_renders(self):
        self.client.force_login(self.main_admin)
        r = self.client.post(reverse("accounts:admin_exam_create"), {
            "title": "امتحان بدرجة خاطئة", "exam_type": "monthly",
            "circle": str(self.circle_own.pk),
            "exam_date": "2026-07-11", "max_marks": "abc", "pass_percentage": "50",
        })
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "أرقاماً")
        self.assertFalse(self.Exam.objects.filter(title="امتحان بدرجة خاطئة").exists())

    # ── approve-all / reject write paths (also NameError regressions) ───
    def _make_pending_mark(self, exam):
        from apps.exams.models import ExamMark
        student = User.objects.create_user(
            username="ex_student@test.com", email="ex_student@test.com", password="x",
            full_name_ar="طالب", role=User.Role.STUDENT,
            is_approved=User.ApprovalStatus.APPROVED, batch=self.batch_own,
        )
        return ExamMark.objects.create(
            exam=exam, student=student, marks_obtained=80,
            status=ExamMark.Status.PENDING, entered_by=self.main_admin,
        )

    def test_admin_exam_approve_all_marks_succeeds(self):
        from apps.exams.models import ExamMark
        mark = self._make_pending_mark(self.exam_own)
        self.client.force_login(self.main_admin)
        r = self.client.post(reverse("accounts:admin_exam_approve_all", args=[self.exam_own.pk]))
        self.assertEqual(r.status_code, 302)
        mark.refresh_from_db()
        self.assertEqual(mark.status, ExamMark.Status.APPROVED)

    def test_admin_exam_reject_marks_succeeds(self):
        from apps.exams.models import ExamMark
        mark = self._make_pending_mark(self.exam_own)
        self.client.force_login(self.main_admin)
        r = self.client.post(
            reverse("accounts:admin_exam_reject_marks", args=[self.exam_own.pk]),
            {"mark_ids": [str(mark.pk)], "reason": "إعادة التصحيح"},
        )
        self.assertEqual(r.status_code, 302)
        mark.refresh_from_db()
        self.assertEqual(mark.status, ExamMark.Status.REJECTED)

    # ── destructive actions must reject GET (CSRF-safe: POST-only) ───────
    def test_exam_delete_ignores_get(self):
        self.client.force_login(self.main_admin)
        r = self.client.get(reverse("accounts:admin_exam_delete", args=[self.exam_own.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertTrue(self.Exam.objects.filter(pk=self.exam_own.pk).exists())

    def test_exam_publish_ignores_get(self):
        self.client.force_login(self.main_admin)
        r = self.client.get(reverse("accounts:admin_exam_publish", args=[self.exam_own.pk]))
        self.assertEqual(r.status_code, 302)
        self.exam_own.refresh_from_db()
        self.assertNotEqual(self.exam_own.status, self.Exam.Status.PUBLISHED)

    def test_exam_approve_all_ignores_get(self):
        from apps.exams.models import ExamMark
        mark = self._make_pending_mark(self.exam_own)
        self.client.force_login(self.main_admin)
        r = self.client.get(reverse("accounts:admin_exam_approve_all", args=[self.exam_own.pk]))
        self.assertEqual(r.status_code, 302)
        mark.refresh_from_db()
        self.assertEqual(mark.status, ExamMark.Status.PENDING)

    # ── report_exam_results must be batch-scoped ────────────────────────
    def _approved_mark(self, exam, student):
        from apps.exams.models import ExamMark
        exam.status = self.Exam.Status.COMPLETED
        exam.save(update_fields=["status"])
        return ExamMark.objects.create(
            exam=exam, student=student, marks_obtained=90,
            status=ExamMark.Status.APPROVED, entered_by=self.main_admin,
            approved_by=self.main_admin,
        )

    def test_report_results_scoped_for_sub_admin(self):
        student_own = User.objects.create_user(
            username="rep_own@test.com", email="rep_own@test.com", password="x",
            full_name_ar="طالب دفعتي", role=User.Role.STUDENT,
            is_approved=User.ApprovalStatus.APPROVED, batch=self.batch_own,
        )
        student_foreign = User.objects.create_user(
            username="rep_foreign@test.com", email="rep_foreign@test.com", password="x",
            full_name_ar="طالب أجنبي", role=User.Role.STUDENT,
            is_approved=User.ApprovalStatus.APPROVED, batch=self.batch_foreign,
        )
        self._approved_mark(self.exam_own, student_own)
        self._approved_mark(self.exam_foreign, student_foreign)
        self.client.force_login(self.sub)
        r = self.client.get(reverse("accounts:report_exam_results"))
        self.assertEqual(r.status_code, 200)
        students = {row["student"].pk for row in r.context["exam_data"]}
        self.assertIn(student_own.pk, students)
        self.assertNotIn(student_foreign.pk, students)

    def test_report_results_unscoped_for_main_admin(self):
        student_own = User.objects.create_user(
            username="rep_own2@test.com", email="rep_own2@test.com", password="x",
            full_name_ar="طالب دفعتي", role=User.Role.STUDENT,
            is_approved=User.ApprovalStatus.APPROVED, batch=self.batch_own,
        )
        student_foreign = User.objects.create_user(
            username="rep_foreign2@test.com", email="rep_foreign2@test.com", password="x",
            full_name_ar="طالب أجنبي", role=User.Role.STUDENT,
            is_approved=User.ApprovalStatus.APPROVED, batch=self.batch_foreign,
        )
        self._approved_mark(self.exam_own, student_own)
        self._approved_mark(self.exam_foreign, student_foreign)
        self.client.force_login(self.main_admin)
        r = self.client.get(reverse("accounts:report_exam_results"))
        students = {row["student"].pk for row in r.context["exam_data"]}
        self.assertIn(student_own.pk, students)
        self.assertIn(student_foreign.pk, students)

    # ── reject_marks must not 500 on tampered mark_ids ──────────────────
    def test_reject_marks_invalid_ids_does_not_crash(self):
        self.client.force_login(self.main_admin)
        r = self.client.post(
            reverse("accounts:admin_exam_reject_marks", args=[self.exam_own.pk]),
            {"mark_ids": ["not-a-number"], "reason": "x"},
        )
        self.assertEqual(r.status_code, 302)  # graceful redirect, not a 500


class SupervisorGroupsIDORTests(TestCase):
    """`?batch=` on the supervisor board must be clamped to the supervised set,
    and the batch list must include M2M-supervised batches, not just the legacy FK."""

    def setUp(self):
        self.main_admin = User.objects.create_user(
            username="sg_admin@test.com", email="sg_admin@test.com", password="x",
            full_name_ar="مدير", role=User.Role.MAIN_ADMIN,
            is_approved=User.ApprovalStatus.APPROVED, is_staff=True,
        )
        self.batch_own = Batch.objects.create(
            name="دفعتي", number=31, year=2026, created_by=self.main_admin,
        )
        self.batch_foreign = Batch.objects.create(
            name="دفعة أجنبية", number=32, year=2026, created_by=self.main_admin,
        )
        self.sub = User.objects.create_user(
            username="sg_sub@test.com", email="sg_sub@test.com", password="x",
            full_name_ar="مشرف", role=User.Role.SUB_ADMIN,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        # Supervised only through the M2M relation (legacy FK left null).
        self.batch_own.sub_admins.add(self.sub)
        self.circle_own = Circle.objects.create(
            name="حلقتي", batch=self.batch_own, status=Circle.Status.ACTIVE,
        )
        self.circle_foreign = Circle.objects.create(
            name="حلقة أجنبية", batch=self.batch_foreign, status=Circle.Status.ACTIVE,
        )

    def test_m2m_supervised_batch_appears(self):
        self.client.force_login(self.sub)
        r = self.client.get(reverse("accounts:supervisor_groups"))
        self.assertEqual(r.status_code, 200)
        batch_ids = {b.pk for b in r.context["batches"]}
        self.assertIn(self.batch_own.pk, batch_ids)

    def test_foreign_batch_query_is_clamped(self):
        self.client.force_login(self.sub)
        r = self.client.get(
            reverse("accounts:supervisor_groups") + f"?batch={self.batch_foreign.pk}"
        )
        self.assertEqual(r.status_code, 200)
        # Clamped back to a supervised batch — the foreign circle never leaks.
        self.assertEqual(r.context["selected_batch"], self.batch_own.pk)
        group_names = {g["circle"].name for g in r.context["groups"]}
        self.assertNotIn(self.circle_foreign.name, group_names)


class CommunicationsScopingTests(TestCase):
    """A SUB_ADMIN must only see support requests submitted by — and
    notifications sent to — users in the batches they supervise."""

    def setUp(self):
        from apps.requests.models import SupportRequest
        from apps.notifications.models import Notification

        self.SupportRequest = SupportRequest
        self.Notification = Notification
        self.main_admin = User.objects.create_user(
            username="cm_admin@test.com", email="cm_admin@test.com", password="x",
            full_name_ar="مدير", role=User.Role.MAIN_ADMIN,
            is_approved=User.ApprovalStatus.APPROVED, is_staff=True,
        )
        self.batch_own = Batch.objects.create(
            name="دفعتي", number=41, year=2026, created_by=self.main_admin,
        )
        self.batch_foreign = Batch.objects.create(
            name="دفعة أجنبية", number=42, year=2026, created_by=self.main_admin,
        )
        self.sub = User.objects.create_user(
            username="cm_sub@test.com", email="cm_sub@test.com", password="x",
            full_name_ar="مشرف", role=User.Role.SUB_ADMIN,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        self.batch_own.sub_admins.add(self.sub)
        self.student_own = User.objects.create_user(
            username="cm_own@test.com", email="cm_own@test.com", password="x",
            full_name_ar="طالب دفعتي", role=User.Role.STUDENT,
            is_approved=User.ApprovalStatus.APPROVED, batch=self.batch_own,
        )
        self.student_foreign = User.objects.create_user(
            username="cm_foreign@test.com", email="cm_foreign@test.com", password="x",
            full_name_ar="طالب أجنبي", role=User.Role.STUDENT,
            is_approved=User.ApprovalStatus.APPROVED, batch=self.batch_foreign,
        )
        self.req_own = SupportRequest.objects.create(
            submitted_by=self.student_own, title="طلب من دفعتي",
        )
        self.req_foreign = SupportRequest.objects.create(
            submitted_by=self.student_foreign, title="طلب أجنبي",
        )
        self.notif_own = Notification.objects.create(
            recipient=self.student_own, type=Notification.Type.SYSTEM,
            title="إشعار دفعتي", message="…",
        )
        self.notif_foreign = Notification.objects.create(
            recipient=self.student_foreign, type=Notification.Type.SYSTEM,
            title="إشعار أجنبي", message="…",
        )

    def test_sub_admin_requests_list_hides_foreign(self):
        self.client.force_login(self.sub)
        r = self.client.get(reverse("accounts:admin_requests"))
        self.assertEqual(r.status_code, 200)
        titles = {req.title for req in r.context["requests"]}
        self.assertIn("طلب من دفعتي", titles)
        self.assertNotIn("طلب أجنبي", titles)
        self.assertEqual(r.context["total_count"], 1)

    def test_main_admin_requests_list_sees_all(self):
        self.client.force_login(self.main_admin)
        r = self.client.get(reverse("accounts:admin_requests"))
        self.assertEqual(r.context["total_count"], 2)

    def test_sub_admin_cannot_open_foreign_request_detail(self):
        self.client.force_login(self.sub)
        r = self.client.get(
            reverse("accounts:admin_request_detail", args=[self.req_foreign.pk])
        )
        self.assertEqual(r.status_code, 404)

    def test_sub_admin_can_open_own_request_detail(self):
        self.client.force_login(self.sub)
        r = self.client.get(
            reverse("accounts:admin_request_detail", args=[self.req_own.pk])
        )
        self.assertEqual(r.status_code, 200)

    def test_whitespace_only_comment_is_ignored(self):
        self.client.force_login(self.sub)
        self.client.post(
            reverse("accounts:admin_request_detail", args=[self.req_own.pk]),
            {"comment_body": "   "},
        )
        self.assertEqual(self.req_own.comments.count(), 0)

    def test_sub_admin_notifications_list_hides_foreign(self):
        self.client.force_login(self.sub)
        r = self.client.get(reverse("accounts:admin_notifications"))
        self.assertEqual(r.status_code, 200)
        titles = {n.title for n in r.context["notifications"]}
        self.assertIn("إشعار دفعتي", titles)
        self.assertNotIn("إشعار أجنبي", titles)

    # ── broadcast create is scoped to the sub-admin's batch (#4) ─────────
    def test_sub_admin_broadcast_scoped_to_own_batch(self):
        self.client.force_login(self.sub)
        self.client.post(reverse("accounts:admin_notification_create"), {
            "type": "system", "title": "بث", "message": "رسالة", "target": "students",
        })
        self.assertTrue(
            self.Notification.objects.filter(recipient=self.student_own, title="بث").exists()
        )
        self.assertFalse(
            self.Notification.objects.filter(recipient=self.student_foreign, title="بث").exists()
        )

    def test_main_admin_broadcast_reaches_all_batches(self):
        self.client.force_login(self.main_admin)
        self.client.post(reverse("accounts:admin_notification_create"), {
            "type": "system", "title": "بث٢", "message": "رسالة", "target": "students",
        })
        self.assertTrue(
            self.Notification.objects.filter(recipient=self.student_own, title="بث٢").exists()
        )
        self.assertTrue(
            self.Notification.objects.filter(recipient=self.student_foreign, title="بث٢").exists()
        )

    # ── unreachable/empty broadcast targets fail loudly, never silently ──
    def test_sub_admin_broadcast_to_admins_rejected(self):
        # admin/supervisor accounts have no User.batch, so batch scoping would
        # always empty these targets — the view must refuse, not no-op.
        self.client.force_login(self.sub)
        for target in ("admins", "supervisors"):
            r = self.client.post(reverse("accounts:admin_notification_create"), {
                "type": "system", "title": "بث٣", "message": "رسالة", "target": target,
            })
            self.assertEqual(r.status_code, 200)
            self.assertIn("نطاق إشرافك", r.context["error"])
        self.assertFalse(self.Notification.objects.filter(title="بث٣").exists())

    def test_zero_recipient_broadcast_shows_error_not_silent_redirect(self):
        # No teachers exist in the sub-admin's batch → zero recipients.
        self.client.force_login(self.sub)
        r = self.client.post(reverse("accounts:admin_notification_create"), {
            "type": "system", "title": "بث٤", "message": "رسالة", "target": "teachers",
        })
        self.assertEqual(r.status_code, 200)
        self.assertIn("لا يوجد مستلمون", r.context["error"])
        self.assertFalse(self.Notification.objects.filter(title="بث٤").exists())

    def test_successful_broadcast_reports_recipient_count(self):
        self.client.force_login(self.sub)
        r = self.client.post(reverse("accounts:admin_notification_create"), {
            "type": "system", "title": "بث٥", "message": "رسالة", "target": "students",
        }, follow=True)
        msgs = [str(m) for m in r.context["messages"]]
        self.assertTrue(any("تم إرسال الإشعار إلى 1" in m for m in msgs), msgs)


class TeacherExamGradingTests(TestCase):
    """Regression: teacher_exam_grade/submit/export referenced exam service
    helpers (verify_teacher_assignment, save_mark, …) that were never imported
    into accounts.views.teacher — every teacher grading route raised
    NameError (500). These exercise the grade → submit write path end to end."""

    def setUp(self):
        from apps.circles.models import CircleEnrollment
        from apps.exams.models import Exam

        self.Exam = Exam
        self.teacher = User.objects.create_user(
            username="tg_teacher@test.com", email="tg_teacher@test.com", password="x",
            full_name_ar="معلم", role=User.Role.TEACHER,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        self.circle = Circle.objects.create(
            name="حلقة الاختبار", teacher=self.teacher, status=Circle.Status.ACTIVE,
        )
        self.student = User.objects.create_user(
            username="tg_student@test.com", email="tg_student@test.com", password="x",
            full_name_ar="طالب", role=User.Role.STUDENT,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        CircleEnrollment.objects.create(
            circle=self.circle, student=self.student,
            status=CircleEnrollment.Status.ACTIVE,
        )
        self.exam = Exam.objects.create(
            title="امتحان المعلم", circle=self.circle, created_by=self.teacher,
            status=Exam.Status.PUBLISHED, max_marks=100,
        )

    def test_teacher_can_open_grade_page(self):
        self.client.force_login(self.teacher)
        r = self.client.get(reverse("accounts:teacher_exam_grade", args=[self.exam.pk]))
        self.assertEqual(r.status_code, 200)

    def test_teacher_grade_saves_marks(self):
        from apps.exams.models import ExamMark
        self.client.force_login(self.teacher)
        r = self.client.post(
            reverse("accounts:teacher_exam_grade", args=[self.exam.pk]),
            {f"mark_{self.student.id}": "85"},
        )
        self.assertEqual(r.status_code, 302)
        mark = ExamMark.objects.get(exam=self.exam, student=self.student)
        self.assertEqual(mark.marks_obtained, 85)
        self.assertEqual(mark.status, ExamMark.Status.PENDING)
        self.exam.refresh_from_db()
        self.assertEqual(self.exam.status, self.Exam.Status.GRADING)

    def test_teacher_submit_for_approval(self):
        from apps.exams.services import save_mark
        save_mark(
            exam=self.exam, student=self.student, marks_obtained=85,
            entered_by=self.teacher,
        )
        self.exam.status = self.Exam.Status.GRADING
        self.exam.save(update_fields=["status"])
        self.client.force_login(self.teacher)
        r = self.client.post(reverse("accounts:teacher_exam_submit", args=[self.exam.pk]))
        self.assertEqual(r.status_code, 302)
        self.exam.refresh_from_db()
        self.assertEqual(self.exam.status, self.Exam.Status.PENDING_APPROVAL)

    def test_foreign_teacher_cannot_grade(self):
        other = User.objects.create_user(
            username="tg_other@test.com", email="tg_other@test.com", password="x",
            full_name_ar="معلم آخر", role=User.Role.TEACHER,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        self.client.force_login(other)
        r = self.client.get(reverse("accounts:teacher_exam_grade", args=[self.exam.pk]))
        self.assertEqual(r.status_code, 403)


class NotificationRedirectSafetyTests(TestCase):
    """notification_mark_read follows the notification's link on a GET
    click-through — that link is admin-settable, so it must be restricted to
    internal URLs to avoid an open redirect (#5)."""

    def setUp(self):
        from apps.notifications.models import Notification

        self.Notification = Notification
        self.user = User.objects.create_user(
            username="nr_user@test.com", email="nr_user@test.com", password="x",
            full_name_ar="مستخدم", role=User.Role.STUDENT,
            is_approved=User.ApprovalStatus.APPROVED,
        )

    def _notif(self, link):
        return self.Notification.objects.create(
            recipient=self.user, type=self.Notification.Type.SYSTEM,
            title="ت", message="ر", link=link,
        )

    def test_external_link_falls_back_to_dashboard(self):
        n = self._notif("https://evil.example.com/phish")
        self.client.force_login(self.user)
        r = self.client.get(reverse("accounts:notification_mark_read", args=[n.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, "/dashboard/")

    def test_protocol_relative_link_falls_back(self):
        n = self._notif("//evil.example.com")
        self.client.force_login(self.user)
        r = self.client.get(reverse("accounts:notification_mark_read", args=[n.pk]))
        self.assertEqual(r.url, "/dashboard/")

    def test_internal_link_is_followed(self):
        n = self._notif("/dashboard/certificates/own/")
        self.client.force_login(self.user)
        r = self.client.get(reverse("accounts:notification_mark_read", args=[n.pk]))
        self.assertEqual(r.url, "/dashboard/certificates/own/")

    def test_mark_read_marks_notification(self):
        n = self._notif("/dashboard/")
        self.client.force_login(self.user)
        self.client.get(reverse("accounts:notification_mark_read", args=[n.pk]))
        n.refresh_from_db()
        self.assertTrue(n.is_read)


class TeacherProgressCorrectionTests(TestCase):
    """Teachers can now correct session entries after the fact (edit/delete a
    ProgressLog) and drive the SRS layer (evaluate a rub, record a memorized
    rub). Both must rebuild StudentAchievement and stay teacher-scoped."""

    @classmethod
    def setUpTestData(cls):
        from django.core.management import call_command
        call_command("seed_quran")

    def setUp(self):
        from apps.circles.models import Session
        from apps.memorization.engine import create_progress_log
        from apps.memorization.models import ProgressLog, StudentAchievement
        from apps.references.models import Surah

        self.ProgressLog = ProgressLog
        self.StudentAchievement = StudentAchievement
        self.teacher = User.objects.create_user(
            username="pc_t@test.com", email="pc_t@test.com", password="x",
            full_name_ar="معلم", role=User.Role.TEACHER,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        self.other_teacher = User.objects.create_user(
            username="pc_t2@test.com", email="pc_t2@test.com", password="x",
            full_name_ar="معلم آخر", role=User.Role.TEACHER,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        self.student = User.objects.create_user(
            username="pc_s@test.com", email="pc_s@test.com", password="x",
            full_name_ar="طالب", role=User.Role.STUDENT,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        self.circle = Circle.objects.create(
            name="حلقة", teacher=self.teacher, status=Circle.Status.ACTIVE,
        )
        CircleEnrollment.objects.create(
            circle=self.circle, student=self.student,
            status=CircleEnrollment.Status.ACTIVE,
        )
        from datetime import date
        self.session = Session.objects.create(
            circle=self.circle, session_date=date.today(),
        )
        self.log = create_progress_log(
            session=self.session, student=self.student,
            log_category=ProgressLog.Category.HIFDH,
            surah=Surah.objects.get(pk=2), start_ayah=1, end_ayah=25,
            points=12,
        )

    def _achievement(self):
        return self.StudentAchievement.objects.get(student=self.student)

    def test_teacher_edits_log_and_achievement_recomputed(self):
        self.assertEqual(self._achievement().total_hifdh_ayahs, 25)
        self.client.force_login(self.teacher)
        r = self.client.post(
            reverse("accounts:teacher_progress_log_edit", args=[self.log.pk]),
            {"log_category": "HIFDH", "surah": 2, "start_ayah": 1,
             "end_ayah": 10, "points": "18", "teacher_notes": "تصحيح"},
        )
        self.assertEqual(r.status_code, 302)
        self.log.refresh_from_db()
        self.assertEqual(self.log.end_ayah, 10)
        self.assertEqual(float(self.log.points), 18.0)
        self.assertEqual(self.log.updated_by, self.teacher)
        self.assertIsNotNone(self.log.updated_at)
        self.assertEqual(self._achievement().total_hifdh_ayahs, 10)

    def test_foreign_teacher_cannot_edit_or_delete(self):
        self.client.force_login(self.other_teacher)
        r = self.client.get(reverse("accounts:teacher_progress_log_edit", args=[self.log.pk]))
        self.assertEqual(r.status_code, 404)
        r = self.client.post(reverse("accounts:teacher_progress_log_delete", args=[self.log.pk]))
        self.assertEqual(r.status_code, 404)
        self.assertTrue(self.ProgressLog.objects.filter(pk=self.log.pk).exists())

    def test_teacher_deletes_log_and_achievement_recomputed(self):
        self.client.force_login(self.teacher)
        r = self.client.post(reverse("accounts:teacher_progress_log_delete", args=[self.log.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertFalse(self.ProgressLog.objects.filter(pk=self.log.pk).exists())
        self.assertEqual(self._achievement().total_hifdh_ayahs, 0)

    def test_invalid_ayah_range_rerenders_with_error(self):
        self.client.force_login(self.teacher)
        r = self.client.post(
            reverse("accounts:teacher_progress_log_edit", args=[self.log.pk]),
            {"log_category": "HIFDH", "surah": 2, "start_ayah": 1,
             "end_ayah": 999, "points": ""},
        )
        self.assertEqual(r.status_code, 200)  # re-rendered form, no crash
        self.log.refresh_from_db()
        self.assertEqual(self.log.end_ayah, 25)  # unchanged

    def test_teacher_records_memorized_rub_then_evaluates(self):
        from apps.memorization.models import MemorizationRecord, ReviewHistory

        self.client.force_login(self.teacher)
        r = self.client.post(
            reverse("accounts:teacher_record_add", args=[self.student.pk]),
            {"rub_number": 1},
        )
        self.assertEqual(r.status_code, 302)
        record = MemorizationRecord.objects.get(student=self.student, rub__number=1)
        self.assertEqual(record.status, MemorizationRecord.Status.MEMORIZED)
        self.assertIsNotNone(record.next_review_date)

        r = self.client.post(
            reverse("accounts:teacher_record_evaluate", args=[self.student.pk, record.pk]),
            {"evaluation": "ضعيف", "mistakes_count": 4},
        )
        self.assertEqual(r.status_code, 302)
        record.refresh_from_db()
        self.assertEqual(record.status, MemorizationRecord.Status.WEAK)
        self.assertEqual(record.review_count, 1)
        self.assertEqual(ReviewHistory.objects.filter(record=record).count(), 1)

    def test_foreign_teacher_cannot_evaluate(self):
        from apps.memorization.models import MemorizationRecord

        record = MemorizationRecord.record_for(self.student, 1, circle=self.circle)
        record.mark_memorized(by=self.teacher)
        self.client.force_login(self.other_teacher)
        self.client.post(
            reverse("accounts:teacher_record_evaluate", args=[self.student.pk, record.pk]),
            {"evaluation": "ممتاز"},
        )
        record.refresh_from_db()
        self.assertEqual(record.review_count, 0)  # evaluation rejected

    def test_student_progress_page_shows_live_data(self):
        self.client.force_login(self.teacher)
        r = self.client.get(reverse("accounts:teacher_student_progress", args=[self.student.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["stats"]["hifz"], 1)
        self.assertContains(r, "سجل الحصص")


class SessionLogProgressTests(TestCase):
    """The minimal tracking input on the teacher session page: student +
    category + hizb/thumn only."""

    def setUp(self):
        from datetime import date
        self.teacher = User.objects.create_user(
            username="slp_t@test.com", email="slp_t@test.com", password="x",
            full_name_ar="معلم", role=User.Role.TEACHER,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        self.student = User.objects.create_user(
            username="slp_s@test.com", email="slp_s@test.com", password="x",
            full_name_ar="طالب", role=User.Role.STUDENT,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        self.outsider = User.objects.create_user(
            username="slp_o@test.com", email="slp_o@test.com", password="x",
            full_name_ar="طالب خارجي", role=User.Role.STUDENT,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        self.circle = Circle.objects.create(
            name="حلقة", teacher=self.teacher, status=Circle.Status.ACTIVE,
        )
        CircleEnrollment.objects.create(
            circle=self.circle, student=self.student,
            status=CircleEnrollment.Status.ACTIVE,
        )
        self.session = Session.objects.create(circle=self.circle, session_date=date.today())

    def _post(self, **data):
        return self.client.post(
            reverse("accounts:teacher_session_log_progress", args=[self.session.pk]),
            {"student": self.student.pk, "category": "HIFDH", "hizb": 2, "thumn": 3, **data},
        )

    def test_teacher_logs_amount_entry(self):
        from apps.memorization.models import ProgressLog, StudentAchievement
        self.client.force_login(self.teacher)
        r = self._post()
        self.assertEqual(r.status_code, 302)
        log = ProgressLog.objects.get(student=self.student)
        self.assertEqual((log.hizb, log.thumn, log.total_thumns), (2, 3, 19))
        self.assertEqual(log.session_id, self.session.pk)
        self.assertIsNone(log.surah_id)
        ach = StudentAchievement.objects.get(student=self.student)
        self.assertEqual(ach.total_hifdh_thumns, 19)

    def test_non_enrolled_student_rejected(self):
        from apps.memorization.models import ProgressLog
        self.client.force_login(self.teacher)
        self._post(student=self.outsider.pk)
        self.assertFalse(ProgressLog.objects.exists())

    def test_invalid_amount_rejected(self):
        from apps.memorization.models import ProgressLog
        self.client.force_login(self.teacher)
        self._post(hizb=0, thumn=0)
        self._post(thumn=9)
        self.assertFalse(ProgressLog.objects.exists())

    def test_foreign_teacher_404(self):
        foreign = User.objects.create_user(
            username="slp_t2@test.com", email="slp_t2@test.com", password="x",
            full_name_ar="معلم آخر", role=User.Role.TEACHER,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        self.client.force_login(foreign)
        r = self._post()
        self.assertEqual(r.status_code, 404)


class SignupServerSideGuardTests(TestCase):
    """Signup guards that must hold even with JavaScript bypassed."""

    def _data(self, **over):
        base = {
            "full_name_ar": "طالب", "email": "guard@test.com",
            "phone": "0555123456", "gender": "male", "role": "student",
            "password1": "testpass123", "password2": "testpass123",
            "pledge": "on",
        }
        base.update(over)
        return {k: v for k, v in base.items() if v is not None}

    def test_signup_without_pledge_rejected_server_side(self):
        from apps.accounts.forms import SignupForm
        form = SignupForm(self._data(pledge=None))
        self.assertFalse(form.is_valid())
        self.assertIn("التعهد", str(form.errors))

    def test_signup_view_post_creates_pending_user_promptly(self):
        from unittest.mock import patch
        # run the "async" email inline so the test is deterministic
        class InlineThread:
            def __init__(self, target=None, daemon=None):
                self.target = target
            def start(self):
                self.target()
        with patch("apps.accounts.views.auth.send_verification_email", return_value=True) as m, \
             patch("threading.Thread", InlineThread):
            r = self.client.post(reverse("accounts:signup"), self._data())
        self.assertEqual(r.status_code, 302)
        user = User.objects.get(email="guard@test.com")
        self.assertEqual(user.is_approved, User.ApprovalStatus.PENDING)
        self.assertEqual(m.call_count, 1)

    def test_malformed_student_id_on_log_progress_is_400_not_500(self):
        from datetime import date
        teacher = User.objects.create_user(
            username="gt@test.com", email="gt@test.com", password="x",
            full_name_ar="معلم", role=User.Role.TEACHER,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        circle = Circle.objects.create(name="حلقة", teacher=teacher, status=Circle.Status.ACTIVE)
        session = Session.objects.create(circle=circle, session_date=date.today())
        self.client.force_login(teacher)
        r = self.client.post(
            reverse("accounts:teacher_session_log_progress", args=[session.pk]),
            {"student": "not-a-uuid", "category": "HIFDH", "hizb": 1, "thumn": 0},
        )
        self.assertEqual(r.status_code, 302)  # graceful redirect, not 500

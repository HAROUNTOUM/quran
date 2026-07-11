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
from apps.circles.models import Circle, Session
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
        }
        form = SignupForm(data)
        self.assertTrue(form.is_valid(), msg=dict(form.errors))

    def test_signup_empty_full_name(self):
        form = SignupForm(data={"full_name_ar": "", "email": "a@b.com", "phone": "0555123456", "gender": "male", "role": "student", "password1": "testpass123", "password2": "testpass123"})
        self.assertFalse(form.is_valid())

    def test_signup_duplicate_email(self):
        User.objects.create_user(username="existing@test.com", email="existing@test.com", password="test1234", full_name_ar="موجود")
        form = SignupForm(data={"full_name_ar": "جديد", "email": "existing@test.com", "phone": "0555123456", "gender": "male", "role": "student", "password1": "testpass123", "password2": "testpass123"})
        self.assertFalse(form.is_valid())
        self.assertIn("مسجل مسبقاً", str(form.errors))

    def test_signup_short_password(self):
        form = SignupForm(data={"full_name_ar": "أحمد", "email": "a@b.com", "phone": "0555123456", "gender": "male", "role": "student", "password1": "short", "password2": "short"})
        self.assertFalse(form.is_valid())
        self.assertIn("8 أحرف", str(form.errors))

    def test_signup_mismatched_passwords(self):
        form = SignupForm(data={"full_name_ar": "أحمد", "email": "a@b.com", "phone": "0555123456", "gender": "male", "role": "student", "password1": "testpass123", "password2": "different"})
        self.assertFalse(form.is_valid())
        self.assertIn("غير متطابقتين", str(form.errors))

    def test_signup_short_phone(self):
        form = SignupForm(data={"full_name_ar": "أحمد", "email": "a@b.com", "phone": "123", "gender": "male", "role": "student", "password1": "testpass123", "password2": "testpass123"})
        self.assertFalse(form.is_valid())
        self.assertIn("هاتف", str(form.errors))

    def test_signup_email_normalized(self):
        form = SignupForm(data={"full_name_ar": "أحمد", "email": "Test@Example.COM", "phone": "0555123456", "gender": "male", "role": "student", "password1": "testpass123", "password2": "testpass123"})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["email"], "test@example.com")

    def test_signup_saves_user(self):
        form = SignupForm(data={"full_name_ar": "أحمد بن محمد", "email": "ahmed@test.com", "phone": "0555123456", "gender": "male", "role": "student", "password1": "testpass123", "password2": "testpass123"})
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
    AUTH_RATE_LIMIT_ENABLED=True,
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

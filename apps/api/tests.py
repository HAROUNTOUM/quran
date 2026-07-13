from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.circles.models import Circle, CircleEnrollment, Session, SessionTurn
from apps.certificates.models import Certificate, CertificateTemplate
from apps.attendance.models import Attendance
from apps.memorization.models import MemorizationProgress, RecitationGrade
from apps.references.models import Surah, EvaluationCriterion
from apps.requests.models import SupportRequest
from apps.announcements.models import Announcement
from apps.notifications.models import Notification


def create_test_surahs():
    for i in range(1, 5):
        Surah.objects.create(
            id=i, name_ar=f"سورة {i}", name_en=f"Surah {i}",
            ayah_count=10, revelation_type="makki",
        )


def create_test_criteria():
    for name in ["التجويد", "الحفظ", "النغم", "الوقف"]:
        EvaluationCriterion.objects.create(name_ar=name)


class APITestBase(TestCase):
    def setUp(self):
        create_test_surahs()
        create_test_criteria()

        self.unapproved = User.objects.create_user(
            username="pending@test.com", email="pending@test.com",
            password="test1234", full_name_ar="مستخدم معلق",
            role=User.Role.STUDENT, is_approved=User.ApprovalStatus.PENDING,
        )
        self.admin = User.objects.create_user(
            username="admin@test.com", email="admin@test.com",
            password="test1234", full_name_ar="مدير النظام",
            role=User.Role.MAIN_ADMIN, is_approved=User.ApprovalStatus.APPROVED,
        )
        self.supervisor = User.objects.create_user(
            username="supervisor@test.com", email="supervisor@test.com",
            password="test1234", full_name_ar="المشرف",
            role=User.Role.SUB_ADMIN, is_approved=User.ApprovalStatus.APPROVED,
        )
        self.teacher = User.objects.create_user(
            username="teacher@test.com", email="teacher@test.com",
            password="test1234", full_name_ar="المعلم",
            role=User.Role.TEACHER, is_approved=User.ApprovalStatus.APPROVED,
        )
        self.student1 = User.objects.create_user(
            username="student1@test.com", email="student1@test.com",
            password="test1234", full_name_ar="طالب 1",
            role=User.Role.STUDENT, is_approved=User.ApprovalStatus.APPROVED,
        )
        self.student2 = User.objects.create_user(
            username="student2@test.com", email="student2@test.com",
            password="test1234", full_name_ar="طالب 2",
            role=User.Role.STUDENT, is_approved=User.ApprovalStatus.APPROVED,
        )

        self.circle = Circle.objects.create(
            name="الحلقة الأولى", teacher=self.teacher,
            location="المسجد", gender="male", max_students=30,
            status=Circle.Status.ACTIVE,
            schedule_days=["saturday", "monday"],
            schedule_time=timezone.now().time(),
        )
        self.enrollment1 = CircleEnrollment.objects.create(
            circle=self.circle, student=self.student1,
            status=CircleEnrollment.Status.ACTIVE,
        )
        self.enrollment2 = CircleEnrollment.objects.create(
            circle=self.circle, student=self.student2,
            status=CircleEnrollment.Status.ACTIVE,
        )
        self.session = Session.objects.create(
            circle=self.circle, session_date=timezone.now().date(),
        )

        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def login(self):
        resp = self.client.post("/api/v1/auth/login/", {
            "email": self.admin.email, "password": "test1234",
        })
        if resp.status_code == 200:
            token = resp.json()["data"]["access"]
            self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")


class AuthAPITest(APITestBase):
    def test_login_valid(self):
        resp = self.client.post("/api/v1/auth/login/", {
            "email": self.admin.email, "password": "test1234",
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertIn("access", data["data"])
        self.assertIn("refresh", data["data"])

    def test_login_invalid(self):
        resp = self.client.post("/api/v1/auth/login/", {
            "email": self.admin.email, "password": "wrong",
        })
        self.assertEqual(resp.status_code, 401)
        self.assertFalse(resp.json()["success"])

    def test_me_authenticated(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get("/api/v1/auth/me/")
        self.assertEqual(resp.status_code, 200)

    def test_me_unauthenticated(self):
        self.client.force_authenticate(user=None)
        resp = self.client.get("/api/v1/auth/me/")
        self.assertEqual(resp.status_code, 403)


class UserAPITest(APITestBase):
    def test_list_users(self):
        resp = self.client.get("/api/v1/users/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])

    def test_list_users_filter_role(self):
        resp = self.client.get("/api/v1/users/?role=teacher")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(all(u["role"] == "teacher" for u in data["data"]))

    def test_user_stats(self):
        resp = self.client.get("/api/v1/users/stats/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("total_students", data["data"])
        self.assertIn("total_teachers", data["data"])

    def test_teacher_cannot_list_all(self):
        self.client.force_authenticate(user=self.teacher)
        resp = self.client.get("/api/v1/users/")
        self.assertEqual(resp.status_code, 403)


class RegistrationAPITest(APITestBase):
    def test_list_pending(self):
        resp = self.client.get("/api/v1/registration/")
        self.assertEqual(resp.status_code, 200)

    def test_stats(self):
        resp = self.client.get("/api/v1/registration/stats/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("pending_students", data["data"])

    def test_register_anonymous(self):
        self.client.credentials()
        resp = self.client.post("/api/v1/registration/", {
            "full_name_ar": "مستخدم جديد",
            "email": "new@test.com",
            "password": "test1234!",
            "confirm_password": "test1234!",
            "role": "student",
            "gender": "male",
        }, format="json")
        self.assertEqual(resp.status_code, 201)

    def test_approve_registration(self):
        pending = User.objects.create_user(
            username="pend@test.com", email="pend@test.com",
            password="test1234", full_name_ar="معلق",
            role=User.Role.STUDENT, is_approved=User.ApprovalStatus.PENDING,
        )
        resp = self.client.post(f"/api/v1/registration/{pending.id}/approve/")
        self.assertEqual(resp.status_code, 200)
        pending.refresh_from_db()
        self.assertEqual(pending.is_approved, User.ApprovalStatus.APPROVED)

    def test_reject_registration(self):
        pending = User.objects.create_user(
            username="pend2@test.com", email="pend2@test.com",
            password="test1234", full_name_ar="معلق2",
            role=User.Role.STUDENT, is_approved=User.ApprovalStatus.PENDING,
        )
        resp = self.client.post(f"/api/v1/registration/{pending.id}/reject/", {"reason": "مرفوض"}, format="json")
        self.assertEqual(resp.status_code, 200)
        pending.refresh_from_db()
        self.assertEqual(pending.is_approved, User.ApprovalStatus.REJECTED)

    def test_bulk_approve(self):
        for i in range(3):
            User.objects.create_user(
                username=f"bulk{i}@test.com", email=f"bulk{i}@test.com",
                password="test1234", full_name_ar=f"مستخدم {i}",
                role=User.Role.STUDENT, is_approved=User.ApprovalStatus.PENDING,
            )
        resp = self.client.post("/api/v1/registration/bulk/", {"ids": [], "action": "approve"}, format="json")
        self.assertEqual(resp.status_code, 400)


class CircleAPITest(APITestBase):
    def test_list_circles(self):
        resp = self.client.get("/api/v1/circles/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])

    def test_create_circle(self):
        resp = self.client.post("/api/v1/circles/", {
            "name": "حلقة جديدة",
            "teacher_id": str(self.teacher.id),
            "description": "وصف",
            "location": "المسجد",
        }, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Circle.objects.count(), 2)

    def test_circle_students(self):
        resp = self.client.get(f"/api/v1/circles/{self.circle.id}/students/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data["data"]), 2)

    def test_circle_stats(self):
        resp = self.client.get(f"/api/v1/circles/{self.circle.id}/stats/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("attendance_rate", resp.json()["data"])

    def test_enroll_student(self):
        new_student = User.objects.create_user(
            username="newstd@test.com", email="newstd@test.com",
            password="test1234", full_name_ar="طالب جديد",
            role=User.Role.STUDENT, is_approved=User.ApprovalStatus.APPROVED,
        )
        resp = self.client.post(f"/api/v1/circles/{self.circle.id}/enroll/", {
            "student_id": str(new_student.id),
        }, format="json")
        self.assertEqual(resp.status_code, 201)

    def test_remove_student(self):
        resp = self.client.post(f"/api/v1/circles/{self.circle.id}/remove_student/", {
            "student_id": str(self.student1.id),
        }, format="json")
        self.assertEqual(resp.status_code, 200)

    def test_teacher_sees_own_only(self):
        other_teacher = User.objects.create_user(
            username="other@test.com", email="other@test.com",
            password="test1234", full_name_ar="معلم آخر",
            role=User.Role.TEACHER, is_approved=User.ApprovalStatus.APPROVED,
        )
        Circle.objects.create(name="حلقة أخرى", teacher=other_teacher, status=Circle.Status.ACTIVE)
        self.client.force_authenticate(user=self.teacher)
        resp = self.client.get("/api/v1/circles/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["data"]), 1)


class SessionAPITest(APITestBase):
    def test_list_sessions(self):
        resp = self.client.get("/api/v1/sessions/")
        self.assertEqual(resp.status_code, 200)

    def test_create_session(self):
        resp = self.client.post("/api/v1/sessions/", {
            "circle": self.circle.id,
            "session_date": (timezone.now().date() + timedelta(days=1)).isoformat(),
        }, format="json")
        self.assertEqual(resp.status_code, 201)

    def test_submit_attendance(self):
        self.session.status = Session.Status.LIVE
        self.session.save(update_fields=["status"])
        resp = self.client.post(f"/api/v1/sessions/{self.session.id}/submit_attendance/", {
            "records": [
                {"student_id": str(self.student1.id), "status": "present"},
                {"student_id": str(self.student2.id), "status": "absent"},
            ],
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Attendance.objects.count(), 2)

    def test_get_attendance(self):
        Attendance.objects.create(session=self.session, student=self.student1, status="present")
        resp = self.client.get(f"/api/v1/sessions/{self.session.id}/attendance/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["data"]), 1)


class AttendanceAPITest(APITestBase):
    def test_patch_attendance(self):
        att = Attendance.objects.create(session=self.session, student=self.student1, status="present")
        resp = self.client.patch(f"/api/v1/attendance/{att.id}/", {"status": "late"}, format="json")
        self.assertEqual(resp.status_code, 200)
        att.refresh_from_db()
        self.assertEqual(att.status, "late")

    def test_chart_endpoints(self):
        resp = self.client.get("/api/v1/attendance/weekly-chart/")
        self.assertEqual(resp.status_code, 200)
        resp = self.client.get("/api/v1/attendance/general-trend/")
        self.assertEqual(resp.status_code, 200)


class GradeAPITest(APITestBase):
    def test_create_grade(self):
        criterion = EvaluationCriterion.objects.first()
        resp = self.client.post("/api/v1/grades/", {
            "session_id": self.session.id,
            "student_id": str(self.student1.id),
            "criterion_id": criterion.id,
            "score": 85,
            "max_score": 100,
        }, format="json")
        self.assertEqual(resp.status_code, 201)

    def test_teacher_chart(self):
        resp = self.client.get("/api/v1/grades/teacher-chart/")
        self.assertEqual(resp.status_code, 200)

    def test_list_grades(self):
        criterion = EvaluationCriterion.objects.first()
        RecitationGrade.objects.create(
            session=self.session, student=self.student1,
            criterion=criterion, score=90, max_score=100,
        )
        resp = self.client.get("/api/v1/grades/")
        self.assertEqual(resp.status_code, 200)


class RequestAPITest(APITestBase):
    def test_create_request(self):
        resp = self.client.post("/api/v1/requests/", {
            "title": "طلب جديد",
            "body": "محتوى الطلب",
            "type": "technical",
            "priority": "high",
        }, format="json")
        self.assertEqual(resp.status_code, 201)

    def test_list_requests(self):
        SupportRequest.objects.create(submitted_by=self.student1, title="طلب اختبار")
        resp = self.client.get("/api/v1/requests/")
        self.assertEqual(resp.status_code, 200)

    def test_add_comment(self):
        req = SupportRequest.objects.create(submitted_by=self.student1, title="طلب اختبار")
        resp = self.client.post(f"/api/v1/requests/{req.id}/comments/", {"body": "تعليق"}, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(req.comments.count(), 1)


class AnnouncementAPITest(APITestBase):
    def test_list_announcements(self):
        Announcement.objects.create(author=self.admin, title="إعلان 1", body="محتوى")
        resp = self.client.get("/api/v1/announcements/")
        self.assertEqual(resp.status_code, 200)

    def test_create_announcement(self):
        resp = self.client.post("/api/v1/announcements/", {"title": "جديد", "body": "محتوى"}, format="json")
        self.assertEqual(resp.status_code, 201)

    def test_student_cannot_create(self):
        self.client.force_authenticate(user=self.student1)
        resp = self.client.post("/api/v1/announcements/", {"title": "ممنوع", "body": "لا"}, format="json")
        self.assertEqual(resp.status_code, 403)


class NotificationAPITest(APITestBase):
    def test_list_notifications(self):
        Notification.objects.create(
            recipient=self.admin, type=Notification.Type.SYSTEM,
            title="إشعار", message="رسالة",
        )
        resp = self.client.get("/api/v1/notifications/")
        self.assertEqual(resp.status_code, 200)

    def test_count(self):
        resp = self.client.get("/api/v1/notifications/count/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("unread", resp.json()["data"])

    def test_mark_all_read(self):
        Notification.objects.create(
            recipient=self.admin, type=Notification.Type.SYSTEM,
            title="إشعار", message="رسالة", is_read=False,
        )
        resp = self.client.post("/api/v1/notifications/mark_all_read/")
        self.assertEqual(resp.status_code, 200)


class ReportAPITest(APITestBase):
    def test_dashboard_stats(self):
        resp = self.client.get("/api/v1/reports/dashboard-stats/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("total_circles", resp.json()["data"])

    def test_student_stats(self):
        resp = self.client.get("/api/v1/reports/student-stats/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("levels", resp.json()["data"])

    def test_teacher_stats(self):
        resp = self.client.get("/api/v1/reports/teacher-stats/")
        self.assertEqual(resp.status_code, 200)

    def test_urgent_alerts(self):
        resp = self.client.get("/api/v1/reports/urgent-alerts/")
        self.assertEqual(resp.status_code, 200)

    def test_student_cannot_access_reports(self):
        self.client.force_authenticate(user=self.student1)
        resp = self.client.get("/api/v1/reports/dashboard-stats/")
        self.assertEqual(resp.status_code, 403)


class JustificationAPITest(APITestBase):
    def test_list_justifications(self):
        resp = self.client.get("/api/v1/justifications/")
        self.assertEqual(resp.status_code, 200)


class QuranAPITest(TestCase):
    @classmethod
    def setUpTestData(cls):
        from django.core.management import call_command
        call_command("seed_quran")
        cls.student = User.objects.create_user(
            username="qs@test.com", email="qs@test.com", password="test1234",
            full_name_ar="طالب", role=User.Role.STUDENT,
            is_approved=User.ApprovalStatus.APPROVED,
        )

    def setUp(self):
        # The quran:* reference endpoints cache their payloads and Django does
        # not reset the cache between test cases — clear it so earlier tests
        # can't feed this class stale (e.g. pre-seed empty) responses.
        from django.core.cache import cache
        cache.clear()
        self.client = APIClient()
        self.client.force_authenticate(user=self.student)

    def test_requires_auth(self):
        c = APIClient()
        self.assertEqual(c.get("/api/v1/quran/juz/").status_code, 403)

    def test_juz_list(self):
        resp = self.client.get("/api/v1/quran/juz/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(len(data), 30)
        self.assertEqual(len(data[0]["hizbs"]), 2)

    def test_rub_filtered_by_juz(self):
        resp = self.client.get("/api/v1/quran/rub/?juz=1")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(len(data), 8)
        self.assertIn("label", data[0])
        self.assertEqual(data[0]["page"], 1)

    def test_surahs(self):
        resp = self.client.get("/api/v1/quran/surahs/")
        self.assertEqual(len(resp.json()["data"]), 114)

    def test_ayahs_by_surah(self):
        resp = self.client.get("/api/v1/quran/ayahs/?surah=1")
        data = resp.json()["data"]
        self.assertEqual(len(data), 7)
        self.assertEqual(data[0]["verse_key"], "1:1")

    def test_ayahs_requires_a_filter(self):
        self.assertEqual(self.client.get("/api/v1/quran/ayahs/").status_code, 400)

    def test_student_status_empty_before_records(self):
        resp = self.client.get("/api/v1/quran/student-status/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"], {})


class SessionTurnAPITest(APITestBase):
    def setUp(self):
        super().setUp()
        # Use local time (Asia/Riyadh) so is_unlocked combines correctly
        local_now = timezone.localtime(timezone.now())
        past_dt = local_now - timedelta(minutes=5)
        self.session.session_date = past_dt.date()
        self.session.session_time = past_dt.time()
        self.session.duration_minutes = 60
        self.session.status = Session.Status.TURN_TAKING_OPEN
        self.session.save(update_fields=[
            "session_date", "session_time", "duration_minutes", "status",
        ])
        # Turn claiming requires an existing attendance row (auto-confirmed on claim)
        Attendance.objects.create(
            session=self.session, student=self.student1,
            status=Attendance.Status.NOT_RESPONDED,
        )

        self.other_circle = Circle.objects.create(
            name="حلقة أخرى", teacher=self.teacher,
            schedule_time=past_dt.time(),
            status=Circle.Status.ACTIVE, max_students=30,
        )
        self.other_session = Session.objects.create(
            circle=self.other_circle, session_date=past_dt.date(),
            session_time=past_dt.time(), duration_minutes=60,
            status=Session.Status.TURN_TAKING_OPEN,
        )
        self.other_student = User.objects.create_user(
            username="other_student@test.com", email="other_student@test.com",
            password="test1234", full_name_ar="طالب آخر",
            role=User.Role.STUDENT, is_approved=User.ApprovalStatus.APPROVED,
        )
        CircleEnrollment.objects.create(
            circle=self.other_circle, student=self.other_student,
            status=CircleEnrollment.Status.ACTIVE,
        )

    def test_student_list_turns(self):
        SessionTurn.objects.create(session=self.session, student=self.student1, turn_number=1)
        self.client.force_authenticate(user=self.student1)
        resp = self.client.get(f"/api/v1/turns/?session={self.session.id}")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])
        self.assertEqual(len(resp.json()["data"]), 1)

    def test_student_cannot_list_other_circle_turns(self):
        SessionTurn.objects.create(
            session=self.other_session, student=self.other_student, turn_number=1
        )
        self.client.force_authenticate(user=self.student1)
        resp = self.client.get(f"/api/v1/turns/?session={self.other_session.id}")
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(resp.json()["success"])

    def test_student_claim_turn(self):
        self.client.force_authenticate(user=self.student1)
        resp = self.client.post("/api/v1/turns/claim/", {"session": self.session.id}, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.json()["success"])
        self.assertEqual(SessionTurn.objects.count(), 1)

    def test_student_claim_twice(self):
        self.client.force_authenticate(user=self.student1)
        self.client.post("/api/v1/turns/claim/", {"session": self.session.id}, format="json")
        resp = self.client.post("/api/v1/turns/claim/", {"session": self.session.id}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()["success"])

    def test_student_release_turn(self):
        self.client.force_authenticate(user=self.student1)
        self.client.post("/api/v1/turns/claim/", {"session": self.session.id}, format="json")
        resp = self.client.post("/api/v1/turns/release/", {"session": self.session.id}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(SessionTurn.objects.count(), 0)

    def test_student_release_nonexistent(self):
        self.client.force_authenticate(user=self.student1)
        resp = self.client.post("/api/v1/turns/release/", {"session": self.session.id}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()["success"])

    def test_teacher_reorder_turns(self):
        SessionTurn.objects.create(session=self.session, student=self.student1, turn_number=1)
        SessionTurn.objects.create(session=self.session, student=self.student2, turn_number=2)
        self.client.force_authenticate(user=self.teacher)
        resp = self.client.post("/api/v1/turns/reorder/", {
            "session": self.session.id,
            "order": [str(self.student2.id), str(self.student1.id)],
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        turns = SessionTurn.objects.filter(session=self.session).order_by("turn_number")
        self.assertEqual(list(turns.values_list("student_id", flat=True)),
                         [self.student2.id, self.student1.id])

    def test_teacher_remove_turn(self):
        SessionTurn.objects.create(session=self.session, student=self.student1, turn_number=1)
        self.client.force_authenticate(user=self.teacher)
        resp = self.client.post("/api/v1/turns/remove/", {
            "session": self.session.id,
            "student": str(self.student1.id),
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(SessionTurn.objects.count(), 0)

    def test_student_cannot_reorder(self):
        self.client.force_authenticate(user=self.student1)
        resp = self.client.post("/api/v1/turns/reorder/", {
            "session": self.session.id,
            "order": [],
        }, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_student_cannot_remove(self):
        self.client.force_authenticate(user=self.student1)
        resp = self.client.post("/api/v1/turns/remove/", {
            "session": self.session.id,
            "student": str(self.student1.id),
        }, format="json")
        self.assertEqual(resp.status_code, 403)


class CertificateAPITest(APITestBase):
    def setUp(self):
        super().setUp()
        self.template = CertificateTemplate.objects.create(
            name="قالب اختبار", category="hifz",
        )
        self.cert1 = Certificate.objects.create(
            student=self.student1, template=self.template,
            certificate_number="CERT-001", status="issued",
        )
        self.cert2 = Certificate.objects.create(
            student=self.student2, template=self.template,
            certificate_number="CERT-002", status="issued",
        )

    def test_student_list_own_certificates(self):
        self.client.force_authenticate(user=self.student1)
        resp = self.client.get("/api/v1/certificates/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data["data"]), 1)
        self.assertEqual(data["data"][0]["certificate_number"], "CERT-001")

    def test_admin_lists_all(self):
        resp = self.client.get("/api/v1/certificates/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["data"]), 2)

    def test_idor_student_cannot_access_other(self):
        self.client.force_authenticate(user=self.student1)
        resp = self.client.get(f"/api/v1/certificates/{self.cert2.id}/")
        self.assertEqual(resp.status_code, 404)

    def test_student_retrieve_own(self):
        self.client.force_authenticate(user=self.student1)
        resp = self.client.get(f"/api/v1/certificates/{self.cert1.id}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["certificate_number"], "CERT-001")


class StudentHomeAPITest(APITestBase):
    def test_student_can_access(self):
        self.client.force_authenticate(user=self.student1)
        resp = self.client.get("/api/v1/dashboard/student-home/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertIn("active_circles", data["data"])
        self.assertIn("today_sessions", data["data"])
        self.assertIn("unread_notifications", data["data"])
        self.assertIn("certificates_count", data["data"])

    def test_teacher_cannot_access(self):
        self.client.force_authenticate(user=self.teacher)
        resp = self.client.get("/api/v1/dashboard/student-home/")
        self.assertEqual(resp.status_code, 403)

    def test_admin_cannot_access(self):
        resp = self.client.get("/api/v1/dashboard/student-home/")
        self.assertEqual(resp.status_code, 403)

    def test_response_shape(self):
        self.client.force_authenticate(user=self.student1)
        resp = self.client.get("/api/v1/dashboard/student-home/")
        data = resp.json()["data"]
        self.assertIsInstance(data["active_circles"], list)
        self.assertIsInstance(data["today_sessions"], list)
        self.assertIsInstance(data["unread_notifications"], int)
        self.assertIsInstance(data["certificates_count"], int)
        self.assertIsInstance(data["pending_requests_count"], int)
        self.assertIsInstance(data["pending_justifications_count"], int)


class ProgressLogCorrectionAPITest(TestCase):
    """PATCH/DELETE /api/v1/progress-logs/<id>/ — session teacher only."""

    @classmethod
    def setUpTestData(cls):
        from django.core.management import call_command
        call_command("seed_quran")

    def setUp(self):
        from datetime import date
        from apps.circles.models import Circle, CircleEnrollment, Session
        from apps.memorization.engine import create_progress_log
        from apps.memorization.models import ProgressLog, StudentAchievement
        from apps.references.models import Surah

        self.ProgressLog = ProgressLog
        self.StudentAchievement = StudentAchievement
        self.teacher = User.objects.create_user(
            username="plc_t@test.com", email="plc_t@test.com", password="x",
            full_name_ar="معلم", role=User.Role.TEACHER,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        self.student = User.objects.create_user(
            username="plc_s@test.com", email="plc_s@test.com", password="x",
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
        self.session = Session.objects.create(circle=self.circle, session_date=date.today())
        self.log = create_progress_log(
            session=self.session, student=self.student,
            log_category=ProgressLog.Category.HIFDH,
            surah=Surah.objects.get(pk=2), start_ayah=1, end_ayah=25, points=12,
        )
        self.client = APIClient()

    def test_teacher_patches_own_session_log(self):
        self.client.force_authenticate(user=self.teacher)
        r = self.client.patch(
            f"/api/v1/progress-logs/{self.log.pk}/",
            {"end_ayah": 10, "points": 18},
            format="json",
        )
        self.assertEqual(r.status_code, 200)
        self.log.refresh_from_db()
        self.assertEqual(self.log.end_ayah, 10)
        self.assertEqual(float(self.log.points), 18.0)
        self.assertEqual(
            self.StudentAchievement.objects.get(student=self.student).total_hifdh_ayahs, 10
        )

    def test_student_cannot_patch_or_delete(self):
        self.client.force_authenticate(user=self.student)
        r = self.client.patch(
            f"/api/v1/progress-logs/{self.log.pk}/", {"points": 20}, format="json",
        )
        self.assertEqual(r.status_code, 403)
        r = self.client.delete(f"/api/v1/progress-logs/{self.log.pk}/")
        self.assertEqual(r.status_code, 403)
        self.assertTrue(self.ProgressLog.objects.filter(pk=self.log.pk).exists())

    def test_teacher_deletes_own_session_log(self):
        self.client.force_authenticate(user=self.teacher)
        r = self.client.delete(f"/api/v1/progress-logs/{self.log.pk}/")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(self.ProgressLog.objects.filter(pk=self.log.pk).exists())

    def test_foreign_teacher_gets_404_on_patch_and_delete(self):
        foreign = User.objects.create_user(
            username="plc_t2@test.com", email="plc_t2@test.com", password="x",
            full_name_ar="معلم آخر", role=User.Role.TEACHER,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        self.client.force_authenticate(user=foreign)
        # get_queryset scopes teachers to their own circles' logs -> 404
        r = self.client.patch(
            f"/api/v1/progress-logs/{self.log.pk}/", {"points": 20}, format="json",
        )
        self.assertEqual(r.status_code, 404)
        r = self.client.delete(f"/api/v1/progress-logs/{self.log.pk}/")
        self.assertEqual(r.status_code, 404)
        self.assertTrue(self.ProgressLog.objects.filter(pk=self.log.pk).exists())

from datetime import date, timedelta
from django.test import TestCase
from django.utils import timezone

from django.db.models import Count, Q

from apps.accounts.models import User
from apps.circles.models import Circle, CircleEnrollment, Session
from apps.attendance.models import Attendance
from apps.notifications.models import Notification


class AttendanceTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.teacher = User.objects.create_user(
            username="teacher@test.com", email="teacher@test.com",
            password="test1234", full_name_ar="معلم",
            role=User.Role.TEACHER, is_approved=User.ApprovalStatus.APPROVED,
        )
        cls.student = User.objects.create_user(
            username="student@test.com", email="student@test.com",
            password="test1234", full_name_ar="طالب",
            role=User.Role.STUDENT, is_approved=User.ApprovalStatus.APPROVED,
        )
        cls.circle = Circle.objects.create(
            name="حلقة تجريبية", teacher=cls.teacher,
            status=Circle.Status.ACTIVE,
        )
        CircleEnrollment.objects.create(
            circle=cls.circle, student=cls.student,
            status=CircleEnrollment.Status.ACTIVE,
        )
        cls.session = Session.objects.create(
            circle=cls.circle, session_date=date.today(),
        )

    def test_absent_marked_creates_notification(self):
        Attendance.objects.create(
            session=self.session, student=self.student,
            status=Attendance.Status.ABSENT,
        )
        notifs = Notification.objects.filter(
            recipient=self.student, type="absence_alert",
        )
        self.assertEqual(notifs.count(), 1)
        self.assertIn("تم تسجيل غيابك", notifs.first().title)

    def test_justification_before_session(self):
        future_date = date.today() + timedelta(days=7)
        future_session = Session.objects.create(
            circle=self.circle, session_date=future_date,
        )
        Attendance.objects.create(
            session=future_session, student=self.student,
            status=Attendance.Status.ABSENT,
            justification="سأكون مشغولاً",
            justification_status=Attendance.JustificationStatus.PENDING,
            justification_submitted_at=timezone.now(),
        )
        att = Attendance.objects.get(session=future_session, student=self.student)
        self.assertEqual(att.justification_status, Attendance.JustificationStatus.PENDING)
        self.assertEqual(att.justification, "سأكون مشغولاً")

    def test_justification_after_session(self):
        past_date = date.today() - timedelta(days=3)
        past_session = Session.objects.create(
            circle=self.circle, session_date=past_date,
        )
        Attendance.objects.create(
            session=past_session, student=self.student,
            status=Attendance.Status.ABSENT,
        )
        Notification.objects.filter(recipient=self.student).delete()
        att = Attendance.objects.get(session=past_session, student=self.student)
        att.justification = "كنت مريضاً"
        att.justification_status = Attendance.JustificationStatus.PENDING
        att.justification_submitted_at = timezone.now()
        att.save(update_fields=["justification", "justification_status", "justification_submitted_at"])
        att.refresh_from_db()
        self.assertEqual(att.justification, "كنت مريضاً")
        self.assertEqual(att.justification_status, Attendance.JustificationStatus.PENDING)

    def test_accept_justification(self):
        att = Attendance.objects.create(
            session=self.session, student=self.student,
            status=Attendance.Status.ABSENT,
            justification="مرض",
            justification_status=Attendance.JustificationStatus.PENDING,
        )
        att.status = Attendance.Status.EXCUSED
        att.justification_status = Attendance.JustificationStatus.ACCEPTED
        att.teacher_comment = "عذر مقبول"
        att.reviewed_by = self.teacher
        att.reviewed_at = timezone.now()
        att.save(update_fields=[
            "status", "justification_status",
            "teacher_comment", "reviewed_by", "reviewed_at",
        ])
        att.refresh_from_db()
        self.assertEqual(att.justification_status, Attendance.JustificationStatus.ACCEPTED)
        self.assertEqual(att.status, Attendance.Status.EXCUSED)
        notif = Notification.objects.filter(
            recipient=self.student, type=Notification.Type.ABSENCE_REVIEW,
        ).last()
        self.assertIsNotNone(notif)
        self.assertIn("قبول", notif.title)

    def test_refuse_justification(self):
        att = Attendance.objects.create(
            session=self.session, student=self.student,
            status=Attendance.Status.ABSENT,
            justification="لا يوجد سبب",
            justification_status=Attendance.JustificationStatus.PENDING,
        )
        att.justification_status = Attendance.JustificationStatus.REFUSED
        att.teacher_comment = "عذر غير مقبول"
        att.reviewed_by = self.teacher
        att.reviewed_at = timezone.now()
        att.save(update_fields=[
            "justification_status", "teacher_comment",
            "reviewed_by", "reviewed_at",
        ])
        att.refresh_from_db()
        self.assertEqual(att.justification_status, Attendance.JustificationStatus.REFUSED)
        notif = Notification.objects.filter(
            recipient=self.student, type=Notification.Type.ABSENCE_REVIEW,
        ).last()
        self.assertIsNotNone(notif)
        self.assertIn("رفض", notif.title)
        self.assertIn("عذر غير مقبول", notif.message)

    def test_absence_counts_on_profile(self):
        Attendance.objects.create(
            session=self.session, student=self.student,
            status=Attendance.Status.ABSENT,
            justification_status=Attendance.JustificationStatus.ACCEPTED,
        )
        session2 = Session.objects.create(
            circle=self.circle, session_date=date.today() - timedelta(days=1),
        )
        Attendance.objects.create(
            session=session2, student=self.student,
            status=Attendance.Status.ABSENT,
            justification_status=Attendance.JustificationStatus.NONE,
        )
        counts = Attendance.objects.filter(student=self.student, status='absent').aggregate(
            total=Count('id'),
            justified=Count('id', filter=Q(justification_status=Attendance.JustificationStatus.ACCEPTED)),
            unjustified=Count('id', filter=Q(justification_status__in=[
                Attendance.JustificationStatus.REFUSED, Attendance.JustificationStatus.NONE,
            ])),
        )
        self.assertEqual(counts['total'], 2)
        self.assertEqual(counts['justified'], 1)
        self.assertEqual(counts['unjustified'], 1)

    def test_cannot_resubmit_while_pending(self):
        Attendance.objects.create(
            session=self.session, student=self.student,
            status=Attendance.Status.ABSENT,
            justification="سبب أول",
            justification_status=Attendance.JustificationStatus.PENDING,
        )
        att = Attendance.objects.get(session=self.session, student=self.student)
        self.assertEqual(att.justification_status, Attendance.JustificationStatus.PENDING)
        from apps.api.views import AbsenceJustificationViewSet
        from rest_framework.test import APIRequestFactory
        factory = APIRequestFactory()
        request = factory.post("/api/v1/justifications/", {
            "session_id": self.session.id,
            "reason": "سبب ثانٍ",
        })
        request.user = self.student
        view = AbsenceJustificationViewSet.as_view({"post": "create"})
        response = view(request)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data["success"])
        att.refresh_from_db()
        self.assertEqual(att.justification, "سبب أول")

    def test_django_admin_attendance_list_filters(self):
        Attendance.objects.create(
            session=self.session, student=self.student,
            status=Attendance.Status.ABSENT,
            justification_status=Attendance.JustificationStatus.PENDING,
        )
        self.client.force_login(self.teacher)
        response = self.client.get("/admin/attendance/attendance/")
        self.assertEqual(response.status_code, 302)
        self.client.force_login(
            User.objects.create_superuser(
                username="super@test.com", email="super@test.com",
                password="test1234",
            )
        )
        response = self.client.get("/admin/attendance/attendance/")
        self.assertEqual(response.status_code, 200)
        response = self.client.get(
            "/admin/attendance/attendance/?justification_status__exact=pending"
        )
        self.assertEqual(response.status_code, 200)

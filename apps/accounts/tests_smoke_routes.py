"""Route smoke test: GET every named route (no-arg AND detail) as each role,
with realistic seed data present, and fail if any returns a server error (500)
or raises. Guards against broken navigation across the whole app; detail routes
use best-effort pks, so a wrong guess just 404s (harmless — only 500/EXC fail)."""
from datetime import date

from django.test import TestCase, Client
from django.urls import get_resolver, reverse, NoReverseMatch

from apps.accounts.models import Batch, TeacherAbsence, TeacherSubstitution, User
from apps.announcements.models import Announcement
from apps.circles.models import Circle, CircleEnrollment, Session
from apps.exams.models import Exam, ExamMark
from apps.notifications.models import Notification
from apps.requests.models import SupportRequest


def _collect_named_routes():
    """Return list of (full_name, group_names) for every named route."""
    out = []
    resolver = get_resolver()

    def walk(patterns, ns_prefix):
        for p in patterns:
            if hasattr(p, "url_patterns"):
                new_ns = p.namespace or ""
                prefix = f"{ns_prefix}{new_ns}:" if new_ns else ns_prefix
                walk(p.url_patterns, prefix)
            else:
                name = getattr(p, "name", None)
                if not name:
                    continue
                groups = list(p.pattern.regex.groupindex.keys())
                out.append((f"{ns_prefix}{name}", groups))

    walk(resolver.url_patterns, "")
    return out


class RouteSmokeWithDataTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username="sm_admin@t.com", email="sm_admin@t.com", password="x",
            full_name_ar="مدير", role=User.Role.MAIN_ADMIN,
            is_approved=User.ApprovalStatus.APPROVED, is_staff=True,
        )
        cls.sub = User.objects.create_user(
            username="sm_sub@t.com", email="sm_sub@t.com", password="x",
            full_name_ar="مشرف", role=User.Role.SUB_ADMIN,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        cls.batch = Batch.objects.create(name="دفعة", number=1, year=2026, created_by=cls.admin)
        cls.batch.sub_admins.add(cls.sub)
        cls.teacher = User.objects.create_user(
            username="sm_teacher@t.com", email="sm_teacher@t.com", password="x",
            full_name_ar="معلم", role=User.Role.TEACHER,
            is_approved=User.ApprovalStatus.APPROVED, batch=cls.batch,
        )
        cls.student = User.objects.create_user(
            username="sm_student@t.com", email="sm_student@t.com", password="x",
            full_name_ar="طالب", role=User.Role.STUDENT,
            is_approved=User.ApprovalStatus.APPROVED, batch=cls.batch,
        )
        cls.circle = Circle.objects.create(
            name="حلقة", batch=cls.batch, status=Circle.Status.ACTIVE, teacher=cls.teacher,
        )
        CircleEnrollment.enroll(cls.student, cls.circle)
        cls.session = Session.objects.create(
            circle=cls.circle, session_date=date(2026, 7, 11),
            status=Session.Status.SCHEDULED,
        )
        cls.exam = Exam.objects.create(
            title="امتحان", circle=cls.circle, created_by=cls.admin,
            assigned_teacher=cls.teacher, status=Exam.Status.PUBLISHED,
        )
        cls.mark = ExamMark.objects.create(
            exam=cls.exam, student=cls.student, marks_obtained=80,
            entered_by=cls.teacher, status=ExamMark.Status.APPROVED,
        )
        cls.announcement = Announcement.objects.create(
            author=cls.admin, title="إعلان", body="نص",
        )
        cls.support_request = SupportRequest.objects.create(
            submitted_by=cls.student, title="طلب", body="نص",
        )
        cls.notification = Notification.objects.create(
            recipient=cls.student, type=Notification.Type.SYSTEM, title="إشعار", message="نص",
        )
        cls.absence = TeacherAbsence.objects.create(
            teacher=cls.teacher, start_date=date(2026, 7, 1), end_date=date(2026, 7, 20),
            reason="سفر", status=TeacherAbsence.Status.APPROVED, substitute_teacher=cls.teacher,
        )
        TeacherSubstitution.objects.create(
            absence=cls.absence, circle=cls.circle, substitute_teacher=cls.teacher,
        )

    def _kwargs_for(self, name, groups):
        """Best-effort kwargs so detail routes hit a real object; wrong guesses
        just 404 (harmless — we only flag 500/EXC)."""
        low = name.lower()
        kw = {}
        for g in groups:
            gl = g.lower()
            if "circle" in gl:
                kw[g] = self.circle.pk
            elif "session" in gl:
                kw[g] = self.session.pk
            elif "student" in gl:
                kw[g] = self.student.pk
            elif "teacher" in gl:
                kw[g] = self.teacher.pk
            elif "batch" in gl:
                kw[g] = self.batch.pk
            elif gl in ("pk", "id"):
                if "exam" in low:
                    kw[g] = self.exam.pk
                elif "batch" in low:
                    kw[g] = self.batch.pk
                elif "circle" in low:
                    kw[g] = self.circle.pk
                elif "session" in low:
                    kw[g] = self.session.pk
                elif "student" in low:
                    kw[g] = self.student.pk
                elif "teacher" in low or "supervisor" in low:
                    kw[g] = self.teacher.pk
                elif "announcement" in low:
                    kw[g] = self.announcement.pk
                elif "request" in low:
                    kw[g] = self.support_request.pk
                elif "notification" in low:
                    kw[g] = self.notification.pk
                else:
                    return None
            else:
                return None
        return kw

    def test_routes_with_data(self):
        roles = {"admin": self.admin, "sub_admin": self.sub,
                 "teacher": self.teacher, "student": self.student}
        clients = {}
        for r, u in roles.items():
            c = Client()
            c.force_login(u)
            clients[r] = c

        errors = []
        checked = 0
        for name, groups in _collect_named_routes():
            if name.startswith(("admin:", "api:")):
                continue
            kw = self._kwargs_for(name, groups) if groups else {}
            if kw is None:
                continue
            try:
                url = reverse(name, kwargs=kw) if kw else reverse(name)
            except NoReverseMatch:
                continue
            checked += 1
            for role, c in clients.items():
                try:
                    st = c.get(url).status_code
                except Exception as e:
                    errors.append((name, url, role, f"EXC {type(e).__name__}: {e}"))
                    continue
                if st >= 500:
                    errors.append((name, url, role, st))

        print("\n===== ROUTE SMOKE (WITH DATA) =====")
        print(f"checked {checked} routes x 4 roles")
        print(f"ERRORS ({len(errors)}):")
        for name, url, role, st in errors:
            print(f"  [{st}] {name}  ({role})  {url}")
        self.assertEqual(errors, [], f"{len(errors)} route/role 500s")

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import date, timedelta
import random

from apps.accounts.models import User
from apps.circles.models import Circle, CircleEnrollment, Session
from apps.attendance.models import Attendance
from apps.requests.models import SupportRequest
from apps.announcements.models import Announcement


class Command(BaseCommand):
    help = "Seed database with test data"

    def handle(self, *args, **options):
        self.stdout.write("Seeding data...")

        # ── Users ──────────────────────────────────────────
        admin, _ = User.objects.get_or_create(
            email="admin@hafez.com",
            defaults=dict(
                username="admin@hafez.com",
                role=User.Role.ADMIN,
                full_name_ar="أحمد المدير",
                phone="0500000001",
                gender="male",
                is_approved=User.ApprovalStatus.APPROVED,
                is_active=True,
            ),
        )
        admin.set_password("test1234")
        admin.save()

        supervisor, _ = User.objects.get_or_create(
            email="supervisor@hafez.com",
            defaults=dict(
                username="supervisor@hafez.com",
                role=User.Role.SUPERVISOR,
                full_name_ar="خالد المشرف",
                phone="0500000002",
                gender="male",
                is_approved=User.ApprovalStatus.APPROVED,
                is_active=True,
            ),
        )
        supervisor.set_password("test1234")
        supervisor.save()

        teacher1, _ = User.objects.get_or_create(
            email="teacher1@hafez.com",
            defaults=dict(
                username="teacher1@hafez.com",
                role=User.Role.TEACHER,
                full_name_ar="سعيد المعلم",
                phone="0500000011",
                gender="male",
                is_approved=User.ApprovalStatus.APPROVED,
                is_active=True,
            ),
        )
        teacher1.set_password("test1234")
        teacher1.save()

        teacher2, _ = User.objects.get_or_create(
            email="teacher2@hafez.com",
            defaults=dict(
                username="teacher2@hafez.com",
                role=User.Role.TEACHER,
                full_name_ar="نورة المعلمة",
                phone="0500000012",
                gender="female",
                is_approved=User.ApprovalStatus.APPROVED,
                is_active=True,
            ),
        )
        teacher2.set_password("test1234")
        teacher2.save()

        students = []
        student_names = [
            "محمد الطالب", "فاطمة الطالبة", "عمر الطالب", "سارة الطالبة",
            "عبدالله الطالب", "مريم الطالبة", "يوسف الطالب", "حفصة الطالبة",
            "إبراهيم الطالب", "آمنة الطالبة", "حمزة الطالب", "رقية الطالبة",
            "زياد الطالب", "ليلى الطالبة", "حسن الطالب", "نورة الطالبة",
        ]
        for i, name in enumerate(student_names):
            u, created = User.objects.get_or_create(
                email=f"student{i+1}@hafez.com",
                defaults=dict(
                    username=f"student{i+1}@hafez.com",
                    role=User.Role.STUDENT,
                    full_name_ar=name,
                    phone=f"05000001{i+1:02d}",
                    gender="male" if i % 2 == 0 else "female",
                    is_approved=User.ApprovalStatus.APPROVED if i < 12 else User.ApprovalStatus.PENDING,
                    is_active=True,
                ),
            )
            if created:
                u.set_password("test1234")
                u.save()
            students.append(u)

        # ── Circles ────────────────────────────────────────
        circles_data = [
            ("حلقة الفجر", teacher1, "المسجد النبوي", Circle.Gender.MALE, 20, "بعد الفجر كل يوم"),
            ("حلقة العصر", teacher1, "المركز الإسلامي", Circle.Gender.MALE, 25, "بعد العصر سبت-أربعاء"),
            ("حلقة الضحى", teacher2, "معهد التحفيظ", Circle.Gender.FEMALE, 15, "بعد الضحى أحد-ثلاثاء"),
            ("حلقة المغرب", teacher2, "مسجد الحي", Circle.Gender.FEMALE, 20, "بعد المغرب يومياً"),
            ("حلقة العشاء", None, "المسجد الجامع", Circle.Gender.MALE, 30, "بعد العشاء سبت-خميس"),
        ]
        circles = []
        for name, teacher, location, gender, max_s, schedule in circles_data:
            c, _ = Circle.objects.get_or_create(
                name=name,
                defaults=dict(
                    teacher=teacher,
                    location=location,
                    gender=gender,
                    max_students=max_s,
                    schedule=schedule,
                    status=Circle.Status.ACTIVE,
                ),
            )
            circles.append(c)

        # ── Enrollments ────────────────────────────────────
        active_students = User.objects.filter(is_approved=User.ApprovalStatus.APPROVED, role=User.Role.STUDENT)[:12]
        for i, student in enumerate(active_students):
            circle = circles[i % len(circles)]
            CircleEnrollment.objects.get_or_create(
                circle=circle,
                student=student,
                defaults=dict(status=CircleEnrollment.Status.ACTIVE),
            )

        # ── Sessions & Attendance ──────────────────────────
        for circle in circles:
            for days_ago in range(14, 0, -1):
                session_date = date.today() - timedelta(days=days_ago)
                if session_date.weekday() >= 5:
                    continue
                session, _ = Session.objects.get_or_create(
                    circle=circle,
                    session_date=session_date,
                )
                active_enrollments = circle.enrollments.filter(status=CircleEnrollment.Status.ACTIVE)
                for enrollment in active_enrollments:
                    status = random.choices(
                        [Attendance.Status.PRESENT, Attendance.Status.LATE,
                         Attendance.Status.ABSENT, Attendance.Status.EXCUSED],
                        weights=[60, 15, 15, 10], k=1
                    )[0]
                    Attendance.objects.get_or_create(
                        session=session,
                        student=enrollment.student,
                        defaults=dict(status=status),
                    )

        # ── Support Requests ───────────────────────────────
        request_types = [SupportRequest.Type.ADMINISTRATIVE, SupportRequest.Type.TECHNICAL,
                         SupportRequest.Type.ACADEMIC, SupportRequest.Type.OTHER]
        priorities = [SupportRequest.Priority.URGENT, SupportRequest.Priority.HIGH,
                      SupportRequest.Priority.NORMAL, SupportRequest.Priority.LOW]
        statuses = [SupportRequest.Status.SUBMITTED, SupportRequest.Status.UNDER_REVIEW,
                    SupportRequest.Status.APPROVED, SupportRequest.Status.RESOLVED]

        for i in range(8):
            student = random.choice(active_students)
            SupportRequest.objects.get_or_create(
                title=f"طلب رقم {i+1}",
                defaults=dict(
                    submitted_by=student,
                    body=f"هذا نص الطلب رقم {i+1} للمتابعة",
                    type=random.choice(request_types),
                    priority=random.choice(priorities),
                    status=random.choice(statuses),
                ),
            )

        # ── Announcements ──────────────────────────────────
        announcements_data = [
            ("بدء التسجيل في الفصل الجديد", "يسر الإدارة الإعلان عن بدء التسجيل في الفصل الدراسي الجديد...", admin),
            ("مواعيد الاختبارات الشهرية", "سيتم عقد الاختبارات الشهرية في الأسبوع الأخير من الشهر...", admin),
            ("تنويه هام للحلقات", "يرجى من جميع المعلمين تحديث بيانات الحلقات في النظام...", supervisor),
        ]
        for title, body, author in announcements_data:
            Announcement.objects.get_or_create(
                title=title,
                defaults=dict(body=body, author=author),
            )

        self.stdout.write(self.style.SUCCESS("Done! Seeded Users, Circles, Sessions, Attendance, Requests, Announcements."))

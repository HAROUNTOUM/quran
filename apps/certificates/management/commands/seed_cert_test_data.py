from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import date, timedelta
import random

from apps.accounts.models import User
from apps.circles.models import Circle, CircleEnrollment
from apps.exams.models import Exam, ExamMark
from apps.memorization.models import StudentAchievement
from apps.certificates.models import Certificate, CertificateTemplate
from apps.certificates.services import issue_certificate


class Command(BaseCommand):
    help = "Seed certificate test data: exams, marks, achievements, sample certs"

    def handle(self, *args, **options):
        self.stdout.write("Seeding certificate test data...")

        admin = User.objects.filter(role=User.Role.ADMIN).first()
        if not admin:
            self.stdout.write(self.style.ERROR("No admin found. Run seed_data first."))
            return

        students = list(User.objects.filter(
            role=User.Role.STUDENT,
            is_approved=User.ApprovalStatus.APPROVED,
            is_active=True,
        ))
        if len(students) < 4:
            self.stdout.write(self.style.ERROR("Need at least 4 approved students. Run seed_data first."))
            return

        circles = list(Circle.objects.filter(status=Circle.Status.ACTIVE))
        templates = list(CertificateTemplate.objects.filter(is_active=True))

        # ── Exams with marks ────────────────────────────────
        self.stdout.write("  Creating exams & marks...")
        exam_types = ["monthly", "quarterly", "final", "quiz", "oral"]
        for i in range(3):
            exam_date = date.today() - timedelta(days=random.randint(5, 60))
            exam, _ = Exam.objects.get_or_create(
                title=f"الامتحان التجريبي {i+1}",
                defaults=dict(
                    exam_type=random.choice(exam_types),
                    circle=random.choice(circles) if circles else None,
                    created_by=admin,
                    exam_date=exam_date,
                    max_marks=100,
                    pass_percentage=50,
                    status=Exam.Status.COMPLETED,
                ),
            )
            for student in students[:8]:
                marks = random.uniform(30, 100)
                ExamMark.objects.get_or_create(
                    exam=exam,
                    student=student,
                    defaults=dict(
                        marks_obtained=marks,
                        is_passed=marks >= 50,
                        status=ExamMark.Status.APPROVED,
                        entered_by=admin,
                        approved_by=admin,
                    ),
                )

        # ── Student achievements ────────────────────────────
        self.stdout.write("  Creating achievements...")
        for student in students[:10]:
            StudentAchievement.objects.get_or_create(
                student=student,
                defaults=dict(
                    completed_juz=random.randint(1, 30),
                    current_juz=random.randint(1, 30),
                    total_hifdh_ayahs=random.randint(100, 6000),
                    total_murajaah_ayahs=random.randint(50, 2000),
                    total_hifdh_pages=random.randint(5, 300),
                    total_murajaah_pages=random.randint(2, 100),
                ),
            )

        # ── Sample certificates ─────────────────────────────
        self.stdout.write("  Creating sample certificates...")
        existing_count = Certificate.objects.count()
        if existing_count == 0:
            for i, student in enumerate(students[:5]):
                template = templates[i % len(templates)]
                try:
                    issue_certificate(
                        student=student,
                        template=template,
                        issued_by=admin,
                        details=f"جزء {random.randint(1, 30)}" if template.category != "completion" else "",
                        metadata={"circle_name": circles[i % len(circles)].name if circles else ""},
                    )
                except Exception as e:
                    self.stdout.write(f"    Skipped cert for {student.full_name_ar}: {e}")
            self.stdout.write(self.style.SUCCESS(f"    Created {5} certificates"))
        else:
            self.stdout.write(f"    {existing_count} certificates already exist, skipping")

        # Summary
        print()
        print("── Certificate Test Data Summary ──")
        print(f"  Users:           {User.objects.count()} total, {User.objects.filter(role=User.Role.STUDENT).count()} students")
        print(f"  Circles:         {Circle.objects.count()} total, {Circle.objects.filter(status=Circle.Status.ACTIVE).count()} active")
        print(f"  Enrollments:     {CircleEnrollment.objects.filter(status=CircleEnrollment.Status.ACTIVE).count()} active")
        print(f"  Exams:           {Exam.objects.count()} total, {Exam.objects.filter(status=Exam.Status.COMPLETED).count()} completed")
        print(f"  ExamMarks:       {ExamMark.objects.count()} total, {ExamMark.objects.filter(is_passed=True).count()} passed")
        print(f"  Achievements:    {StudentAchievement.objects.count()}")
        print(f"  Certificates:    {Certificate.objects.count()}")
        print()
        print("  Admin:     admin@hafez.com / test1234")
        print("  Students:  student1@hafez.com to student12@hafez.com / test1234")
        print()

        self.stdout.write(self.style.SUCCESS("Done!"))

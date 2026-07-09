from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from apps.accounts.models import User
from apps.circles.models import Circle, CircleEnrollment, Session


class Command(BaseCommand):
    help = "Seed test sessions within a 15-minute window for turn-taking testing"

    def handle(self, *args, **options):
        now = timezone.localtime()
        teachers = User.objects.filter(role=User.Role.TEACHER, is_approved=User.ApprovalStatus.APPROVED)
        if not teachers.exists():
            self.stdout.write(self.style.WARNING("No teachers found. Run seed_data first."))
            return
        teacher = teachers.first()
        circles = Circle.objects.filter(teacher=teacher, status=Circle.Status.ACTIVE)
        if not circles.exists():
            self.stdout.write(self.style.WARNING("No active circles for teacher. Run seed_data first."))
            return
        today = now.date()
        minutes = now.minute
        # Round to nearest 15-min slot ahead
        base_minute = ((minutes // 15) + 1) * 15
        if base_minute >= 60:
            base_minute = 0
            base_hour = now.hour + 1
        else:
            base_hour = now.hour
        for i, circle in enumerate(circles):
            session_time = timezone.datetime.strptime(f"{base_hour:02d}:{base_minute:02d}", "%H:%M").time()
            session, created = Session.objects.get_or_create(
                circle=circle,
                session_date=today,
                defaults=dict(
                    session_time=session_time,
                    session_type=Session.Type.IN_PERSON,
                    location=circle.location or "غرفة الاختبار",
                    notes=f"حصة اختبار لتجربة تناوب الدخول - تم إنشاؤها في {now.strftime('%H:%M')}",
                ),
            )
            if created:
                self.stdout.write(self.style.SUCCESS(
                    f"Created session: {circle.name} @ {today} {session_time.strftime('%H:%M')}"
                ))
            else:
                self.stdout.write(f"Session exists: {circle.name} @ {today} {session_time.strftime('%H:%M')}")
            # Advance by 5 min for next circle
            base_minute += 5
            if base_minute >= 60:
                base_minute -= 60
                base_hour += 1
        enrolled = CircleEnrollment.objects.filter(
            circle__in=circles, status=CircleEnrollment.Status.ACTIVE
        ).count()
        self.stdout.write(self.style.SUCCESS(
            f"Done. {circles.count()} circle(s), {enrolled} enrolled student(s). "
            "Sessions unlock 15 min before start time for turn-taking testing."
        ))

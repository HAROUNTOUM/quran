"""Send reminders for upcoming private (1-on-1) تسميع sessions.

Run daily (e.g. via cron): notifies each student whose private session is
scheduled for tomorrow and hasn't been reminded yet. Idempotent — a session is
only reminded once (guarded by `reminder_sent_at`)."""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.memorization.models import PrivateSession


class Command(BaseCommand):
    help = "أرسل تذكيرات الجلسات الخاصة المجدولة غداً"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days-ahead", type=int, default=1,
            help="عدد الأيام قبل الجلسة لإرسال التذكير (افتراضي: 1)",
        )

    def handle(self, *args, **options):
        target = timezone.localdate() + timedelta(days=options["days_ahead"])
        due = PrivateSession.objects.filter(
            status=PrivateSession.Status.SCHEDULED,
            scheduled_date=target,
            reminder_sent_at__isnull=True,
        )
        sent = 0
        for session in due:
            session.send_reminder()
            sent += 1
        self.stdout.write(self.style.SUCCESS(f"تم إرسال {sent} تذكيراً للجلسات الخاصة بتاريخ {target}"))

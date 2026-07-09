from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.usersettings.models import SystemSettings, UserSettings


class Command(BaseCommand):
    help = "One-time backfill: create UserSettings for existing users and ensure the SystemSettings singleton exists (Section I)."

    def handle(self, *args, **options):
        User = get_user_model()
        missing = User.objects.filter(settings__isnull=True)
        created = UserSettings.objects.bulk_create(
            [UserSettings(user=user) for user in missing.iterator()],
            ignore_conflicts=True,
        )
        SystemSettings.load()
        self.stdout.write(self.style.SUCCESS(
            f"Created {len(created)} UserSettings rows; SystemSettings singleton ensured."
        ))

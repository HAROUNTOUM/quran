from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.classrooms.models import TeacherRoom


class Command(BaseCommand):
    help = "One-time backfill: create permanent rooms for existing teachers missing one (Section C.4 / Section I)."

    def handle(self, *args, **options):
        User = get_user_model()
        created = 0
        for teacher in User.objects.filter(role="teacher", room__isnull=True).iterator():
            TeacherRoom.get_or_create_for(teacher)
            created += 1
        self.stdout.write(self.style.SUCCESS(f"Created {created} teacher rooms."))

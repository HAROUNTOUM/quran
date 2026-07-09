from django.core.management.base import BaseCommand

from apps.webinars.models import Webinar


class Command(BaseCommand):
    help = "Ensure every scheduled/live webinar has a speaker_room_name"

    def handle(self, *args, **options):
        count = 0
        for webinar in Webinar.objects.filter(speaker_room_name=""):
            webinar.speaker_room_name = webinar._meta.get_field("speaker_room_name").default()
            webinar.save(update_fields=["speaker_room_name"])
            count += 1
        self.stdout.write(self.style.SUCCESS(f"Updated {count} webinar(s)"))

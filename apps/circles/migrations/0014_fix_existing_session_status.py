from django.db import migrations
from django.utils import timezone
from datetime import datetime


def fix_session_status(apps, schema_editor):
    Session = apps.get_model("circles", "Session")

    today = timezone.localdate()

    for session in Session.objects.all():
        tzinfo = timezone.get_current_timezone()
        if session.session_time and session.session_date:
            session.start_time = timezone.make_aware(
                datetime.combine(session.session_date, session.session_time), tzinfo,
            )
        elif session.session_date:
            session.start_time = timezone.make_aware(
                datetime.combine(session.session_date, datetime.min.time()), tzinfo,
            )

        if session.session_date < today:
            session.status = "ended"
        else:
            session.status = "scheduled"

        session.save(update_fields=["status", "start_time"])


class Migration(migrations.Migration):

    dependencies = [
        ("circles", "0013_session_start_time_session_status"),
    ]

    operations = [
        migrations.RunPython(fix_session_status, migrations.RunPython.noop),
    ]

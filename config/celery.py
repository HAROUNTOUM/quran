import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

app = Celery("hafez_platform")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

app.conf.beat_schedule = {
    "session-reminders-every-30min": {
        "task": "tasks.attendance.send_session_reminders",
        "schedule": 1800,
    },
    "flag-unjustified-daily": {
        "task": "tasks.attendance.flag_unjustified_absences",
        "schedule": 86400,
    },
}

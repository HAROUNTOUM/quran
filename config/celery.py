import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

app = Celery("hafez_platform")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

app.conf.beat_schedule = {
    "session-reminders-every-30min": {
        "task": "apps.attendance.tasks.send_session_reminders",
        "schedule": 1800,
    },
    "flag-pending-justifications-daily": {
        "task": "apps.attendance.tasks.flag_pending_justifications",
        "schedule": 1800,
    },
    "flag-unjustified-daily": {
        "task": "apps.attendance.tasks.flag_unjustified_absences",
        "schedule": 86400,
    },
}

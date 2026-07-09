import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

app = Celery("hafez_platform")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

app.conf.beat_schedule = {
    "advance-session-status-every-1min": {
        "task": "apps.attendance.tasks.advance_session_status",
        "schedule": 60,
    },
    "resolve-attendance-every-5min": {
        "task": "apps.attendance.tasks.resolve_attendance",
        "schedule": 300,
    },
}

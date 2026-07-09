from celery import shared_task
from django.db import transaction
from django.utils import timezone
from datetime import timedelta

from apps.attendance.models import Attendance
from apps.circles.models import Session, CONFIRM_WINDOW_MINUTES, TURN_LOCK_MINUTES, SESSION_MAX_DURATION_MINUTES


@shared_task
def advance_session_status():
    now = timezone.now()
    updated = 0

    sched = Session.Status.SCHEDULED
    conf_open = Session.Status.CONFIRMATION_OPEN
    turn_open = Session.Status.TURN_TAKING_OPEN
    live = Session.Status.LIVE
    ended = Session.Status.ENDED

    confirm_offset = timedelta(minutes=CONFIRM_WINDOW_MINUTES)
    turn_offset = timedelta(minutes=TURN_LOCK_MINUTES)
    max_duration = timedelta(minutes=SESSION_MAX_DURATION_MINUTES)

    to_confirmation_open = Session.objects.filter(
        status=sched, start_time__lte=now + confirm_offset,
    )
    for s in to_confirmation_open:
        s.status = conf_open
        s.save(update_fields=["status"])
        updated += 1

    to_turn_taking_open = Session.objects.filter(
        status=conf_open, start_time__lte=now + turn_offset,
    )
    for s in to_turn_taking_open:
        s.status = turn_open
        s.save(update_fields=["status"])
        updated += 1

    to_live = Session.objects.filter(
        status=turn_open, start_time__lte=now,
    )
    for s in to_live:
        s.status = live
        s.save(update_fields=["status"])
        updated += 1

    to_ended = Session.objects.filter(
        status=live, start_time__lte=now - max_duration,
    )
    for s in to_ended:
        s.status = ended
        s.save(update_fields=["status"])
        updated += 1

    return f"Advanced {updated} sessions"


@shared_task
def resolve_attendance():
    now = timezone.now()
    resolved = 0
    max_duration = timedelta(minutes=SESSION_MAX_DURATION_MINUTES)

    ended_sessions = Session.objects.filter(
        status=Session.Status.ENDED,
        start_time__lte=now - max_duration,
    ).values_list("pk", flat=True)

    if not ended_sessions:
        return "No sessions to resolve"

    not_responded = Attendance.objects.filter(
        session_id__in=list(ended_sessions),
        status=Attendance.Status.NOT_RESPONDED,
    )
    count = not_responded.update(status=Attendance.Status.ABSENT_UNJUSTIFIED)
    resolved += count

    confirmed = Attendance.objects.filter(
        session_id__in=list(ended_sessions),
        status=Attendance.Status.CONFIRMED,
        justification_status=Attendance.JustificationStatus.NONE,
    )
    count = confirmed.update(status=Attendance.Status.ABSENT_UNJUSTIFIED)
    resolved += count

    return f"Resolved {resolved} attendance records"

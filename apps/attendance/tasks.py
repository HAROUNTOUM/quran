from celery import shared_task
from django.utils import timezone
from datetime import timedelta

from apps.attendance.models import Attendance
from apps.circles.models import Session, CircleEnrollment
from apps.notifications.models import Notification


@shared_task
def send_session_reminders():
    tomorrow = timezone.localdate() + timedelta(days=1)
    upcoming = Session.objects.filter(session_date=tomorrow).select_related("circle")
    created = 0
    for session in upcoming:
        enrollments = session.circle.enrollments.filter(
            status=CircleEnrollment.Status.ACTIVE
        ).select_related("student")
        for enrollment in enrollments:
            Notification.objects.create(
                recipient=enrollment.student,
                type="session_reminder",
                title="تذكير بحصة",
                message=f"غداً حصة {session.circle.name}",
                link=f"/sessions/{session.pk}/",
            )
            created += 1
    return f"Sent {created} reminders"


@shared_task
def flag_pending_justifications():
    today = timezone.localdate()
    today_sessions = Session.objects.filter(session_date=today).values_list("id", flat=True)

    enrolled = CircleEnrollment.objects.filter(
        status=CircleEnrollment.Status.ACTIVE,
        circle__sessions__id__in=today_sessions,
    ).select_related("student", "circle").distinct()

    flagged = 0
    for enrollment in enrolled:
        has_log = Attendance.objects.filter(
            session__circle=enrollment.circle,
            student=enrollment.student,
            session__session_date=today,
        ).exists()
        if not has_log:
            Attendance.objects.create(
                session_id=today_sessions[0],
                student=enrollment.student,
                status=Attendance.Status.PENDING_JUSTIFICATION,
            )
            Notification.objects.create(
                recipient=enrollment.student,
                type="absence_alert",
                title="غياب بدون تسجيل",
                message=f"لم يتم تسجيل حضورك في حصة {enrollment.circle.name}. يرجى تقديم عذر",
                link="/justifications/",
            )
            flagged += 1
    return f"Flagged {flagged} pending justifications"


@shared_task
def flag_unjustified_absences():
    cutoff = timezone.localdate() - timedelta(days=7)
    absent = Attendance.objects.filter(
        status=Attendance.Status.PENDING_JUSTIFICATION,
        session__session_date__gte=cutoff,
    ).select_related("session__circle", "student")

    flagged = 0
    for att in absent:
        if not Attendance.objects.filter(
            student=att.student,
            session__circle=att.session.circle,
            status=Attendance.Status.EXCUSED,
            session__session_date__gte=cutoff,
        ).exists():
            Notification.objects.create(
                recipient=att.student,
                type="absence_alert",
                title="غياب بدون عذر",
                message=f"تم تسجيل غيابك في حصة {att.session.circle.name} بدون تقديم عذر",
                link=f"/justifications/{att.pk}/",
            )
            att.status = Attendance.Status.ABSENT
            att.save(update_fields=["status"])
            flagged += 1
    return f"Flagged {flagged} unjustified absences"


@shared_task
def recalculate_student_categories():
    from django.db.models import Avg
    from apps.memorization.models import RecitationGrade

    student_averages = list(
        RecitationGrade.objects.values("student").annotate(
            avg_score=Avg("score")
        )
    )

    categories = {"excellent": 0, "good": 0, "weak": 0}
    for entry in student_averages:
        avg = entry["avg_score"] or 0
        if avg >= 90:
            categories["excellent"] += 1
        elif avg >= 70:
            categories["good"] += 1
        else:
            categories["weak"] += 1

    return categories

from django.db import transaction
from django.utils import timezone
from django.db.models import Avg

from apps.memorization.models import MemorizationProgress, RecitationGrade, ReviewRequest
from apps.circles.models import CircleEnrollment
from apps.notifications.models import Notification


@transaction.atomic
def create_progress(enrollment_id, surah_id, ayah_from, ayah_to,
                    type_="hifz", status="memorizing", notes=""):
    enrollment = CircleEnrollment.objects.select_related(
        "circle", "student"
    ).get(pk=enrollment_id)
    progress = MemorizationProgress.objects.create(
        enrollment=enrollment,
        surah_id=surah_id,
        ayah_from=ayah_from,
        ayah_to=ayah_to,
        type=type_,
        status=status,
        notes=notes,
    )
    Notification.objects.create(
        recipient=enrollment.circle.teacher,
        type="progress_update",
        title="تحديث تقدم",
        message=f"تم تسجيل تقدم جديد للطالب {enrollment.student.full_name_ar}",
        link=f"/students/{enrollment.student_id}/progress/",
    )
    return progress


@transaction.atomic
def review_progress(progress_id, status, tested_by=None):
    progress = MemorizationProgress.objects.select_related(
        "enrollment__circle__teacher"
    ).get(pk=progress_id)
    progress.status = status
    if tested_by:
        progress.tested_by = tested_by
        progress.tested_at = timezone.now()
    else:
        progress.last_revised_at = timezone.now()
    progress.save()

    Notification.objects.create(
        recipient=progress.enrollment.student,
        type="progress_review",
        title="مراجعة التقدم",
        message=f"تم تحديث حالة الحفظ إلى {progress.get_status_display()}",
        link=f"/progress/{progress.pk}/",
    )
    return progress


def get_student_progress(student_id, circle_id=None):
    qs = MemorizationProgress.objects.filter(
        enrollment__student_id=student_id
    ).select_related("surah")
    if circle_id:
        qs = qs.filter(enrollment__circle_id=circle_id)
    return qs.order_by("-created_at")


def get_student_summary(student_id):
    from django.db.models import Count, Sum, F

    stats = MemorizationProgress.objects.filter(
        enrollment__student_id=student_id
    ).aggregate(
        total_records=Count("id"),
        mastered=Count("id", filter=MemorizationProgress.Status("mastered")),
        memorizing=Count("id", filter=MemorizationProgress.Status("memorizing")),
        tested=Count("id", filter=MemorizationProgress.Status("tested")),
        reviewed=Count("id", filter=MemorizationProgress.Status("reviewed")),
        weak=Count("id", filter=MemorizationProgress.Status("weak")),
        total_ayahs=Sum(F("ayah_to") - F("ayah_from") + 1),
    )
    return stats


@transaction.atomic
def approve_review_request(request_id, reviewer):
    req = ReviewRequest.objects.select_related("student", "circle").get(pk=request_id)
    if req.status != ReviewRequest.Status.PENDING:
        return None, "تمت معالجة الطلب مسبقاً"
    req.status = ReviewRequest.Status.APPROVED
    req.reviewed_by = reviewer
    req.save(update_fields=["status", "reviewed_by"])

    Notification.objects.create(
        recipient=req.student,
        type="request_approved",
        title="تم قبول الطلب",
        message=f"تم قبول طلب {req.get_type_display()}",
        link=f"/requests/{req.pk}/",
    )
    return req, None


@transaction.atomic
def reject_review_request(request_id, reviewer, reason=""):
    req = ReviewRequest.objects.select_related("student").get(pk=request_id)
    if req.status != ReviewRequest.Status.PENDING:
        return None, "تمت معالجة الطلب مسبقاً"
    req.status = ReviewRequest.Status.REJECTED
    req.reviewed_by = reviewer
    req.rejection_reason = reason
    req.save(update_fields=["status", "reviewed_by", "rejection_reason"])

    Notification.objects.create(
        recipient=req.student,
        type="request_rejected",
        title="تم رفض الطلب",
        message=f"تم رفض طلب {req.get_type_display()}: {reason or 'بدون سبب'}",
        link=f"/requests/{req.pk}/",
    )
    return req, None


def categorize_student(student_id):
    avg = RecitationGrade.objects.filter(
        student_id=student_id
    ).aggregate(avg_score=Avg("score"))["avg_score"] or 0

    if avg >= 90:
        return "excellent"
    elif avg >= 70:
        return "good"
    return "weak"


def get_session_progress_summary(session_id):
    from apps.circles.models import Session
    session = Session.objects.get(pk=session_id)
    grades = RecitationGrade.objects.filter(session=session)
    avg = grades.aggregate(avg_score=Avg("score"))["avg_score"] or 0
    return {
        "average_score": round(avg, 1),
        "total_graded": grades.count(),
        "total_enrolled": session.circle.enrollments.filter(
            status=CircleEnrollment.Status.ACTIVE
        ).count(),
    }

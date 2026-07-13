from django.db import transaction
from django.db.models import Sum, F

from apps.memorization.models import ProgressLog, StudentAchievement
from apps.memorization.validators import compute_completed_pages


def compute_ayah_count(start_ayah, end_ayah):
    return end_ayah - start_ayah + 1


@transaction.atomic
def create_progress_log(session, student, log_category, surah, start_ayah, end_ayah,
                        evaluation_grade="", teacher_notes="", completed_pages=None,
                        points=None):
    if completed_pages is None:
        completed_pages = compute_completed_pages(start_ayah, end_ayah)

    log = ProgressLog.objects.create(
        session=session,
        student=student,
        log_category=log_category,
        surah=surah,
        start_ayah=start_ayah,
        end_ayah=end_ayah,
        completed_pages=completed_pages,
        evaluation_grade=evaluation_grade,
        points=points,
        teacher_notes=teacher_notes,
    )

    _update_achievement(student)

    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync
    import json

    channel_layer = get_channel_layer()
    if channel_layer:
        async_to_sync(channel_layer.group_send)(
            f"session_{session.id}_progress",
            {
                "type": "progress_update",
                "student_id": str(student.id),
                "student_name": student.full_name_ar,
                "log_category": log_category,
                "surah": surah.name_ar,
                "start_ayah": start_ayah,
                "end_ayah": end_ayah,
                "evaluation_grade": evaluation_grade,
                "completed_pages": float(completed_pages),
            },
        )

    return log


@transaction.atomic
def log_student_progress(student, category: str, hizb: int, thumn: int,
                         session=None) -> ProgressLog:
    """Record a minimal amount-based tracking entry: the teacher submits only
    the category (حفظ جديد/مراجعة) and the amount in hizb + thumn. Creates the
    append-only ProgressLog row and incrementally bumps the student's
    StudentAchievement counters with F() expressions — no cache rebuild.

    `session` is optional: entries made during a live session keep the link
    so the after-session report includes them."""
    from django.core.exceptions import ValidationError
    from django.db.models import F
    from django.utils import timezone

    if category not in (ProgressLog.Category.HIFDH, ProgressLog.Category.MURAJAAH):
        raise ValidationError("نوع التسجيل يجب أن يكون حفظاً جديداً أو مراجعة")
    hizb, thumn = int(hizb or 0), int(thumn or 0)
    if hizb < 0 or not (0 <= thumn <= 7):
        raise ValidationError("المقدار غير صالح: الأثمان بين 0 و7 والأحزاب 0 أو أكثر")
    if hizb == 0 and thumn == 0:
        raise ValidationError("أدخل مقداراً أكبر من صفر")

    log = ProgressLog.objects.create(
        student=student, log_category=category,
        hizb=hizb, thumn=thumn, session=session,
    )

    achievement, _ = StudentAchievement.objects.get_or_create(student=student)
    counter = (
        "total_hifdh_thumns" if category == ProgressLog.Category.HIFDH
        else "total_murajaah_thumns"
    )
    # .update() bypasses auto_now, so stamp last_updated explicitly.
    StudentAchievement.objects.filter(pk=achievement.pk).update(
        **{counter: F(counter) + log.total_thumns}, last_updated=timezone.now(),
    )
    return log


def can_modify_progress_log(user, log) -> bool:
    """Only the session's own teacher (or the main admin) may correct a
    recorded entry — mirrors ReviewRequest.can_be_responded_by."""
    from apps.accounts.models import User
    if user.role == User.Role.MAIN_ADMIN:
        return True
    if log.session_id is None:  # session-less amount entry: admin only
        return False
    return user.role == User.Role.TEACHER and log.session.circle.teacher_id == user.id


@transaction.atomic
def update_progress_log(log, by, log_category, surah, start_ayah, end_ayah,
                        points=None, evaluation_grade="", teacher_notes="",
                        completed_pages=None):
    """Correct a recorded session entry. Validates the ayah range, stamps the
    correction audit trail, and rebuilds the student's achievement totals."""
    from django.core.exceptions import PermissionDenied
    from django.utils import timezone
    from apps.references.utils import validate_ayah_range

    if not can_modify_progress_log(by, log):
        raise PermissionDenied("لا تملك صلاحية تعديل هذا التسجيل")
    if log.surah_id is None:
        from django.core.exceptions import ValidationError
        raise ValidationError("هذا تسجيل مقدار (حزب/ثمن) — احذفه وسجّل مقداراً جديداً بدلاً من تعديله")
    surah_pk = getattr(surah, "pk", surah)
    start_ayah, end_ayah = validate_ayah_range(surah_pk, start_ayah, end_ayah)
    if completed_pages is None:
        completed_pages = compute_completed_pages(start_ayah, end_ayah)

    log.log_category = log_category
    log.surah_id = surah_pk
    log.start_ayah = start_ayah
    log.end_ayah = end_ayah
    log.points = points
    log.evaluation_grade = evaluation_grade or ""
    log.teacher_notes = teacher_notes or ""
    log.completed_pages = completed_pages
    log.updated_at = timezone.now()
    log.updated_by = by
    log.save()
    _update_achievement(log.student)
    return log


@transaction.atomic
def delete_progress_log(log, by):
    """Remove a mistakenly recorded entry and rebuild achievement totals."""
    from django.core.exceptions import PermissionDenied

    if not can_modify_progress_log(by, log):
        raise PermissionDenied("لا تملك صلاحية حذف هذا التسجيل")
    student = log.student
    log.delete()
    _update_achievement(student)


THUMNS_PER_JUZ = 16  # 2 hizb × 8 athman


def session_report_data(session, student=None):
    """The after-session report: every recorded entry (type, surah, ayah
    range, thumn amount, mark /20, remark) plus the todos the teacher
    assigned in this session — all annotated with thumn/hizb units.
    Pass `student` to scope the report to one student (student-facing page)."""
    from apps.memorization.models import StudyTask
    from apps.references.utils import count_thumns, format_hizb_thumn, thumn_start_keys

    keys = thumn_start_keys()

    def units(surah_id, a_from, a_to, amount_thumns=0):
        if not surah_id:  # amount-based entry: hizb/thumn only
            return format_hizb_thumn(amount_thumns)
        return format_hizb_thumn(count_thumns([(surah_id, a_from, a_to)], _keys=keys))

    logs = ProgressLog.objects.filter(session=session).select_related("student", "surah")
    todos = StudyTask.objects.filter(session=session).select_related(
        "student", "surah", "assigned_by"
    )
    if student is not None:
        logs = logs.filter(student=student)
        todos = todos.filter(student=student)

    report_rows = [{
        "id": log.pk,
        "student": log.student,
        "was_corrected": log.updated_by_id is not None,
        "category": log.get_log_category_display(),
        "category_code": log.log_category,
        "surah": log.surah.name_ar if log.surah_id else "—",
        "ayah_from": log.start_ayah if log.start_ayah is not None else "",
        "ayah_to": log.end_ayah if log.end_ayah is not None else "",
        "thumn_units": units(log.surah_id, log.start_ayah, log.end_ayah, log.total_thumns),
        "points": log.points,
        "grade": log.get_evaluation_grade_display() if log.evaluation_grade else "",
        "remark": log.teacher_notes,
        "created_at": log.created_at,
    } for log in logs]

    todo_rows = [{
        "student": t.student,
        "task_type": t.get_task_type_display(),
        "surah": t.surah.name_ar,
        "ayah_from": t.ayah_from,
        "ayah_to": t.ayah_to,
        "thumn_units": units(t.surah_id, t.ayah_from, t.ayah_to),
        "due_date": t.due_date,
        "status": t.get_status_display(),
        "status_code": t.status,
        "is_overdue": t.is_overdue,
        "remark": t.notes,
        "assigned_by": t.assigned_by.full_name_ar if t.assigned_by else "",
    } for t in todos]

    return report_rows, todo_rows


def _update_achievement(student):
    from apps.references.utils import covered_thumns, thumn_start_keys

    achievement, _ = StudentAchievement.objects.get_or_create(student=student)

    ayahs = F("end_ayah") - F("start_ayah") + 1
    logs = ProgressLog.objects.filter(student=student)
    hifdh_logs = logs.filter(log_category=ProgressLog.Category.HIFDH)
    murajaah_logs = logs.filter(log_category=ProgressLog.Category.MURAJAAH)

    achievement.total_hifdh_ayahs = hifdh_logs.aggregate(t=Sum(ayahs))["t"] or 0
    achievement.total_murajaah_ayahs = murajaah_logs.aggregate(t=Sum(ayahs))["t"] or 0
    achievement.total_hifdh_pages = hifdh_logs.aggregate(t=Sum("completed_pages"))["t"] or 0
    achievement.total_murajaah_pages = murajaah_logs.aggregate(t=Sum("completed_pages"))["t"] or 0

    # Tracking-unit totals: distinct covered thumns from range-based rows
    # PLUS the amount-based rows' total_thumns (the minimal hizb/thumn
    # entries carry no ayah range). Keeps full rebuilds consistent with the
    # incremental F() path in log_student_progress.
    keys = thumn_start_keys()
    hifdh_covered = covered_thumns(
        hifdh_logs.filter(surah__isnull=False)
        .values_list("surah_id", "start_ayah", "end_ayah"), _keys=keys
    )
    hifdh_amount = hifdh_logs.filter(surah__isnull=True).aggregate(
        t=Sum("total_thumns"))["t"] or 0
    murajaah_amount = murajaah_logs.filter(surah__isnull=True).aggregate(
        t=Sum("total_thumns"))["t"] or 0
    achievement.total_hifdh_thumns = len(hifdh_covered) + hifdh_amount
    achievement.total_murajaah_thumns = len(covered_thumns(
        murajaah_logs.filter(surah__isnull=False)
        .values_list("surah_id", "start_ayah", "end_ayah"), _keys=keys
    )) + murajaah_amount

    completed = 0
    current = None  # first juz that is started but not finished
    for juz_num in range(1, 31):
        juz_thumns = set(range((juz_num - 1) * THUMNS_PER_JUZ + 1,
                               juz_num * THUMNS_PER_JUZ + 1))
        if juz_thumns <= hifdh_covered:
            completed += 1
        elif current is None and juz_thumns & hifdh_covered:
            current = juz_num
    achievement.completed_juz = completed
    achievement.current_juz = current or min(completed + 1, 30)

    achievement.save()

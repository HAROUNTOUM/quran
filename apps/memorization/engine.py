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


THUMNS_PER_JUZ = 16  # 2 hizb × 8 athman


def session_report_data(session, student=None):
    """The after-session report: every recorded entry (type, surah, ayah
    range, thumn amount, mark /20, remark) plus the todos the teacher
    assigned in this session — all annotated with thumn/hizb units.
    Pass `student` to scope the report to one student (student-facing page)."""
    from apps.memorization.models import StudyTask
    from apps.references.utils import count_thumns, format_hizb_thumn, thumn_start_keys

    keys = thumn_start_keys()

    def units(surah_id, a_from, a_to):
        return format_hizb_thumn(count_thumns([(surah_id, a_from, a_to)], _keys=keys))

    logs = ProgressLog.objects.filter(session=session).select_related("student", "surah")
    todos = StudyTask.objects.filter(session=session).select_related(
        "student", "surah", "assigned_by"
    )
    if student is not None:
        logs = logs.filter(student=student)
        todos = todos.filter(student=student)

    report_rows = [{
        "student": log.student,
        "category": log.get_log_category_display(),
        "category_code": log.log_category,
        "surah": log.surah.name_ar,
        "ayah_from": log.start_ayah,
        "ayah_to": log.end_ayah,
        "thumn_units": units(log.surah_id, log.start_ayah, log.end_ayah),
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

    # Tracking-unit totals + juz frontier from real thumn coverage.
    keys = thumn_start_keys()
    hifdh_covered = covered_thumns(
        hifdh_logs.values_list("surah_id", "start_ayah", "end_ayah"), _keys=keys
    )
    achievement.total_hifdh_thumns = len(hifdh_covered)
    achievement.total_murajaah_thumns = len(covered_thumns(
        murajaah_logs.values_list("surah_id", "start_ayah", "end_ayah"), _keys=keys
    ))

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

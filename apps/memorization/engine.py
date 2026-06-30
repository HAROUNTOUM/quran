from django.db import transaction
from django.db.models import Sum, F

from apps.memorization.models import ProgressLog, StudentAchievement
from apps.memorization.validators import SURAH_AYAH_COUNTS, compute_completed_pages


def compute_ayah_count(start_ayah, end_ayah):
    return end_ayah - start_ayah + 1


@transaction.atomic
def create_progress_log(session, student, log_category, surah, start_ayah, end_ayah,
                        evaluation_grade="", teacher_notes="", completed_pages=None):
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


def _update_achievement(student):
    achievement, _ = StudentAchievement.objects.get_or_create(student=student)

    hifdh_ayahs = ProgressLog.objects.filter(
        student=student, log_category=ProgressLog.Category.HIFDH
    ).aggregate(
        total=Sum(F("end_ayah") - F("start_ayah") + 1)
    )["total"] or 0

    murajaah_ayahs = ProgressLog.objects.filter(
        student=student, log_category=ProgressLog.Category.MURAJAAH
    ).aggregate(
        total=Sum(F("end_ayah") - F("start_ayah") + 1)
    )["total"] or 0

    hifdh_pages = ProgressLog.objects.filter(
        student=student, log_category=ProgressLog.Category.HIFDH
    ).aggregate(total=Sum("completed_pages"))["total"] or 0

    murajaah_pages = ProgressLog.objects.filter(
        student=student, log_category=ProgressLog.Category.MURAJAAH
    ).aggregate(total=Sum("completed_pages"))["total"] or 0

    achievement.total_hifdh_ayahs = hifdh_ayahs
    achievement.total_murajaah_ayahs = murajaah_ayahs
    achievement.total_hifdh_pages = hifdh_pages
    achievement.total_murajaah_pages = murajaah_pages

    completed = 0
    remaining = hifdh_ayahs
    for juz_num in range(1, 31):
        juz_ayahs = sum(
            SURAH_AYAH_COUNTS.get(s, 0)
            for s in _surahs_in_juz(juz_num)
        )
        if remaining >= juz_ayahs:
            completed += 1
            remaining -= juz_ayahs
        else:
            achievement.completed_juz = completed
            achievement.current_juz = juz_num
            break
    else:
        achievement.completed_juz = 30
        achievement.current_juz = 30

    achievement.save()


def _surahs_in_juz(juz_num):
    mapping = {
        1: list(range(1, 3)),
        2: [2],
        3: [2],
        4: [3],
        5: [4],
        6: [4],
        7: [5],
        8: [6],
        9: [7],
        10: [8, 9],
        11: [9, 10, 11],
        12: [11],
        13: [12, 13, 14],
        14: [15, 16],
        15: [17, 18],
        16: [18],
        17: [21],
        18: [22, 23, 24, 25],
        19: [25, 26, 27],
        20: [27, 28, 29],
        21: [29, 30, 31, 32, 33],
        22: [33, 34, 35, 36],
        23: [36, 37, 38, 39],
        24: [39, 40, 41],
        25: [41, 42, 43, 44, 45],
        26: [46, 47, 48, 49, 50, 51],
        27: [51, 52, 53, 54, 55, 56, 57],
        28: [58, 59, 60, 61, 62, 63, 64, 65, 66],
        29: [67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77],
        30: [78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114],
    }
    return mapping.get(juz_num, [])

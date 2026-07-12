from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.http import require_GET

from apps.reports.utils import CSVRenderer
from apps.references.utils import count_thumns, format_hizb_thumn, thumn_span, thumn_start_keys


@require_GET
@login_required
def report_csv_export(request):
    report_type = request.GET.get("type", "")
    start = request.GET.get("start", "")
    end = request.GET.get("end", "")

    if report_type == "attendance":
        return _export_attendance(request, start, end)
    elif report_type == "hifz":
        return _export_hifz(request, start, end)
    elif report_type == "murajaa":
        return _export_murajaa(request, start, end)
    elif report_type == "grades":
        return _export_grades(request, start, end)
    elif report_type == "tasks":
        return _export_tasks(request, start, end)
    return _export_attendance(request, start, end)


def _export_attendance(request, start, end):
    from apps.attendance.models import Attendance
    qs = Attendance.objects.select_related("session", "student")
    if start:
        qs = qs.filter(session__session_date__gte=start)
    if end:
        qs = qs.filter(session__session_date__lte=end)
    if not request.user.is_staff:
        qs = qs.filter(session__circle__teacher=request.user)
    headers = ["الطالب", "التاريخ", "الحالة", "التبرير", "حالة التبرير"]
    rows = (
        (r.student.full_name_ar, r.session.session_date, r.get_status_display(),
         r.justification[:50] if r.justification else "", r.get_justification_status_display())
        for r in qs.iterator(chunk_size=500)
    )
    return CSVRenderer("attendance.csv").render(headers, rows)


def _thumn_columns(surah_id, ayah_from, ayah_to, keys):
    """(thumn span label, hizb/thumn amount label) for one record's range."""
    span = thumn_span(surah_id, ayah_from, ayah_to, _keys=keys)
    if span is None:
        return "", ""
    first, last = span
    span_label = f"{first}" if first == last else f"{first}-{last}"
    amount = format_hizb_thumn(count_thumns([(surah_id, ayah_from, ayah_to)], _keys=keys))
    return span_label, amount


def _export_hifz(request, start, end):
    from apps.memorization.models import ProgressLog
    return _export_progress_category(
        request, start, end, ProgressLog.Category.HIFDH, "hifz.csv"
    )


def _export_murajaa(request, start, end):
    from apps.memorization.models import ProgressLog
    return _export_progress_category(
        request, start, end, ProgressLog.Category.MURAJAAH, "murajaa.csv"
    )


def _export_progress_category(request, start, end, category, filename):
    """Hifz/murajaa export from the canonical ProgressLog (the same table the
    session reports and StudentAchievement read). The deprecated
    MemorizationProgress table these exports used to read has no writers, so
    it only ever showed pre-refactor historical rows."""
    from apps.memorization.models import ProgressLog
    qs = ProgressLog.objects.filter(log_category=category)
    qs = qs.select_related("student", "surah", "session__circle")
    if start:
        qs = qs.filter(created_at__gte=start)
    if end:
        qs = qs.filter(created_at__lte=end)
    if not request.user.is_staff:
        qs = qs.filter(session__circle__teacher=request.user)
    keys = thumn_start_keys()
    headers = ["الطالب", "من سورة", "من آية", "إلى سورة", "إلى آية",
               "الثمن", "المقدار (حزب/ثمن)", "النقطة /20", "الدرجة",
               "الحلقة", "التاريخ"]
    rows = (
        (r.student.full_name_ar,
         r.surah.name_ar, r.start_ayah, r.surah.name_ar, r.end_ayah,
         *_thumn_columns(r.surah_id, r.start_ayah, r.end_ayah, keys),
         r.points if r.points is not None else "",
         r.evaluation_grade,
         r.session.circle.name if r.session.circle_id else "",
         r.created_at.date())
        for r in qs.iterator(chunk_size=500)
    )
    return CSVRenderer(filename).render(headers, rows)


def _export_grades(request, start, end):
    from apps.memorization.models import ProgressLog
    qs = ProgressLog.objects.select_related("student", "surah", "session__circle")
    if start:
        qs = qs.filter(created_at__gte=start)
    if end:
        qs = qs.filter(created_at__lte=end)
    if not request.user.is_staff:
        qs = qs.filter(session__circle__teacher=request.user)
    keys = thumn_start_keys()
    headers = ["الطالب", "نوع الحصة", "من سورة", "من آية", "إلى سورة", "إلى آية",
               "الثمن", "المقدار (حزب/ثمن)", "الصفحات", "النقطة /20", "الدرجة",
               "ملاحظات", "التاريخ"]
    rows = (
        (r.student.full_name_ar, r.get_log_category_display(),
         r.surah.name_ar, r.start_ayah, r.surah.name_ar, r.end_ayah,
         *_thumn_columns(r.surah_id, r.start_ayah, r.end_ayah, keys),
         r.completed_pages or 0,
         r.points if r.points is not None else "",
         r.evaluation_grade, r.teacher_notes[:50] if r.teacher_notes else "",
         r.created_at.date())
        for r in qs.iterator(chunk_size=500)
    )
    return CSVRenderer("grades.csv").render(headers, rows)


def _export_tasks(request, start, end):
    from apps.memorization.models import StudyTask
    qs = StudyTask.objects.select_related(
        "student", "assigned_by", "surah", "circle", "session"
    )
    if start:
        qs = qs.filter(created_at__gte=start)
    if end:
        qs = qs.filter(created_at__lte=end)
    if not request.user.is_staff:
        qs = qs.filter(student__enrollments__circle__teacher=request.user).distinct()
    headers = ["الطالب", "نوع المهمة", "السورة", "من آية", "إلى آية",
               "تاريخ الاستحقاق", "الحالة", "الحلقة", "الحصة المرتبطة",
               "المسند من", "تاريخ الإسناد", "تاريخ الإنجاز"]
    rows = (
        (t.student.full_name_ar, t.get_task_type_display(), t.surah.name_ar,
         t.ayah_from, t.ayah_to,
         t.due_date or "", t.get_status_display(),
         t.circle.name if t.circle else "",
         t.session.session_date if t.session else "",
         t.assigned_by.full_name_ar if t.assigned_by else "",
         t.created_at.date(), t.completed_at.date() if t.completed_at else "")
        for t in qs.iterator(chunk_size=500)
    )
    return CSVRenderer("tasks.csv").render(headers, rows)

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.shortcuts import render
from django.utils.dateparse import parse_date
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.http import require_GET

from apps.reports.utils import CSVRenderer
from apps.references.utils import count_thumns, format_hizb_thumn, thumn_span, thumn_start_keys

def _parse_date_param(raw):
    """Parse a YYYY-MM-DD query param. Returns (date-or-None, ok):
    empty → (None, True); valid → (date, True); malformed → (None, False)."""
    if not raw:
        return None, True
    try:
        parsed = parse_date(raw)
    except ValueError:  # well-formed but impossible date, e.g. 2026-02-30
        return None, False
    return parsed, parsed is not None


@require_GET
@login_required
def report_csv_export(request):
    # Empty type keeps the historical default (attendance); an unknown type is
    # rejected instead of silently serving the wrong report.
    report_type = request.GET.get("type", "") or "attendance"
    export = _EXPORTS.get(report_type)
    if export is None:
        return HttpResponseBadRequest("نوع تقرير غير معروف")

    start, start_ok = _parse_date_param(request.GET.get("start", ""))
    end, end_ok = _parse_date_param(request.GET.get("end", ""))
    if not (start_ok and end_ok):
        return HttpResponseBadRequest("صيغة تاريخ غير صالحة (المطلوب: YYYY-MM-DD)")

    return export(request, start, end)


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


def _scoped_progress_logs(request, start, end, category=None):
    """The one queryset builder for ProgressLog-based exports. Do not
    reintroduce reads of the deprecated MemorizationProgress here — canonical
    progress data lives in ProgressLog (the table session reports and
    StudentAchievement read). The legacy table is now fully read-only (its
    last writers — the teacher lesson toggle and the memorization-progress
    API write actions — were removed); it holds historical rows only, pending
    the retirement backfill.
    `start`/`end` are dates; the range is inclusive of both whole days."""
    from apps.memorization.models import ProgressLog
    qs = ProgressLog.objects.select_related("student", "surah", "session__circle")
    if category is not None:
        qs = qs.filter(log_category=category)
    if start:
        qs = qs.filter(created_at__date__gte=start)
    if end:
        qs = qs.filter(created_at__date__lte=end)
    if not request.user.is_staff:
        qs = qs.filter(session__circle__teacher=request.user)
    return qs


def _export_progress_category(request, start, end, category, filename):
    qs = _scoped_progress_logs(request, start, end, category)
    keys = thumn_start_keys()
    headers = ["الطالب", "من سورة", "من آية", "إلى سورة", "إلى آية",
               "الثمن", "المقدار (حزب/ثمن)", "النقطة /20", "الدرجة",
               "الحلقة", "التاريخ"]
    rows = (
        (r.student.full_name_ar,
         r.surah.name_ar if r.surah_id else "—", r.start_ayah or "",
         r.surah.name_ar if r.surah_id else "—", r.end_ayah or "",
         *(_thumn_columns(r.surah_id, r.start_ayah, r.end_ayah, keys)
           if r.surah_id else ("", format_hizb_thumn(r.total_thumns))),
         r.points if r.points is not None else "",
         r.evaluation_grade,
         r.session.circle.name if r.session_id else "",
         r.created_at.date())
        for r in qs.iterator(chunk_size=500)
    )
    return CSVRenderer(filename).render(headers, rows)


def _export_grades(request, start, end):
    qs = _scoped_progress_logs(request, start, end)
    keys = thumn_start_keys()
    headers = ["الطالب", "نوع الحصة", "من سورة", "من آية", "إلى سورة", "إلى آية",
               "الثمن", "المقدار (حزب/ثمن)", "الصفحات", "النقطة /20", "الدرجة",
               "ملاحظات", "التاريخ"]
    rows = (
        (r.student.full_name_ar, r.get_log_category_display(),
         r.surah.name_ar if r.surah_id else "—", r.start_ayah or "",
         r.surah.name_ar if r.surah_id else "—", r.end_ayah or "",
         *(_thumn_columns(r.surah_id, r.start_ayah, r.end_ayah, keys)
           if r.surah_id else ("", format_hizb_thumn(r.total_thumns))),
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
        qs = qs.filter(created_at__date__gte=start)
    if end:
        qs = qs.filter(created_at__date__lte=end)
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


# Resolved at call time, so definition order above doesn't matter.
_EXPORTS = {
    "attendance": _export_attendance,
    "hifz": _export_hifz,
    "murajaa": _export_murajaa,
    "grades": _export_grades,
    "tasks": _export_tasks,
}

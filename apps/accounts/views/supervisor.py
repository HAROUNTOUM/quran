"""General Supervisor batch→group follow-up board (requirement #3).

Read-only oversight surface for المشرف العام / المسؤول الأعلى:

    اختر الدفعة  →  اختر الفوج  →  لوحة المتابعة

The board aggregates, per student, the attendance symbols across every session
(✅ حضر / ⭕ غائب بعذر / ❌ غائب بغير عذر) plus the حفظ/مراجعة amounts — all
rolled up automatically from the existing Attendance and ProgressLog records
that teachers fill after each session. Nothing here is entered by hand.
"""
from collections import defaultdict

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, render

from apps.accounts import scoping
from apps.accounts.decorators import role_required
from apps.accounts.models import User, Batch
from apps.attendance.models import Attendance
from apps.circles.models import Circle, CircleEnrollment
from apps.memorization.models import ProgressLog

# Attendance status (stored value) → supervisor symbol.
_PRESENT = {
    Attendance.Status.PRESENT.value,
    Attendance.Status.LATE.value,
    Attendance.Status.LEFT_EARLY.value,
}
_EXCUSED = {
    Attendance.Status.ABSENT_JUSTIFIED.value,
    Attendance.Status.EXCUSED.value,
}
_UNEXCUSED = {
    Attendance.Status.ABSENT_UNJUSTIFIED.value,
    Attendance.Status.ABSENT.value,
}


def _symbol(status):
    """Map an Attendance.status to the legend symbol. Unknown / not-yet-marked
    statuses (not_responded, confirmed) render as an empty cell."""
    if status in _PRESENT:
        return "✅"
    if status in _EXCUSED:
        return "⭕"
    if status in _UNEXCUSED:
        return "❌"
    return ""


@login_required
@role_required(User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN)
def supervisor_groups(request):
    """Step 1+2: pick a batch (الدفعة), then see its groups (الأفواج)."""
    user = request.user
    if user.role == User.Role.MAIN_ADMIN:
        batches = list(Batch.objects.all().order_by("-created_at"))
    else:
        # Covers both the legacy `sub_admin` FK and the newer `sub_admins` M2M.
        batches = list(scoping.scoped_batches(user))
        if not batches:
            return render(request, "dashboard/supervisor/groups.html", {
                "batches": [], "selected_batch": None, "groups": [],
            })

    allowed_ids = {b.pk for b in batches}

    raw = request.GET.get("batch")
    selected_batch = None
    if raw:
        try:
            candidate = int(raw)
        except (TypeError, ValueError):
            candidate = None
        # Only honour a requested batch the user is actually allowed to see.
        if candidate in allowed_ids:
            selected_batch = candidate
    if selected_batch is None and batches:
        selected_batch = batches[0].pk

    groups_qs = Circle.objects.select_related("teacher").filter(batch_id=selected_batch)

    groups = []
    for circle in groups_qs.order_by("name"):
        last = circle.sessions.order_by("-session_date").first()
        groups.append({
            "circle": circle,
            "teacher": circle.teacher,
            "last_session": last.session_date if last else None,
            "student_count": circle.enrollments.filter(
                status=CircleEnrollment.Status.ACTIVE
            ).count(),
        })

    return render(request, "dashboard/supervisor/groups.html", {
        "batches": batches,
        "selected_batch": selected_batch,
        "groups": groups,
    })


@login_required
@role_required(User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN)
def supervisor_group_board(request, pk):
    """Step 3: the per-student follow-up board for one group (فوج)."""
    user = request.user
    circle = get_object_or_404(Circle.objects.select_related("teacher"), pk=pk)
    if user.role == User.Role.SUB_ADMIN and not Batch.objects.filter(
        Q(sub_admin=user) | Q(sub_admins=user), pk=circle.batch_id,
    ).exists():
        raise PermissionDenied

    sessions = list(circle.sessions.order_by("session_date", "id"))
    session_ids = [s.id for s in sessions]
    last_session = sessions[-1] if sessions else None

    enrollments = (
        circle.enrollments.filter(status=CircleEnrollment.Status.ACTIVE)
        .select_related("student")
        .order_by("student__full_name_ar")
    )
    students = [e.student for e in enrollments]
    student_ids = [s.id for s in students]

    # (student_id, session_id) → symbol, from one flat query.
    att_map = {}
    if session_ids and student_ids:
        for a in Attendance.objects.filter(
            session_id__in=session_ids, student_id__in=student_ids
        ).values("student_id", "session_id", "status"):
            att_map[(a["student_id"], a["session_id"])] = _symbol(a["status"])

    # حفظ/مراجعة amounts, per student — totals + last-session slice, one query.
    total_hifz = defaultdict(float)
    total_muraja = defaultdict(float)
    last_hifz = defaultdict(float)
    last_muraja = defaultdict(float)
    last_id = last_session.id if last_session else None
    if session_ids and student_ids:
        for p in ProgressLog.objects.filter(
            session_id__in=session_ids, student_id__in=student_ids
        ).values("student_id", "session_id", "log_category", "completed_pages"):
            pages = float(p["completed_pages"] or 0)
            sid = p["student_id"]
            if p["log_category"] == ProgressLog.Category.HIFDH.value:
                total_hifz[sid] += pages
                if p["session_id"] == last_id:
                    last_hifz[sid] += pages
            elif p["log_category"] == ProgressLog.Category.MURAJAAH.value:
                total_muraja[sid] += pages
                if p["session_id"] == last_id:
                    last_muraja[sid] += pages

    rows = []
    for s in students:
        rows.append({
            "student": s,
            "symbols": [att_map.get((s.id, sid), "") for sid in session_ids],
            "last_hifz": round(last_hifz[s.id], 2),
            "last_muraja": round(last_muraja[s.id], 2),
            "total_hifz": round(total_hifz[s.id], 2),
            "total_muraja": round(total_muraja[s.id], 2),
        })

    group_last_total = round(sum(last_hifz.values()) + sum(last_muraja.values()), 2)
    group_all_total = round(sum(total_hifz.values()) + sum(total_muraja.values()), 2)

    return render(request, "dashboard/supervisor/board.html", {
        "circle": circle,
        "sessions": sessions,
        "last_session": last_session,
        "rows": rows,
        "group_last_total": group_last_total,
        "group_all_total": group_all_total,
    })

"""Admin/supervisor exam-management views.

Extracted from the oversized ``accounts/views/admin.py`` as the first step of
the strangler refactor (see ``docs/architecture-audit-2026-07-11.md``). The
URL names are unchanged (still ``accounts:admin_exam_*``); this module is
re-exported from ``accounts.views.__init__``.

Note: the exam service functions (``create_exam``/``notify_published``/
``approve_all_marks``/``reject_marks``) were *used but never imported* in the
old god-file, which meant every exam write path raised ``NameError`` at
runtime. They are imported explicitly here, which fixes that latent bug.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.accounts.decorators import role_required
from apps.accounts.models import User
from apps.accounts.scoping import check_batch_access as _check_batch_access
from apps.accounts.scoping import scoped_batch_ids as _scoped_batch_ids
from apps.accounts.scoping import scoped_circles as _scoped_circles
from apps.accounts.scoping import scoped_users as _scoped_users
from apps.circles.models import Circle, CircleEnrollment
from apps.exams.models import Exam, ExamMark
from apps.exams.services import (
    approve_all_marks,
    create_exam,
    notify_published,
    reject_marks,
)


def _clean_exam_fields(request, default_date):
    """Parse exam_date / max_marks / pass_percentage from POST.

    Returns ``(exam_date, max_marks, pass_percentage, error)``. ``error`` is a
    non-empty Arabic message when a value is malformed, in which case the view
    should re-render the form instead of crashing. ``parse_date`` raises
    ValueError on a well-formed-but-invalid date (e.g. 2026-13-01), and float()
    raises on non-numeric input — both are handled here.
    """
    raw_date = request.POST.get("exam_date", "").strip()
    if raw_date:
        try:
            exam_date = parse_date(raw_date)
        except ValueError:
            exam_date = None
        if exam_date is None:
            return None, None, None, "تاريخ الامتحان غير صالح"
    else:
        exam_date = default_date
    try:
        max_marks = float(request.POST.get("max_marks") or 100)
        pass_percentage = float(request.POST.get("pass_percentage") or 50)
    except (TypeError, ValueError):
        return None, None, None, "الدرجة القصوى ونسبة النجاح يجب أن تكونا أرقاماً"
    return exam_date, max_marks, pass_percentage, None


@login_required
@role_required(User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN)
def report_exam_results(request):
    marks = ExamMark.objects.filter(
        status=ExamMark.Status.APPROVED,
        exam__status=Exam.Status.COMPLETED,
    ).select_related("exam__circle", "student", "approved_by").order_by("-exam__exam_date")
    students_data = {}
    for m in marks:
        sid = m.student_id
        if sid not in students_data:
            students_data[sid] = {
                "student": m.student,
                "total_exams": 0,
                "percentages": [],
                "last_exam_date": m.exam.exam_date,
                "last_circle": m.exam.circle.name if m.exam.circle else None,
            }
        sd = students_data[sid]
        sd["total_exams"] += 1
        sd["percentages"].append(m.percentage)
        if m.exam.exam_date >= sd["last_exam_date"]:
            sd["last_exam_date"] = m.exam.exam_date
            sd["last_circle"] = m.exam.circle.name if m.exam.circle else sd["last_circle"]
    exam_data = []
    for sid, sd in students_data.items():
        pcts = sd["percentages"]
        exam_data.append({
            "student": sd["student"],
            "total_exams": sd["total_exams"],
            "avg_score": round(sum(pcts) / len(pcts), 1),
            "last_exam_date": sd["last_exam_date"],
            "last_circle": sd["last_circle"],
        })
    exam_data.sort(key=lambda x: x["avg_score"], reverse=True)
    return render(request, "dashboard/reports/exam_results.html", {
        "exam_data": exam_data,
        "total_students": len(exam_data),
        "overall_avg": round(sum(e["avg_score"] for e in exam_data) / max(len(exam_data), 1), 1),
    })


@login_required
@role_required(User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN)
def admin_exam_list(request):
    batch_ids = _scoped_batch_ids(request.user)
    exams = Exam.objects.select_related("circle", "created_by", "assigned_teacher").annotate(
        student_count_annotated=Count("marks"),
        average_marks_annotated=Avg("marks__marks_obtained"),
        approved_count=Count("marks", filter=Q(marks__status=ExamMark.Status.APPROVED)),
        pending_count=Count("marks", filter=Q(marks__status=ExamMark.Status.PENDING)),
        rejected_count=Count("marks", filter=Q(marks__status=ExamMark.Status.REJECTED)),
    )
    if batch_ids is not None:
        exams = exams.filter(circle__batch_id__in=batch_ids)
    return render(request, "dashboard/exams/list.html", {"exams": exams})


@login_required
@role_required(User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN)
def admin_exam_create(request):
    circles = _scoped_circles(request.user, Circle.objects.filter(status=Circle.Status.ACTIVE))
    teachers = _scoped_users(request.user, User.objects.filter(role=User.Role.TEACHER, is_approved=User.ApprovalStatus.APPROVED, is_active=True))
    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        if not title:
            return render(request, "dashboard/exams/create.html", {
                "circles": circles, "teachers": teachers, "error": "عنوان الامتحان مطلوب"
            })
        circle_id = request.POST.get("circle") or None
        if circle_id and not circles.filter(pk=circle_id).exists():
            return render(request, "dashboard/exams/create.html", {
                "circles": circles, "teachers": teachers, "error": "الحلقة المختارة خارج نطاق إشرافك",
            })
        assigned_teacher_id = request.POST.get("assigned_teacher") or None
        if assigned_teacher_id and not teachers.filter(pk=assigned_teacher_id).exists():
            return render(request, "dashboard/exams/create.html", {
                "circles": circles, "teachers": teachers, "error": "المعلم المختار خارج نطاق إشرافك",
            })
        exam_date, max_marks, pass_percentage, err = _clean_exam_fields(request, timezone.now().date())
        if err:
            return render(request, "dashboard/exams/create.html", {
                "circles": circles, "teachers": teachers, "error": err,
            })
        data = {
            "title": title,
            "description": request.POST.get("description", ""),
            "exam_type": request.POST.get("exam_type", "monthly"),
            "circle_id": circle_id,
            "assigned_teacher_id": assigned_teacher_id,
            "exam_date": exam_date,
            "max_marks": max_marks,
            "pass_percentage": pass_percentage,
            "auto_publish": request.POST.get("auto_publish") == "on",
        }
        exam = create_exam(data, request.user)
        messages.success(request, "تم إنشاء الامتحان بنجاح")
        return redirect("accounts:admin_exam_detail", pk=exam.pk)
    return render(request, "dashboard/exams/create.html", {"circles": circles, "teachers": teachers})


@login_required
@role_required(User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN)
def admin_exam_edit(request, pk):
    exam = get_object_or_404(Exam, pk=pk)
    _check_batch_access(request.user, exam.circle.batch_id if exam.circle else None)
    circles = _scoped_circles(request.user, Circle.objects.filter(status=Circle.Status.ACTIVE))
    teachers = _scoped_users(request.user, User.objects.filter(role=User.Role.TEACHER, is_approved=User.ApprovalStatus.APPROVED, is_active=True))
    if request.method == "POST":
        exam.title = request.POST.get("title", exam.title)
        exam.description = request.POST.get("description", "")
        exam.exam_type = request.POST.get("exam_type", exam.exam_type)
        new_circle_id = request.POST.get("circle") or None
        if new_circle_id and not circles.filter(pk=new_circle_id).exists():
            messages.error(request, "الحلقة المختارة خارج نطاق إشرافك")
            return render(request, "dashboard/exams/edit.html", {
                "exam": exam, "circles": circles, "teachers": teachers,
            })
        exam.circle_id = new_circle_id
        new_teacher_id = request.POST.get("assigned_teacher") or None
        if new_teacher_id and not teachers.filter(pk=new_teacher_id).exists():
            messages.error(request, "المعلم المختار خارج نطاق إشرافك")
            return render(request, "dashboard/exams/edit.html", {
                "exam": exam, "circles": circles, "teachers": teachers,
            })
        exam.assigned_teacher_id = new_teacher_id
        exam_date, max_marks, pass_percentage, err = _clean_exam_fields(request, exam.exam_date)
        if err:
            messages.error(request, err)
            return render(request, "dashboard/exams/edit.html", {
                "exam": exam, "circles": circles, "teachers": teachers,
            })
        exam.exam_date = exam_date
        exam.max_marks = max_marks
        exam.pass_percentage = pass_percentage
        exam.save()
        messages.success(request, "تم تحديث الامتحان")
        return redirect("accounts:admin_exam_detail", pk=exam.pk)
    return render(request, "dashboard/exams/edit.html", {
        "exam": exam, "circles": circles, "teachers": teachers,
    })


@login_required
@role_required(User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN)
def admin_exam_detail(request, pk):
    exam = get_object_or_404(
        Exam.objects.select_related("circle", "created_by", "assigned_teacher"),
        pk=pk,
    )
    _check_batch_access(request.user, exam.circle.batch_id if exam.circle else None)
    marks = exam.marks.select_related("student", "entered_by", "approved_by").all()
    enrolled_students = []
    if exam.circle:
        enrolled_students = list(User.objects.filter(
            enrollments__circle=exam.circle,
            enrollments__status=CircleEnrollment.Status.ACTIVE,
            role=User.Role.STUDENT,
        ).distinct())
    else:
        enrolled_students = list(User.objects.filter(
            role=User.Role.STUDENT, is_approved=User.ApprovalStatus.APPROVED
        ))
    existing_marks = {m.student_id: m for m in marks}
    history = exam.approval_history.select_related("performed_by").all()[:20]
    approval_progress = exam.approval_progress()
    return render(request, "dashboard/exams/detail.html", {
        "exam": exam, "marks": marks,
        "enrolled_students": enrolled_students,
        "existing_marks": existing_marks,
        "history": history,
        "approval_progress": approval_progress,
    })


@login_required
@role_required(User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN)
def admin_exam_delete(request, pk):
    exam = get_object_or_404(Exam, pk=pk)
    _check_batch_access(request.user, exam.circle.batch_id if exam.circle else None)
    if request.method != "POST":
        return redirect("accounts:admin_exam_detail", pk=exam.pk)
    exam.delete()
    messages.success(request, "تم حذف الامتحان")
    return redirect("accounts:admin_exam_list")


@login_required
@role_required(User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN)
def admin_exam_publish(request, pk):
    exam = get_object_or_404(Exam, pk=pk)
    _check_batch_access(request.user, exam.circle.batch_id if exam.circle else None)
    if request.method != "POST":
        return redirect("accounts:admin_exam_detail", pk=exam.pk)
    exam.status = Exam.Status.PUBLISHED
    exam.save(update_fields=["status"])
    notify_published(exam, request.user)
    messages.success(request, "تم نشر الامتحان")
    return redirect("accounts:admin_exam_detail", pk=exam.pk)


@login_required
@role_required(User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN)
def admin_exam_approve_all(request, pk):
    exam = get_object_or_404(Exam, pk=pk)
    _check_batch_access(request.user, exam.circle.batch_id if exam.circle else None)
    if request.method != "POST":
        return redirect("accounts:admin_exam_detail", pk=exam.pk)
    approve_all_marks(exam, request.user)
    messages.success(request, "تم اعتماد جميع النتائج")
    return redirect("accounts:admin_exam_detail", pk=exam.pk)


@login_required
@role_required(User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN)
def admin_exam_reject_marks(request, pk):
    exam = get_object_or_404(Exam, pk=pk)
    _check_batch_access(request.user, exam.circle.batch_id if exam.circle else None)
    if request.method != "POST":
        messages.error(request, "طلب غير صالح")
        return redirect("accounts:admin_exam_detail", pk=exam.pk)
    mark_ids = request.POST.getlist("mark_ids")
    reason = request.POST.get("reason", "")
    if not mark_ids:
        messages.error(request, "لم يتم تحديد درجات للرفض")
        return redirect("accounts:admin_exam_detail", pk=exam.pk)
    reject_marks(exam, [int(m) for m in mark_ids], request.user, reason)
    messages.success(request, "تم رفض الدرجات المحددة")
    return redirect("accounts:admin_exam_detail", pk=exam.pk)


@login_required
@role_required(User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN)
def admin_exam_export_pdf(request, pk):
    from apps.exams.services import get_export_data
    from apps.exams.utils import generate_exam_pdf
    exam = get_object_or_404(Exam, pk=pk)
    _check_batch_access(request.user, exam.circle.batch_id if exam.circle else None)
    export_data = get_export_data(exam)
    pdf_bytes = generate_exam_pdf(export_data)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="exam_{exam.exam_code}.pdf"'
    return response


@login_required
@role_required(User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN)
def admin_exam_export_csv(request, pk):
    from apps.exams.services import get_export_data
    from apps.exams.utils import generate_exam_csv
    exam = get_object_or_404(Exam, pk=pk)
    _check_batch_access(request.user, exam.circle.batch_id if exam.circle else None)
    export_data = get_export_data(exam)
    csv_str = generate_exam_csv(export_data)
    response = HttpResponse(csv_str, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="exam_{exam.exam_code}.csv"'
    return response

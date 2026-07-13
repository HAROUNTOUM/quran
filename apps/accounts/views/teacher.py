import json

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from apps.accounts.decorators import role_required
from django.http import JsonResponse
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.core.paginator import Paginator
from django.utils import timezone
from datetime import date, timedelta

from apps.accounts.models import User, TeacherAbsence
from apps.circles.models import Circle, CircleEnrollment, Session, SessionRescheduleRequest
from apps.attendance.models import Attendance
from apps.requests.models import SupportRequest
from apps.announcements.models import Announcement
from apps.notifications.models import Notification
from apps.memorization.models import MemorizationProgress, RecitationGrade, StudentAchievement, ReviewRequest, StudyTask
from apps.exams.models import Exam
from apps.exams.services import (
    verify_teacher_assignment,
    verify_exam_status,
    validate_mark_value,
    save_mark,
    submit_for_approval,
    get_export_data,
)
from apps.exams.utils import generate_exam_pdf
from apps.references.models import Surah, EvaluationCriterion

@login_required
@role_required(User.Role.TEACHER)
def teacher_dashboard(request):

    circles = Circle.objects.filter(teacher=request.user, status=Circle.Status.ACTIVE).annotate(
        active_students=Count('enrollments', filter=Q(enrollments__status=CircleEnrollment.Status.ACTIVE)),
        total_sessions=Count('sessions'),
    )

    today_sessions = Session.objects.filter(
        circle__teacher=request.user,
        session_date=date.today(),
    ).select_related('circle')

    circles_list = list(circles)
    total_active_students = sum(c.active_students for c in circles_list)
    total_sessions = sum(c.total_sessions for c in circles_list)

    return render(request, 'dashboard/teacher/home.html', {
        'circles': circles_list,
        'today_sessions': today_sessions,
        'total_active_students': total_active_students,
        'total_sessions': total_sessions,
        'room': request.user.get_or_create_room(),
    })
@login_required
@role_required(User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN, User.Role.TEACHER)
def teacher_session_attendance(request, pk):

    sessions = Session.objects.select_related('circle')
    if request.user.role == User.Role.TEACHER:
        sessions = sessions.filter(circle__teacher=request.user)

    session = get_object_or_404(sessions, pk=pk)

    students = User.objects.filter(
        enrollments__circle=session.circle,
        enrollments__status=CircleEnrollment.Status.ACTIVE,
    ).order_by('full_name_ar')

    existing_attendance = {
        str(a.student_id): a.status
        for a in Attendance.objects.filter(session=session)
    }

    criteria = EvaluationCriterion.objects.filter(is_active=True)
    existing_grades = {}
    for g in RecitationGrade.objects.filter(session=session).select_related('criterion'):
        key = (str(g.student_id), g.criterion_id)
        existing_grades[key] = g.score

    # Build student rows with pre-processed data
    student_rows = []
    for student in students:
        sid = str(student.id)
        grade_cells = []
        for c in criteria:
            grade_cells.append({
                'criterion_id': c.id,
                'score': existing_grades.get((sid, c.id), ''),
            })
        student_rows.append({
            'student_id': sid,
            'student_name': student.full_name_ar,
            'attendance': existing_attendance.get(sid, ''),
            'grades': grade_cells,
        })

    attendance_choices = Attendance.Status.choices

    if request.method == 'POST':
        if session.status != Session.Status.LIVE:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'error': 'لا يمكن تسجيل الحضور إلا أثناء الحصة'}, status=400)
            messages.error(request, "لا يمكن تسجيل الحضور إلا أثناء الحصة")
            return redirect('accounts:teacher_session_attendance', pk=pk)
        for student in students:
            sid = str(student.id)
            status_val = request.POST.get(f'attendance_{sid}')
            if status_val and status_val in dict(Attendance.Status.choices):
                Attendance.objects.update_or_create(
                    session=session,
                    student=student,
                    defaults={'status': status_val},
                )

            for criterion in criteria:
                score_key = f'grade_{sid}_{criterion.id}'
                score_val = request.POST.get(score_key)
                if score_val is not None and score_val != '':
                    try:
                        score = float(score_val)
                        max_score = float(request.POST.get(f'max_{sid}_{criterion.id}', 100))
                        RecitationGrade.objects.update_or_create(
                            session=session,
                            student=student,
                            criterion=criterion,
                            defaults={'score': score, 'max_score': max_score},
                        )
                    except (ValueError, TypeError):
                        pass

        is_htmx = getattr(request, "htmx", None)
        if is_htmx or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return render(request, 'dashboard/teacher/partials/attendance_form.html', {
                'session': session,
                'student_rows': student_rows,
                'criteria': criteria,
                'attendance_choices': attendance_choices,
            })

        return redirect('accounts:teacher_session_attendance', pk=pk)

    return render(request, 'dashboard/teacher/session_attendance.html', {
        'session': session,
        'student_rows': student_rows,
        'criteria': criteria,
        'attendance_choices': attendance_choices,
    })
@login_required
@role_required(User.Role.TEACHER)
def teacher_session_create(request, circle_pk):

    circle = get_object_or_404(
        Circle, pk=circle_pk, teacher=request.user, status=Circle.Status.ACTIVE,
    )

    if request.method == 'POST':
        from datetime import datetime
        session_date_str = request.POST.get('session_date', '')
        if session_date_str:
            try:
                session_date = datetime.strptime(session_date_str, '%Y-%m-%d').date()
            except ValueError:
                session_date = date.today()
        else:
            session_date = date.today()

        session_time_str = request.POST.get('session_time', '').strip()
        session_time = None
        if session_time_str:
            try:
                session_time = datetime.strptime(session_time_str, '%H:%M').time()
            except ValueError:
                pass

        location = request.POST.get("location", "")

        if Session.objects.filter(circle=circle, session_date=session_date).exists():
            messages.error(request, "يوجد حصة بالفعل لهذه الحلقة في هذا التاريخ")
            return render(request, 'dashboard/teacher/session_create.html', {
                'circle': circle,
                'today': date.today(),
                'circle_schedule_time': circle.schedule_time,
            })

        start_time = None
        if session_time and session_date:
            from django.utils import timezone as tz
            tzinfo = tz.get_current_timezone()
            start_time = tz.make_aware(
                datetime.combine(session_date, session_time), tzinfo,
            )

        Session.objects.create(
            circle=circle,
            session_date=session_date,
            session_time=session_time,
            start_time=start_time,
            status=Session.Status.SCHEDULED,
            session_type=request.POST.get("session_type", Session.Type.IN_PERSON),
            location=location,
            meeting_source=request.POST.get("meeting_source", Session.MeetingSource.CLASSROOM),
            meeting_url=request.POST.get("meeting_url", ""),
            meeting_platform=request.POST.get("meeting_platform", ""),
            meeting_id=request.POST.get("meeting_id", ""),
            meeting_password=request.POST.get("meeting_password", ""),
            duration_minutes=request.POST.get("duration_minutes") or None,
            notes=request.POST.get("notes", ""),
        )
        messages.success(request, "تم إنشاء الحصة")
        return redirect('accounts:teacher_circle_detail', pk=circle_pk)

    return render(request, 'dashboard/teacher/session_create.html', {
        'circle': circle,
        'today': date.today(),
        'circle_schedule_time': circle.schedule_time,
    })
@login_required
@role_required(User.Role.TEACHER)
def teacher_session_manage(request):

    circles = Circle.objects.filter(teacher=request.user, status=Circle.Status.ACTIVE).annotate(
        active_students=Count("enrollments", filter=Q(enrollments__status=CircleEnrollment.Status.ACTIVE)),
        total_sessions=Count("sessions"),
        recent_sessions=Count("sessions", filter=Q(sessions__session_date__gte=date.today() - timedelta(days=30))),
        pending_reviews=Count("enrollments__memorization_progress", filter=Q(
            enrollments__memorization_progress__status=MemorizationProgress.Status.MEMORIZING,
        )),
    )

    all_pending = sum(c.pending_reviews for c in circles)
    total_students = sum(c.active_students for c in circles)
    total_sessions = sum(c.total_sessions for c in circles)

    recent_sessions = Session.objects.filter(
        circle__teacher=request.user,
    ).select_related("circle").order_by("-session_date", "-session_time")[:10]

    return render(request, "dashboard/teacher/session_manage.html", {
        "circles": circles,
        "total_circles": len(circles),
        "total_students": total_students,
        "total_sessions": total_sessions,
        "all_pending": all_pending,
        "recent_sessions": recent_sessions,
    })
@login_required
@role_required(User.Role.TEACHER)
def teacher_session_progress(request, pk):

    circle = get_object_or_404(
        Circle.objects.annotate(
            active_students=Count("enrollments", filter=Q(enrollments__status=CircleEnrollment.Status.ACTIVE)),
        ),
        pk=pk, teacher=request.user, status=Circle.Status.ACTIVE,
    )

    progress = MemorizationProgress.objects.filter(
        enrollment__circle=circle,
        enrollment__status=CircleEnrollment.Status.ACTIVE,
    ).select_related("surah", "enrollment__student").order_by("-created_at")

    students = User.objects.filter(
        enrollments__circle=circle,
        enrollments__status=CircleEnrollment.Status.ACTIVE,
        role=User.Role.STUDENT,
    ).order_by("full_name_ar")

    # Build weekly progress data for chart
    weekly_data = []
    for i in range(8, 0, -1):
        week_start = date.today() - timedelta(days=i * 7)
        week_end = date.today() - timedelta(days=(i - 1) * 7)
        week_progress = MemorizationProgress.objects.filter(
            enrollment__circle=circle,
            created_at__date__gte=week_start,
            created_at__date__lt=week_end,
        )
        weekly_data.append({
            "week": f"الأسبوع {9 - i}",
            "hifz": week_progress.filter(type=MemorizationProgress.Type.HIFZ).count(),
            "murajaa": week_progress.filter(type=MemorizationProgress.Type.MURAJAA).count(),
            "mastered": week_progress.filter(status=MemorizationProgress.Status.MASTERED).count(),
        })

    mastered_count = progress.filter(status=MemorizationProgress.Status.MASTERED).count()

    sessions_list = Session.objects.filter(circle=circle).order_by("-session_date")[:20]
    surahs = Surah.objects.all().order_by("id")

    return render(request, "dashboard/teacher/session_progress.html", {
        "circle": circle,
        "students": students,
        "progress": progress,
        "mastered_count": mastered_count,
        "weekly_data": json.dumps(weekly_data, ensure_ascii=False),
        "sessions_list": sessions_list,
        "surahs": surahs,
    })
@login_required
@role_required(User.Role.TEACHER)
def teacher_absence_create(request):
    if request.method == "POST":
        from datetime import date

        start_date_str = request.POST.get("start_date", "")
        end_date_str = request.POST.get("end_date", "")
        reason = request.POST.get("reason", "").strip()
        if start_date_str and end_date_str and reason:
            # L08: parse + order-check the dates instead of passing raw
            # strings to create() (malformed input was a 500).
            try:
                start_date = date.fromisoformat(start_date_str)
                end_date = date.fromisoformat(end_date_str)
            except ValueError:
                messages.error(request, "صيغة التاريخ غير صحيحة")
                return render(request, "dashboard/teacher/absence_create.html")
            if start_date > end_date:
                messages.error(request, "تاريخ البداية يجب أن يكون قبل تاريخ النهاية")
                return render(request, "dashboard/teacher/absence_create.html")
            TeacherAbsence.objects.create(
                teacher=request.user,
                start_date=start_date,
                end_date=end_date,
                reason=reason,
            )
            messages.success(request, "تم إرسال طلب الغياب بنجاح")
            return redirect("accounts:teacher_absence_list")
        messages.error(request, "يرجى ملء جميع الحقول المطلوبة")
    return render(request, "dashboard/teacher/absence_create.html")
@login_required
@role_required(User.Role.TEACHER)
def teacher_absence_list(request):
    absences = TeacherAbsence.objects.filter(teacher=request.user)
    return render(request, "dashboard/teacher/absence_list.html", {
        "absences": absences,
    })
@login_required
@role_required(User.Role.TEACHER)
def teacher_circle_detail(request, pk):
    circle = get_object_or_404(
        Circle.objects.annotate(
            active_students_count=Count("enrollments", filter=Q(enrollments__status=CircleEnrollment.Status.ACTIVE)),
            sessions_count=Count("sessions"),
        ),
        pk=pk, teacher=request.user, status=Circle.Status.ACTIVE,
    )
    students = User.objects.filter(
        enrollments__circle=circle,
        enrollments__status=CircleEnrollment.Status.ACTIVE,
        role=User.Role.STUDENT,
    ).order_by("full_name_ar")
    from apps.attendance.models import SessionAttendanceIntent
    sessions = Session.objects.filter(circle=circle).select_related("circle").annotate(
        att_total=Count("attendance_records"),
        att_present=Count("attendance_records", filter=Q(
            attendance_records__status__in=[
                Attendance.Status.PRESENT, Attendance.Status.LATE, Attendance.Status.LEFT_EARLY,
            ]
        )),
        intent_attending=Count("attendance_intents", filter=Q(
            attendance_intents__intent=SessionAttendanceIntent.Intent.ATTENDING,
        )),
        intent_absent=Count("attendance_intents", filter=Q(
            attendance_intents__intent=SessionAttendanceIntent.Intent.ABSENT,
        )),
    ).order_by("-session_date", "-created_at")[:30]
    return render(request, "dashboard/teacher/circle_detail.html", {
        "circle": circle,
        "students": students,
        "sessions": sessions,
    })
@login_required
@role_required(User.Role.TEACHER)
def teacher_students(request):
    circles = Circle.objects.filter(teacher=request.user, status=Circle.Status.ACTIVE)
    students = User.objects.filter(
        enrollments__circle__in=circles,
        enrollments__status=CircleEnrollment.Status.ACTIVE,
        role=User.Role.STUDENT,
    ).distinct().order_by("full_name_ar")
    search = request.GET.get("search", "")
    circle_filter = request.GET.get("circle", "")
    if search:
        students = students.filter(
            Q(full_name_ar__icontains=search) | Q(email__icontains=search) | Q(phone__icontains=search)
        )
    if circle_filter:
        students = students.filter(enrollments__circle_id=circle_filter)
    return render(request, "dashboard/teacher/students.html", {
        "students": students,
        "circles": circles,
    })
@login_required
@role_required(User.Role.TEACHER)
def teacher_student_progress(request, pk):
    student = get_object_or_404(User, pk=pk, role=User.Role.STUDENT)
    circles = Circle.objects.filter(teacher=request.user, status=Circle.Status.ACTIVE)
    if not CircleEnrollment.objects.filter(
        student=student, circle__in=circles, status=CircleEnrollment.Status.ACTIVE
    ).exists():
        raise PermissionDenied
    # Live data: ProgressLog (session entries) + MemorizationRecord (per-rub
    # hifz status / SRS) — not the deprecated MemorizationProgress tracker.
    from apps.memorization.models import ProgressLog, MemorizationRecord
    from apps.memorization import review_engine

    logs = ProgressLog.objects.filter(
        student=student, session__circle__in=circles,
    ).select_related("surah", "session__circle").order_by("-created_at")
    stats = logs.aggregate(
        total=Count("id"),
        hifz=Count("id", filter=Q(log_category=ProgressLog.Category.HIFDH)),
        murajaa=Count("id", filter=Q(log_category=ProgressLog.Category.MURAJAAH)),
    )
    records = MemorizationRecord.objects.filter(student=student).exclude(
        status=MemorizationRecord.Status.NOT_MEMORIZED
    ).select_related("rub__hizb__juz").order_by("rub__number")
    stats["mastered"] = records.filter(status=MemorizationRecord.Status.MASTERED).count()
    achievement, _ = StudentAchievement.objects.get_or_create(student=student)
    return render(request, "dashboard/teacher/student_progress.html", {
        "student": student,
        "logs": logs,
        "records": records,
        "evaluations": list(review_engine.EVALUATION_MULTIPLIERS.keys()),
        "stats": stats,
        "achievement": achievement,
    })


@login_required
@role_required(User.Role.TEACHER)
def teacher_progress_log_edit(request, pk):
    """Correct a session entry (category, range, mark, remark) after the fact.
    Only the session's own teacher; achievement totals are rebuilt."""
    from apps.memorization.models import ProgressLog
    from apps.memorization import engine

    log = get_object_or_404(
        ProgressLog.objects.select_related("session__circle", "student", "surah"),
        pk=pk, session__circle__teacher=request.user,
    )
    surahs = Surah.objects.order_by("id")
    if request.method == "POST":
        try:
            points_raw = request.POST.get("points", "").strip()
            engine.update_progress_log(
                log, request.user,
                log_category=request.POST.get("log_category", log.log_category),
                surah=int(request.POST.get("surah", log.surah_id)),
                start_ayah=int(request.POST.get("start_ayah", log.start_ayah)),
                end_ayah=int(request.POST.get("end_ayah", log.end_ayah)),
                points=float(points_raw) if points_raw else None,
                evaluation_grade=request.POST.get("evaluation_grade", ""),
                teacher_notes=request.POST.get("teacher_notes", ""),
            )
        except (ValidationError, ValueError) as e:
            messages.error(request, getattr(e, "message", None) or "قيم غير صالحة — تحقق من الآيات والنقطة")
            return render(request, "dashboard/teacher/progress_log_edit.html", {
                "log": log, "surahs": surahs,
                "grades": ProgressLog.Grade.choices,
                "categories": ProgressLog.Category.choices,
            })
        messages.success(request, "تم تعديل التسجيل وإعادة احتساب الإنجاز")
        return redirect("accounts:teacher_session_detail", pk=log.session_id)
    return render(request, "dashboard/teacher/progress_log_edit.html", {
        "log": log, "surahs": surahs,
        "grades": ProgressLog.Grade.choices,
        "categories": ProgressLog.Category.choices,
    })


@login_required
@role_required(User.Role.TEACHER)
def teacher_progress_log_delete(request, pk):
    from apps.memorization.models import ProgressLog
    from apps.memorization import engine

    log = get_object_or_404(
        ProgressLog.objects.select_related("session__circle", "student"),
        pk=pk, session__circle__teacher=request.user,
    )
    session_id = log.session_id
    if request.method != "POST":
        return redirect("accounts:teacher_session_detail", pk=session_id)
    engine.delete_progress_log(log, request.user)
    messages.success(request, "تم حذف التسجيل وإعادة احتساب الإنجاز")
    return redirect("accounts:teacher_session_detail", pk=session_id)


@login_required
@role_required(User.Role.TEACHER)
def teacher_record_evaluate(request, student_id, record_pk):
    """Teacher evaluates a memorized rub: updates status (محفوظ/يحتاج مراجعة/
    ضعيف/متقن), reschedules the next review, and appends ReviewHistory."""
    from apps.memorization.models import MemorizationRecord

    student = get_object_or_404(User, pk=student_id, role=User.Role.STUDENT)
    record = get_object_or_404(MemorizationRecord, pk=record_pk, student=student)
    if request.method == "POST":
        try:
            record.evaluate(
                by=request.user,
                evaluation=request.POST.get("evaluation", ""),
                mistakes_count=int(request.POST.get("mistakes_count") or 0),
                notes=request.POST.get("notes", ""),
            )
            messages.success(request, f"تم تقييم {record.rub.label()} — الحالة: {record.get_status_display()}")
        except (ValidationError, ValueError) as e:
            messages.error(request, getattr(e, "message", None) or "تقييم غير صالح")
    return redirect("accounts:teacher_student_progress", pk=student_id)


@login_required
@role_required(User.Role.TEACHER)
def teacher_record_add(request, student_id):
    """Teacher records that a student has memorized a rub directly (outside
    the study-task flow) — creates/updates the MemorizationRecord and
    schedules its first review."""
    from apps.memorization.models import MemorizationRecord
    from apps.references.models import Rub

    student = get_object_or_404(User, pk=student_id, role=User.Role.STUDENT)
    if not request.user.teaches_student(student):
        raise PermissionDenied
    if request.method == "POST":
        try:
            rub_number = int(request.POST.get("rub_number", ""))
            rub = Rub.objects.get(number=rub_number)
        except (ValueError, Rub.DoesNotExist):
            messages.error(request, "رقم ربع غير صالح (1–240)")
            return redirect("accounts:teacher_student_progress", pk=student_id)
        circle = Circle.objects.filter(
            teacher=request.user, status=Circle.Status.ACTIVE,
            enrollments__student=student,
            enrollments__status=CircleEnrollment.Status.ACTIVE,
        ).first()
        record = MemorizationRecord.record_for(student, rub, circle=circle)
        if record.status == MemorizationRecord.Status.NOT_MEMORIZED:
            record.mark_memorized(by=request.user)
            messages.success(request, f"تم تسجيل حفظ {rub.label()} وجدولة أول مراجعة")
        else:
            messages.info(request, f"{rub.label()} مسجّل مسبقاً — الحالة: {record.get_status_display()}")
    return redirect("accounts:teacher_student_progress", pk=student_id)


@login_required
@role_required(User.Role.TEACHER, User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN)
def teacher_announcements(request):
    search = request.GET.get("search", "")
    announcements = Announcement.objects.select_related("author").order_by("-created_at")
    if search:
        announcements = announcements.filter(Q(title__icontains=search) | Q(body__icontains=search))
    paginator = Paginator(announcements, 15)
    page_obj = paginator.get_page(request.GET.get("page", 1))
    return render(request, "dashboard/teacher/announcements.html", {
        "announcements": page_obj,
        "page_obj": page_obj,
    })
@login_required
@role_required(User.Role.TEACHER, User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN)
def teacher_requests(request):
    qs = SupportRequest.objects.filter(submitted_by=request.user).select_related("submitted_by").order_by("-created_at")
    paginator = Paginator(qs, 15)
    page_obj = paginator.get_page(request.GET.get("page", 1))
    return render(request, "dashboard/teacher/requests.html", {
        "requests": page_obj,
        "page_obj": page_obj,
    })
@login_required
@role_required(User.Role.TEACHER)
def teacher_request_create(request):
    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        body = request.POST.get("body", "").strip()
        req_type = request.POST.get("type", "other")
        priority = request.POST.get("priority", "normal")
        if not title or not body:
            return render(request, "dashboard/teacher/request_create.html", {
                "error": "يرجى ملء جميع الحقول المطلوبة",
                "form_data": request.POST,
            })
        SupportRequest.objects.create(
            submitted_by=request.user,
            title=title,
            body=body,
            type=req_type,
            priority=priority,
        )
        messages.success(request, "تم إرسال الطلب بنجاح")
        return redirect("accounts:teacher_requests")
    return render(request, "dashboard/teacher/request_create.html")
@login_required
@role_required(User.Role.TEACHER, User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN)
def teacher_notifications(request):
    qs = Notification.objects.filter(recipient=request.user).order_by("-created_at")
    notif_type = request.GET.get("type", "")
    if notif_type:
        qs = qs.filter(type=notif_type)
    is_read = request.GET.get("is_read", "")
    if is_read in ("true", "false"):
        qs = qs.filter(is_read=(is_read == "true"))
    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get("page", 1))
    return render(request, "dashboard/teacher/notifications.html", {
        "notifications": page_obj,
        "page_obj": page_obj,
    })
@login_required
@role_required(User.Role.TEACHER)
def teacher_private_sessions(request):
    """Private (1-on-1) تسميع sessions the teacher runs: view + results marking."""
    from apps.memorization.models import PrivateSession
    if request.method == "POST":
        ps = get_object_or_404(
            PrivateSession, pk=request.POST.get("session_id"), teacher=request.user,
        )
        try:
            ps.mark_result(
                by=request.user,
                result_mark=request.POST.get("result_mark", ""),
                result_notes=request.POST.get("result_notes", ""),
            )
            messages.success(request, "تم تسجيل نتيجة الجلسة")
        except ValidationError as e:
            messages.error(request, " ".join(e.messages))
        return redirect("accounts:teacher_private_sessions")

    sessions = PrivateSession.objects.filter(
        teacher=request.user,
    ).select_related("student", "circle").order_by("-scheduled_date", "-created_at")
    status_filter = request.GET.get("status", "")
    if status_filter:
        sessions = sessions.filter(status=status_filter)
    paginator = Paginator(sessions, 20)
    page_obj = paginator.get_page(request.GET.get("page", 1))
    return render(request, "dashboard/teacher/private_sessions.html", {
        "sessions": page_obj,
        "page_obj": page_obj,
    })
@login_required
@role_required(User.Role.TEACHER)
def teacher_review_requests(request):
    review_requests = ReviewRequest.objects.filter(
        circle__teacher=request.user,
    ).select_related("student", "circle", "surah").order_by("-created_at")
    status_filter = request.GET.get("status", "")
    if status_filter:
        review_requests = review_requests.filter(status=status_filter)

    if request.method == "POST":
        from django.core.exceptions import ValidationError
        req_id = request.POST.get("request_id")
        req = get_object_or_404(ReviewRequest, pk=req_id, circle__teacher=request.user)
        action = request.POST.get("action")
        try:
            if action == "approve":
                request.user.respond_to_review_request(
                    req, "approve",
                    scheduled_date=request.POST.get("scheduled_date") or None,
                    scheduled_time=request.POST.get("scheduled_time") or None,
                    meeting_url=request.POST.get("meeting_url", ""),
                    meeting_platform=request.POST.get("meeting_platform", ""),
                )
                messages.success(request, "تم جدولة الطلب وإرساله للطالب")
            elif action == "reject":
                request.user.respond_to_review_request(
                    req, "reject", reason=request.POST.get("rejection_reason", ""),
                )
                messages.success(request, "تم رفض الطلب")
            elif action == "answer":
                request.user.respond_to_review_request(
                    req, "answer", response=request.POST.get("response", ""),
                )
                messages.success(request, "تم إرسال الرد إلى الطالب")
        except ValidationError as e:
            messages.error(request, " ".join(e.messages))
        return redirect("accounts:teacher_review_requests")

    paginator = Paginator(review_requests, 20)
    page_obj = paginator.get_page(request.GET.get("page", 1))
    DAY_LABELS = {"sat": "السبت", "sun": "الأحد", "mon": "الإثنين", "tue": "الثلاثاء", "wed": "الأربعاء", "thu": "الخميس", "fri": "الجمعة"}
    TIME_LABELS = {"fajr": "الفجر", "dhuhr": "الظهر", "asr": "العصر", "maghrib": "المغرب", "isha": "العشاء"}
    return render(request, "dashboard/teacher/review_requests.html", {
        "requests": page_obj,
        "page_obj": page_obj,
        "day_labels": DAY_LABELS,
        "time_labels": TIME_LABELS,
        "platform_choices": [
            ("zoom", "Zoom"), ("google_meet", "Google Meet"),
            ("teams", "Microsoft Teams"), ("whatsapp", "WhatsApp"),
            ("telegram", "Telegram"), ("other", "أخرى"),
        ],
    })
@login_required
@role_required(User.Role.TEACHER)
def teacher_reschedule_requests(request):
    if request.method == "POST":
        from django.core.exceptions import ValidationError
        req_id = request.POST.get("request_id")
        action = request.POST.get("action")
        req = get_object_or_404(SessionRescheduleRequest, pk=req_id, session__circle__teacher=request.user)
        try:
            if action == "approve":
                req.approve(by=request.user)
                messages.success(request, "تم قبول طلب تعديل الموعد")
            elif action == "reject":
                req.reject(by=request.user, reason=request.POST.get("rejection_reason", ""))
                messages.success(request, "تم رفض طلب تعديل الموعد")
        except ValidationError as e:
            messages.error(request, " ".join(e.messages))
        return redirect("accounts:teacher_reschedule_requests")

    reschedule_reqs = SessionRescheduleRequest.objects.filter(
        session__circle__teacher=request.user,
    ).select_related("session__circle", "requested_by").order_by("-created_at")
    status_filter = request.GET.get("status", "")
    if status_filter:
        reschedule_reqs = reschedule_reqs.filter(status=status_filter)
    paginator = Paginator(reschedule_reqs, 20)
    page_obj = paginator.get_page(request.GET.get("page", 1))
    return render(request, "dashboard/teacher/reschedule_requests.html", {
        "requests": page_obj,
        "page_obj": page_obj,
    })
@login_required
@role_required(User.Role.TEACHER)
def teacher_session_detail(request, pk):
    session = get_object_or_404(
        Session.objects.select_related("circle__teacher"),
        pk=pk, circle__teacher=request.user,
    )
    from apps.circles.models import SessionTurn
    turns = SessionTurn.objects.filter(session=session).select_related("student").order_by("turn_number")

    students = User.objects.filter(
        enrollments__circle=session.circle,
        enrollments__status=CircleEnrollment.Status.ACTIVE,
        role=User.Role.STUDENT,
    ).order_by("full_name_ar")

    student_ids_with_turns = set(t.student_id for t in turns)
    students_without_turns = [s for s in students if s.id not in student_ids_with_turns]

    attendance_records = {
        str(a.student_id): a
        for a in Attendance.objects.filter(session=session).select_related("student")
    }

    from apps.memorization.models import RecitationGrade
    grade_qs = RecitationGrade.objects.filter(session=session).select_related("criterion")
    grades_by_student = {}
    for g in grade_qs:
        sid = str(g.student_id)
        if sid not in grades_by_student:
            grades_by_student[sid] = []
        grades_by_student[sid].append(g)

    from apps.references.models import EvaluationCriterion
    all_criteria = EvaluationCriterion.objects.filter(is_active=True)

    student_attendance = []
    for student in students:
        att = attendance_records.get(str(student.id))
        student_attendance.append({
            "student": student,
            "attendance": att,
            "grades": grades_by_student.get(str(student.id), []),
        })

    present_count = sum(1 for a in attendance_records.values() if a.status == Attendance.Status.PRESENT)
    absent_count = sum(
        1 for a in attendance_records.values()
        if a.status in (Attendance.Status.ABSENT_UNJUSTIFIED, Attendance.Status.ABSENT)
    )
    excused_count = sum(
        1 for a in attendance_records.values()
        if a.status == Attendance.Status.ABSENT_JUSTIFIED
    )

    from apps.memorization.engine import session_report_data
    report_rows, todo_rows = session_report_data(session)

    return render(request, "dashboard/teacher/session_detail.html", {
        "session": session,
        "turns": turns,
        "students_without_turns": students_without_turns,
        "student_attendance": student_attendance,
        "present_count": present_count,
        "absent_count": absent_count,
        "excused_count": excused_count,
        "total_students": len(students),
        "all_criteria": all_criteria,
        "report_rows": report_rows,
        "todo_rows": todo_rows,
    })
@login_required
@role_required(User.Role.TEACHER)
def teacher_session_remove_turn(request, pk, student_id):
    session = get_object_or_404(
        Session.objects.select_related("circle__teacher"),
        pk=pk, circle__teacher=request.user,
    )
    from apps.circles.models import SessionTurn
    SessionTurn.objects.filter(session=session, student_id=student_id).delete()
    return JsonResponse({"success": True})
@login_required
@role_required(User.Role.TEACHER)
def teacher_session_reorder_turns(request, pk):
    session = get_object_or_404(
        Session.objects.select_related("circle__teacher"),
        pk=pk, circle__teacher=request.user,
    )
    from apps.circles.models import SessionTurn
    from django.db import transaction
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "طريقة غير مدعومة"}, status=405)
    try:
        data = json.loads(request.body or "{}")
    except (ValueError, json.JSONDecodeError):
        return JsonResponse({"success": False, "message": "بيانات غير صالحة"}, status=400)
    order = data.get("order", [])

    existing_ids = set(
        SessionTurn.objects.filter(session=session).values_list("student_id", flat=True)
    )
    invalid = [sid for sid in order if sid not in existing_ids]
    if invalid:
        return JsonResponse(
            {"success": False, "message": "بعض الطلاب ليس لديهم دور", "invalid_ids": invalid},
            status=400,
        )

    with transaction.atomic():
        turns = SessionTurn.objects.select_for_update().filter(session=session)
        offset = 10000
        turn_map = {str(t.student_id): t for t in turns}
        for i, student_id in enumerate(order, start=1):
            turn_map[student_id].turn_number = offset + i
        SessionTurn.objects.bulk_update(turn_map.values(), ["turn_number"])
        for t in turn_map.values():
            t.turn_number = t.turn_number - offset
        SessionTurn.objects.bulk_update(turn_map.values(), ["turn_number"])

    return JsonResponse({"success": True})
@login_required
@role_required(User.Role.TEACHER)
def teacher_session_advance_status(request, pk):
    session = get_object_or_404(
        Session.objects.select_related("circle"),
        pk=pk, circle__teacher=request.user,
    )
    if request.method == "POST":
        from apps.circles.models import CONFIRM_WINDOW_MINUTES, TURN_LOCK_MINUTES, SESSION_MAX_DURATION_MINUTES
        from datetime import timedelta

        now = timezone.now()
        start = session.start_time or now
        next_status = None

        if session.status == Session.Status.SCHEDULED:
            next_status = Session.Status.CONFIRMATION_OPEN
        elif session.status == Session.Status.CONFIRMATION_OPEN:
            next_status = Session.Status.TURN_TAKING_OPEN
        elif session.status == Session.Status.TURN_TAKING_OPEN:
            next_status = Session.Status.LIVE
        elif session.status == Session.Status.LIVE:
            next_status = Session.Status.ENDED

        if next_status:
            session.status = next_status
            session.save(update_fields=["status"])
            status_names = dict(Session.Status.choices)
            messages.success(request, f"تم تقديم الحصة إلى: {status_names.get(next_status, next_status)}")
        else:
            messages.error(request, "لا يمكن تقديم الحصة من حالتها الحالية")

    return redirect("accounts:teacher_session_detail", pk=pk)
@login_required
@role_required(User.Role.TEACHER)
def teacher_session_toggle_turns(request, pk):
    session = get_object_or_404(
        Session.objects.select_related("circle"),
        pk=pk, circle__teacher=request.user,
    )
    if request.method == "POST":
        if session.status in (Session.Status.DRAFT, Session.Status.ENDED):
            messages.error(request, "لا يمكن تغيير حالة الأدوار في هذه المرحلة")
            return redirect("accounts:teacher_session_detail", pk=pk)
        session.turns_closed = not session.turns_closed
        session.save(update_fields=["turns_closed"])

        if session.turns_closed:
            students = User.objects.filter(
                enrollments__circle=session.circle,
                enrollments__status=CircleEnrollment.Status.ACTIVE,
                role=User.Role.STUDENT,
            )
            for student in students:
                Notification.objects.create(
                    recipient=student,
                    type=Notification.Type.SESSION_STARTING,
                    title=f"حصة {session.circle.name} على وشك البدء",
                    message=f"تم فتح باب التسجيل في أدوار التسميع لحصة {session.circle.name}. سجل دورك الآن!",
                    link=f"/dashboard/student/sessions/{session.pk}/",
                )

        status_text = "أغلقت" if session.turns_closed else "فتحت"
        messages.success(request, f"تم {status_text} أدوار التسميع")
    return redirect("accounts:teacher_session_detail", pk=pk)
@login_required
@role_required(User.Role.TEACHER)
def teacher_session_edit(request, pk):
    session = get_object_or_404(
        Session.objects.select_related("circle"),
        pk=pk, circle__teacher=request.user,
    )
    if request.method == 'POST':
        from datetime import datetime
        old_date = session.session_date
        old_time = session.session_time
        session_date_str = request.POST.get('session_date', '')
        if session_date_str:
            try:
                session.session_date = datetime.strptime(session_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        session_time_str = request.POST.get('session_time', '').strip()
        if session_time_str:
            try:
                session.session_time = datetime.strptime(session_time_str, '%H:%M').time()
            except ValueError:
                pass
        session.session_type = request.POST.get("session_type", session.session_type)
        session.location = request.POST.get("location", session.location)
        session.meeting_source = request.POST.get("meeting_source", session.meeting_source)
        session.meeting_url = request.POST.get("meeting_url", session.meeting_url)
        session.meeting_platform = request.POST.get("meeting_platform", session.meeting_platform)
        session.meeting_id = request.POST.get("meeting_id", session.meeting_id)
        session.meeting_password = request.POST.get("meeting_password", session.meeting_password)
        session.duration_minutes = request.POST.get("duration_minutes") or session.duration_minutes
        session.notes = request.POST.get("notes", session.notes)
        if (session.session_date, session.session_time) != (old_date, old_time):
            if session.session_date and session.session_time:
                from django.utils import timezone as tz
                session.start_time = tz.make_aware(
                    datetime.combine(session.session_date, session.session_time),
                    tz.get_current_timezone(),
                )
            else:
                session.start_time = None
        session.save()
        if (session.session_date, session.session_time) != (old_date, old_time):
            admins = User.objects.filter(role=User.Role.MAIN_ADMIN, is_active=True)
            for admin in admins:
                Notification.objects.create(
                    recipient=admin,
                    type=Notification.Type.RESCHEDULE_REQUEST,
                    title="تعديل موعد حصة من قبل معلم",
                    message=f"قام {request.user.full_name_ar} بتعديل موعد حصة {session.circle.name} من {old_date}" +
                            (f" {old_time.strftime('%H:%M')}" if old_time else "") +
                            f" إلى {session.session_date}" +
                            (f" {session.session_time.strftime('%H:%M')}" if session.session_time else ""),
                    link=f"/dashboard/teacher/sessions/manage/",
                )
        messages.success(request, "تم تحديث الحصة بنجاح")
        return redirect('accounts:teacher_circle_detail', pk=session.circle_id)
    return render(request, 'dashboard/teacher/session_create.html', {
        'circle': session.circle,
        'session': session,
        'today': date.today(),
        'circle_schedule_time': session.circle.schedule_time,
    })
@login_required
@role_required(User.Role.TEACHER)
def teacher_session_delete(request, pk):
    session = get_object_or_404(
        Session.objects.select_related("circle"),
        pk=pk, circle__teacher=request.user,
    )
    if request.method == "POST":
        circle_id = session.circle_id
        session.delete()
        messages.success(request, "تم حذف الحصة بنجاح")
        return redirect('accounts:teacher_circle_detail', pk=circle_id)
    return redirect('accounts:teacher_circle_detail', pk=session.circle_id)
@login_required
@role_required(User.Role.TEACHER)
def teacher_absence_justifications(request):
    from apps.attendance.models import Attendance
    justifications = Attendance.objects.filter(
        session__circle__teacher=request.user,
        justification__gt="",
    ).select_related("student", "session__circle", "reviewed_by").order_by("-updated_at")
    justification_filter = request.GET.get("justification_status", "")
    if justification_filter:
        justifications = justifications.filter(justification_status=justification_filter)
    paginator = Paginator(justifications, 20)
    page_obj = paginator.get_page(request.GET.get("page", 1))
    return render(request, "dashboard/teacher/absence_justifications.html", {
        "justifications": page_obj,
        "page_obj": page_obj,
    })
@login_required
@role_required(User.Role.TEACHER)
def teacher_exams(request):
    my_circles = Circle.objects.filter(teacher=request.user, status=Circle.Status.ACTIVE)
    assigned = Exam.objects.filter(assigned_teacher=request.user)
    circle_exams = Exam.objects.filter(circle__in=my_circles)
    exams = (assigned | circle_exams).filter(
        status__in=[Exam.Status.PUBLISHED, Exam.Status.GRADING]
    ).select_related("circle", "assigned_teacher").distinct().order_by("-exam_date")
    return render(request, "dashboard/exams/teacher_list.html", {
        "exams": exams, "my_circles": my_circles,
    })
@login_required
@role_required(User.Role.TEACHER)
def teacher_exam_grade(request, pk):
    exam = get_object_or_404(Exam.objects.select_related("circle", "assigned_teacher"), pk=pk)
    ok, err = verify_teacher_assignment(exam, request.user)
    if not ok:
        raise PermissionDenied(err)
    ok, err = verify_exam_status(exam, [Exam.Status.PUBLISHED, Exam.Status.GRADING])
    if not ok:
        raise PermissionDenied(err)
    if exam.circle:
        students = User.objects.filter(
            enrollments__circle=exam.circle,
            enrollments__status=CircleEnrollment.Status.ACTIVE,
            role=User.Role.STUDENT,
        ).distinct()
    else:
        students = User.objects.filter(
            role=User.Role.STUDENT, is_approved=User.ApprovalStatus.APPROVED
        )
    existing = {m.student_id: m for m in exam.marks.select_related("student").all()}
    if request.method == "POST":
        with transaction.atomic():
            for student in students:
                marks_obtained = request.POST.get(f"mark_{student.id}")
                if marks_obtained:
                    ok_val, err_val = validate_mark_value(float(marks_obtained), exam.max_marks)
                    if ok_val:
                        save_mark(
                            exam=exam, student=student,
                            marks_obtained=float(marks_obtained),
                            entered_by=request.user,
                            teacher_notes=request.POST.get(f"notes_{student.id}", ""),
                            private_notes=request.POST.get(f"private_{student.id}", ""),
                        )
            exam.status = Exam.Status.GRADING
            exam.save(update_fields=["status"])
        messages.success(request, "تم تسجيل الدرجات. يمكنك تقديمها للاعتماد الآن.")
        return redirect("accounts:teacher_exam_submit", pk=exam.pk)
    return render(request, "dashboard/exams/teacher_grade.html", {
        "exam": exam, "students": students, "existing": existing,
    })
@login_required
@role_required(User.Role.TEACHER)
def teacher_exam_submit(request, pk):
    exam = get_object_or_404(Exam, pk=pk)
    ok, err = verify_teacher_assignment(exam, request.user)
    if not ok:
        raise PermissionDenied
    success, error = submit_for_approval(exam, request.user)
    if success:
        messages.success(request, "تم تقديم النتائج للاعتماد")
    else:
        messages.error(request, error)
    return redirect("accounts:teacher_exams")
@login_required
@role_required(User.Role.TEACHER)
def teacher_exam_export_pdf(request, pk):
    exam = get_object_or_404(Exam, pk=pk)
    ok, err = verify_teacher_assignment(exam, request.user)
    if not ok:
        raise PermissionDenied
    export_data = get_export_data(exam)
    pdf_bytes = generate_exam_pdf(export_data)
    from django.http import HttpResponse
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="exam_{exam.exam_code}.pdf"'
    return response


@login_required
@role_required(User.Role.TEACHER)
def teacher_student_tasks(request, student_id):
    student = get_object_or_404(User, pk=student_id, role=User.Role.STUDENT)
    circles = Circle.objects.filter(teacher=request.user, status=Circle.Status.ACTIVE)
    if not CircleEnrollment.objects.filter(
        student=student, circle__in=circles, status=CircleEnrollment.Status.ACTIVE
    ).exists():
        raise PermissionDenied
    tasks = StudyTask.objects.filter(student=student).select_related("surah", "assigned_by", "circle", "session")
    status_filter = request.GET.get("status")
    if status_filter in ("pending", "done", "validated", "rejected"):
        tasks = tasks.filter(status=status_filter)
    return render(request, "dashboard/teacher/student_tasks.html", {
        "student": student,
        "tasks": tasks,
        "current_filter": status_filter,
        "counts": {
            "all": StudyTask.objects.filter(student=student).count(),
            "pending": StudyTask.objects.filter(student=student, status=StudyTask.Status.PENDING).count(),
            "done": StudyTask.objects.filter(student=student, status=StudyTask.Status.DONE).count(),
            "validated": StudyTask.objects.filter(student=student, status=StudyTask.Status.VALIDATED).count(),
            "rejected": StudyTask.objects.filter(student=student, status=StudyTask.Status.REJECTED).count(),
        },
    })


def _parse_task_due_date(raw):
    """Parse an optional YYYY-MM-DD due date; invalid input becomes None."""
    from datetime import datetime
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def _own_session_or_none(teacher, session_id):
    """Resolve a session id to one of the teacher's own sessions, else None."""
    if not session_id:
        return None
    return Session.objects.filter(pk=session_id, circle__teacher=teacher).first()


def _task_form_sessions(student_circles):
    """Recent sessions of the student's circles, for the 'linked session' select."""
    return Session.objects.filter(circle__in=student_circles).select_related(
        "circle"
    ).order_by("-session_date")[:30]


@login_required
@role_required(User.Role.TEACHER)
def teacher_task_assign(request, student_id):
    from apps.references.models import Surah
    student = get_object_or_404(User, pk=student_id, role=User.Role.STUDENT)
    circles = Circle.objects.filter(teacher=request.user, status=Circle.Status.ACTIVE)
    if not CircleEnrollment.objects.filter(
        student=student, circle__in=circles, status=CircleEnrollment.Status.ACTIVE
    ).exists():
        raise PermissionDenied
    student_circles = circles.filter(
        enrollments__student=student, enrollments__status=CircleEnrollment.Status.ACTIVE,
    )
    if request.method == "POST":
        task_type = request.POST.get("task_type")
        surah_id = request.POST.get("surah")
        ayah_from = request.POST.get("ayah_from")
        ayah_to = request.POST.get("ayah_to")
        circle_id = request.POST.get("circle")
        notes = request.POST.get("notes", "")
        due_date = _parse_task_due_date(request.POST.get("due_date", ""))
        session = _own_session_or_none(request.user, request.POST.get("session"))
        if task_type and surah_id and ayah_from and ayah_to:
            try:
                StudyTask.assign(
                    student=student, assigned_by=request.user,
                    task_type=task_type, surah=surah_id,
                    ayah_from=ayah_from, ayah_to=ayah_to,
                    circle=Circle.objects.filter(pk=circle_id).first() if circle_id else None,
                    notes=notes, due_date=due_date, session=session,
                )
                messages.success(request, f"تم إسناد المهمة للطالب {student.full_name_ar}")
                return redirect("accounts:teacher_student_tasks", student_id=student.id)
            except ValidationError as e:
                messages.error(request, "؛ ".join(e.messages) if hasattr(e, "messages") else str(e))
        else:
            messages.error(request, "يرجى ملء جميع الحقول المطلوبة")
    surahs = Surah.objects.all().order_by("id")
    return render(request, "dashboard/teacher/task_form.html", {
        "student": student,
        "surahs": surahs,
        "student_circles": student_circles,
        "sessions": _task_form_sessions(student_circles),
        "form_title": "إسناد مهمة",
        "form_action": "assign",
    })


@login_required
@role_required(User.Role.TEACHER)
def teacher_task_validate(request, pk):
    task = get_object_or_404(StudyTask, pk=pk)
    student = task.student
    circles = Circle.objects.filter(teacher=request.user, status=Circle.Status.ACTIVE)
    if not CircleEnrollment.objects.filter(
        student=student, circle__in=circles, status=CircleEnrollment.Status.ACTIVE
    ).exists():
        raise PermissionDenied
    if task.status != StudyTask.Status.DONE:
        messages.error(request, "هذه المهمة ليست بانتظار التحقق")
        return redirect("accounts:teacher_student_tasks", student_id=student.id)
    if request.method == "POST":
        action = request.POST.get("action")
        rejection_reason = request.POST.get("rejection_reason", "")
        try:
            if action == "validate":
                task.validate(by=request.user)
                messages.success(request, "تم اعتماد المهمة")
            elif action == "reject":
                task.validate(by=request.user, rejection_reason=rejection_reason)
                messages.success(request, "تم رفض المهمة")
        except ValidationError as e:
            messages.error(request, "؛ ".join(e.messages) if hasattr(e, "messages") else str(e))
        return redirect("accounts:teacher_student_tasks", student_id=student.id)
    return render(request, "dashboard/teacher/task_validate.html", {"task": task})


@login_required
@role_required(User.Role.TEACHER)
def teacher_task_edit(request, pk):
    from apps.references.models import Surah
    task = get_object_or_404(StudyTask, pk=pk)
    student = task.student
    circles = Circle.objects.filter(teacher=request.user, status=Circle.Status.ACTIVE)
    if not CircleEnrollment.objects.filter(
        student=student, circle__in=circles, status=CircleEnrollment.Status.ACTIVE
    ).exists():
        raise PermissionDenied
    student_circles = circles.filter(
        enrollments__student=student, enrollments__status=CircleEnrollment.Status.ACTIVE,
    )
    if request.method == "POST":
        task_type = request.POST.get("task_type")
        surah_id = request.POST.get("surah")
        ayah_from = request.POST.get("ayah_from")
        ayah_to = request.POST.get("ayah_to")
        circle_id = request.POST.get("circle")
        notes = request.POST.get("notes", "")
        due_date = _parse_task_due_date(request.POST.get("due_date", ""))
        session = _own_session_or_none(request.user, request.POST.get("session"))
        if task_type and surah_id and ayah_from and ayah_to:
            try:
                task.update_details(
                    by=request.user, task_type=task_type, surah=surah_id,
                    ayah_from=ayah_from, ayah_to=ayah_to,
                    circle=Circle.objects.filter(pk=circle_id).first() if circle_id else None,
                    notes=notes, due_date=due_date, session=session,
                )
                messages.success(request, "تم تحديث المهمة بنجاح")
                return redirect("accounts:teacher_student_tasks", student_id=student.id)
            except ValidationError as e:
                messages.error(request, "؛ ".join(e.messages) if hasattr(e, "messages") else str(e))
        else:
            messages.error(request, "يرجى ملء جميع الحقول المطلوبة")
    surahs = Surah.objects.all().order_by("id")
    return render(request, "dashboard/teacher/task_form.html", {
        "student": student,
        "task": task,
        "surahs": surahs,
        "student_circles": student_circles,
        "sessions": _task_form_sessions(student_circles),
        "form_title": "تعديل المهمة",
        "form_action": "edit",
    })


@login_required
@role_required(User.Role.TEACHER)
def teacher_task_delete(request, pk):
    task = get_object_or_404(StudyTask, pk=pk)
    student = task.student
    circles = Circle.objects.filter(teacher=request.user, status=Circle.Status.ACTIVE)
    if not CircleEnrollment.objects.filter(
        student=student, circle__in=circles, status=CircleEnrollment.Status.ACTIVE
    ).exists():
        raise PermissionDenied
    if request.method == "POST":
        task.delete()
        messages.success(request, "تم حذف المهمة بنجاح")
    return redirect("accounts:teacher_student_tasks", student_id=student.id)


@login_required
@role_required(User.Role.TEACHER)
def teacher_webinars(request):
    """The teacher's "ندواتي كمتحدّث" surface: webinars where they are the
    host or a designated co-speaker, with a link into the speaker room.
    Webinar creation stays admin-only — this is read/enter only."""
    from apps.webinars.models import Webinar
    webinars = Webinar.objects.filter(
        Q(created_by=request.user) | Q(co_speakers=request.user),
    ).distinct().order_by("scheduled_at")
    return render(request, "dashboard/teacher/webinars.html", {
        "webinars": webinars,
    })
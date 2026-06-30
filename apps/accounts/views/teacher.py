import json

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from apps.accounts.decorators import role_required
from django.http import JsonResponse
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q
from django.core.paginator import Paginator
from datetime import date, timedelta

from apps.accounts.models import User, TeacherAbsence
from apps.circles.models import Circle, CircleEnrollment, Session, SessionRescheduleRequest
from apps.attendance.models import Attendance
from apps.requests.models import SupportRequest
from apps.announcements.models import Announcement
from apps.notifications.models import Notification
from apps.memorization.models import MemorizationProgress, RecitationGrade, StudentAchievement, ReviewRequest
from apps.exams.models import Exam
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

    recent_sessions = Session.objects.filter(
        circle__teacher=request.user,
    ).select_related('circle').annotate(
        att_total=Count('attendance_records'),
        att_present=Count('attendance_records', filter=Q(
            attendance_records__status__in=['present', 'late', 'left_early']
        )),
    ).order_by('-session_date', '-created_at')[:20]

    return render(request, 'dashboard/teacher/home.html', {
        'circles': circles,
        'today_sessions': today_sessions,
        'recent_sessions': recent_sessions,
    })
@login_required
@role_required(User.Role.ADMIN, User.Role.SUPERVISOR, User.Role.TEACHER)
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

        session, created = Session.objects.get_or_create(
            circle=circle,
            session_date=session_date,
            defaults={
                "session_time": session_time,
                "session_type": request.POST.get("session_type", Session.Type.IN_PERSON),
                "location": location,
                "meeting_url": request.POST.get("meeting_url", ""),
                "meeting_platform": request.POST.get("meeting_platform", ""),
                "meeting_id": request.POST.get("meeting_id", ""),
                "meeting_password": request.POST.get("meeting_password", ""),
                "duration_minutes": request.POST.get("duration_minutes") or None,
                "notes": request.POST.get("notes", ""),
            },
        )
        if not created:
            if session_time_str:
                session.session_time = session_time
            session.session_type = request.POST.get("session_type", session.session_type)
            session.location = location or session.location
            session.meeting_url = request.POST.get("meeting_url", session.meeting_url)
            session.meeting_platform = request.POST.get("meeting_platform", session.meeting_platform)
            session.meeting_id = request.POST.get("meeting_id", session.meeting_id)
            session.meeting_password = request.POST.get("meeting_password", session.meeting_password)
            session.duration_minutes = request.POST.get("duration_minutes") or session.duration_minutes
            session.notes = request.POST.get("notes", session.notes)
            session.save()
            messages.success(request, "تم تحديث الحصة")
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
def teacher_toggle_lesson(request, pk):
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "طلب غير صالح"}, status=400)
    progress = get_object_or_404(
        MemorizationProgress.objects.select_related("enrollment__circle"),
        pk=pk,
        enrollment__circle__teacher=request.user,
    )
    new_status = request.POST.get("status", "")
    if new_status in dict(MemorizationProgress.Status.choices):
        progress.status = new_status
        progress.save(update_fields=["status", "updated_at"])
        return JsonResponse({"success": True, "status": progress.status, "label": progress.get_status_display()})
    return JsonResponse({"success": False, "error": "حالة غير صالحة"}, status=400)
@login_required
@role_required(User.Role.TEACHER)
def teacher_absence_create(request):
    if request.method == "POST":
        start_date_str = request.POST.get("start_date", "")
        end_date_str = request.POST.get("end_date", "")
        reason = request.POST.get("reason", "")
        if start_date_str and end_date_str and reason:
            TeacherAbsence.objects.create(
                teacher=request.user,
                start_date=start_date_str,
                end_date=end_date_str,
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
            attendance_records__status__in=["present", "late", "left_early"]
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
    progress = MemorizationProgress.objects.filter(
        enrollment__student=student,
        enrollment__circle__in=circles,
    ).select_related("surah", "enrollment__circle").order_by("-created_at")
    stats = progress.aggregate(
        total=Count("id"),
        hifz=Count("id", filter=Q(type=MemorizationProgress.Type.HIFZ)),
        murajaa=Count("id", filter=Q(type=MemorizationProgress.Type.MURAJAA)),
        mastered=Count("id", filter=Q(status=MemorizationProgress.Status.MASTERED)),
    )
    achievement, _ = StudentAchievement.objects.get_or_create(student=student)
    return render(request, "dashboard/teacher/student_progress.html", {
        "student": student,
        "progress": progress,
        "stats": stats,
        "achievement": achievement,
    })
@login_required
@role_required(User.Role.TEACHER, User.Role.ADMIN, User.Role.SUPERVISOR)
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
@role_required(User.Role.TEACHER, User.Role.ADMIN, User.Role.SUPERVISOR)
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
@role_required(User.Role.TEACHER, User.Role.ADMIN, User.Role.SUPERVISOR)
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
def teacher_review_requests(request):
    review_requests = ReviewRequest.objects.filter(
        circle__teacher=request.user,
    ).select_related("student", "circle", "surah").order_by("-created_at")
    status_filter = request.GET.get("status", "")
    if status_filter:
        review_requests = review_requests.filter(status=status_filter)
    paginator = Paginator(review_requests, 20)
    page_obj = paginator.get_page(request.GET.get("page", 1))
    return render(request, "dashboard/teacher/review_requests.html", {
        "requests": page_obj,
        "page_obj": page_obj,
    })
@login_required
@role_required(User.Role.TEACHER)
def teacher_reschedule_requests(request):
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

    student_attendance = []
    for student in students:
        att = attendance_records.get(str(student.id))
        student_attendance.append({
            "student": student,
            "attendance": att,
        })

    present_count = sum(1 for a in attendance_records.values() if a.status in ["present", "late", "left_early"])
    absent_count = sum(1 for a in attendance_records.values() if a.status == "absent")
    excused_count = sum(1 for a in attendance_records.values() if a.status == "excused")

    return render(request, "dashboard/teacher/session_detail.html", {
        "session": session,
        "turns": turns,
        "students_without_turns": students_without_turns,
        "student_attendance": student_attendance,
        "present_count": present_count,
        "absent_count": absent_count,
        "excused_count": excused_count,
        "total_students": len(students),
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
    data = json.loads(request.body)
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
        turn_map = {str(t.student_id): t for t in turns}
        for i, student_id in enumerate(order, start=1):
            turn_map[student_id].turn_number = -i
        SessionTurn.objects.bulk_update(turn_map.values(), ["turn_number"])
        for t in turn_map.values():
            t.turn_number = -t.turn_number
        SessionTurn.objects.bulk_update(turn_map.values(), ["turn_number"])

    return JsonResponse({"success": True})
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
        session.meeting_url = request.POST.get("meeting_url", session.meeting_url)
        session.meeting_platform = request.POST.get("meeting_platform", session.meeting_platform)
        session.meeting_id = request.POST.get("meeting_id", session.meeting_id)
        session.meeting_password = request.POST.get("meeting_password", session.meeting_password)
        session.duration_minutes = request.POST.get("duration_minutes") or session.duration_minutes
        session.notes = request.POST.get("notes", session.notes)
        session.save()
        if (session.session_date, session.session_time) != (old_date, old_time):
            admins = User.objects.filter(role=User.Role.ADMIN, is_active=True)
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
    ).filter(
        Q(justification__gt="") | Q(status=Attendance.Status.PENDING_JUSTIFICATION)
    ).select_related("student", "session__circle", "reviewed_by").order_by("-updated_at")
    status_filter = request.GET.get("status", "")
    if status_filter:
        justifications = justifications.filter(status=status_filter)
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
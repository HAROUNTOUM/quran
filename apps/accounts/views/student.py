from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from apps.accounts.decorators import role_required
from django.http import JsonResponse
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q, F, Sum, IntegerField, Case, When, Prefetch
from django.core.paginator import Paginator
from datetime import date, timedelta
from django.utils import timezone
from apps.notifications.models import Notification

from apps.accounts.models import User
from apps.circles.models import Circle, CircleEnrollment, Session, SessionRescheduleRequest
from apps.attendance.models import Attendance, SessionAttendanceIntent
from apps.requests.models import SupportRequest
from apps.announcements.models import Announcement
from apps.notifications.models import Notification
from apps.memorization.models import MemorizationProgress, ReviewRequest, RecitationGrade, StudyTask
from apps.certificates.models import Certificate
from apps.references.models import Surah
from apps.references.utils import count_thumns, format_hizb_thumn

@login_required
@role_required(User.Role.STUDENT)
def student_dashboard(request):

    enrollments = CircleEnrollment.objects.filter(
        student=request.user, status=CircleEnrollment.Status.ACTIVE
    ).select_related('circle', 'circle__teacher', 'current_surah')
    circle_ids = [en.circle_id for en in enrollments]

    recent_attendance = Attendance.objects.filter(
        student=request.user
    ).select_related('session__circle').order_by('-session__session_date')[:5]

    att_counts = Attendance.objects.filter(student=request.user).aggregate(
        present=Sum(Case(When(status=Attendance.Status.PRESENT, then=1), default=0, output_field=IntegerField())),
        absent=Sum(Case(When(status__in=[Attendance.Status.ABSENT_UNJUSTIFIED, Attendance.Status.ABSENT], then=1), default=0, output_field=IntegerField())),
        total=Count('id'),
    )
    present_count = att_counts['present'] or 0
    total_attendance = att_counts['total'] or 0
    attendance_rate = round(present_count / total_attendance * 100, 1) if total_attendance else 0
    absent_count = att_counts['absent'] or 0

    absence_breakdown = Attendance.objects.filter(
        student=request.user, status__in=[Attendance.Status.ABSENT_UNJUSTIFIED, Attendance.Status.ABSENT],
    ).aggregate(
        justified=Count('id', filter=Q(justification_status=Attendance.JustificationStatus.ACCEPTED)),
        pending=Count('id', filter=Q(justification_status=Attendance.JustificationStatus.PENDING)),
        unjustified=Count('id', filter=Q(justification_status__in=[
            Attendance.JustificationStatus.REFUSED, Attendance.JustificationStatus.NONE,
        ])),
    )

    from apps.memorization.models import ProgressLog
    memo_counts = ProgressLog.objects.filter(
        student=request.user
    ).values('log_category').annotate(cnt=Count('id'))
    hifz_count = next((m['cnt'] for m in memo_counts if m['log_category'] == ProgressLog.Category.HIFDH), 0)
    murajaa_count = next((m['cnt'] for m in memo_counts if m['log_category'] == ProgressLog.Category.MURAJAAH), 0)

    recent_announcements = Announcement.objects.all().order_by('-created_at')[:5]

    upcoming_sessions = Session.objects.filter(
        circle_id__in=circle_ids,
        turns_closed=False,
        session_date__gte=timezone.localdate(),
    ).exclude(status=Session.Status.ENDED).select_related('circle').order_by('session_date', 'session_time')[:5]

    unlocked_sessions = Session.objects.filter(
        circle_id__in=circle_ids,
        turns_closed=False,
        session_date__gte=timezone.localdate(),
    ).select_related('circle')

    pending_review_count = ReviewRequest.objects.filter(
        student=request.user, status=ReviewRequest.Status.PENDING
    ).count()

    # Unread notifications come from the global context processor
    # (core.context_processors.unread_notifications → `unread_count`),
    # so no duplicate query here (H07).
    recent_certificates = Certificate.objects.filter(
        student=request.user, status="issued",
    ).select_related("template").order_by("-issue_date")[:3]

    student_alerts = []
    now = timezone.now()
    thirty_days_ago = now - timedelta(days=30)
    repeated_absences = Attendance.objects.filter(
        student=request.user,
        status=Attendance.Status.ABSENT_UNJUSTIFIED,
        session__session_date__gte=thirty_days_ago.date(),
    ).count()
    if repeated_absences >= 3:
        student_alerts.append({
            "type": "absence",
            "title": "غيابات متكررة",
            "body": f"لديك {repeated_absences} غيابات غير مبررة هذا الشهر",
            "link": "/dashboard/student/attendance/",
        })
    pending_justifications = absence_breakdown.get("pending", 0)
    if pending_justifications:
        student_alerts.append({
            "type": "pending_justification",
            "title": "تبريرات قيد المراجعة",
            "body": f"لديك {pending_justifications} تبريراً بانتظار مراجعة المعلم",
            "link": "/dashboard/student/justifications/",
        })
    paused_circles = [
        en.circle.name for en in enrollments
        if en.circle.status == Circle.Status.PAUSED
    ]
    if paused_circles:
        student_alerts.append({
            "type": "paused_circle",
            "title": "حلقة متوقفة",
            "body": f"الحلقة {paused_circles[0]} متوقفة حالياً. يرجى متابعة المعلم",
            "link": f"/dashboard/student/circles/",
        })

    from apps.classrooms.models import TeacherRoom
    teacher_rooms = TeacherRoom.objects.filter(
        teacher__in=request.user.get_assigned_teachers(),
        is_active=True, teacher__is_active=True,
    ).select_related("teacher")

    from apps.memorization.models import MemorizationRecord
    memorized_rubs_total = MemorizationRecord.objects.memorized(request.user).count()
    from apps.memorization.models import StudyTask
    pending_tasks_count = StudyTask.objects.filter(
        student=request.user, status=StudyTask.Status.PENDING
    ).count()

    return render(request, 'dashboard/student/home.html', {
        'memorized_rubs_total': memorized_rubs_total,
        'pending_tasks_count': pending_tasks_count,
        'circles': [en.circle for en in enrollments],
        'enrollments': enrollments,
        'recent_attendance': recent_attendance,
        'attendance_rate': attendance_rate,
        'present_count': present_count,
        'total_attendance': total_attendance,
        'absent_count': absent_count,
        'absence_breakdown': absence_breakdown,
        'hifz_count': hifz_count,
        'murajaa_count': murajaa_count,
        'recent_announcements': recent_announcements,
        'upcoming_sessions': upcoming_sessions,
        'unlocked_sessions': unlocked_sessions,
        'pending_review_count': pending_review_count,
        'recent_certificates': recent_certificates,
        'student_alerts': student_alerts,
        'teacher_rooms': teacher_rooms,
    })
@login_required
@role_required(User.Role.STUDENT)
def student_circles(request):

    enrolled_ids = CircleEnrollment.objects.filter(
        student=request.user, status=CircleEnrollment.Status.ACTIVE
    ).values_list('circle_id', flat=True)

    pending_ids = CircleEnrollment.objects.filter(
        student=request.user, status=CircleEnrollment.Status.PENDING
    ).values_list('circle_id', flat=True)

    unavailable_ids = list(enrolled_ids) + list(pending_ids)

    available_circles = Circle.objects.filter(
        status=Circle.Status.ACTIVE
    ).exclude(
        id__in=unavailable_ids
    ).select_related('teacher').annotate(
        enrolled_count=Count('enrollments', filter=Q(enrollments__status=CircleEnrollment.Status.ACTIVE))
    )

    my_enrollments = CircleEnrollment.objects.filter(
        student=request.user, status=CircleEnrollment.Status.ACTIVE
    ).select_related('circle', 'circle__teacher', 'current_surah')

    pending_enrollments = CircleEnrollment.objects.filter(
        student=request.user, status=CircleEnrollment.Status.PENDING
    ).select_related('circle', 'circle__teacher')

    return render(request, 'dashboard/student/circles.html', {
        'available_circles': available_circles,
        'my_enrollments': my_enrollments,
        'pending_enrollments': pending_enrollments,
    })
@login_required
@role_required(User.Role.STUDENT)
def student_enroll_circle(request, pk):

    if request.method == 'POST':
        circle = get_object_or_404(Circle, pk=pk, status=Circle.Status.ACTIVE)

        enrollment = CircleEnrollment.objects.filter(
            student=request.user, circle=circle
        ).first()

        if enrollment:
            if enrollment.status in [CircleEnrollment.Status.ACTIVE, CircleEnrollment.Status.PENDING]:
                messages.info(request, 'أنت مسجل بالفعل أو لديك طلب انتظار لهذه الحلقة')
                return redirect('accounts:student_circles')
            enrollment.status = CircleEnrollment.Status.PENDING
            enrollment.left_at = None
            enrollment.save()
        else:
            enrollment = CircleEnrollment.objects.create(
                circle=circle,
                student=request.user,
                status=CircleEnrollment.Status.PENDING,
            )

        from django.urls import reverse

        for admin in User.objects.filter(role=User.Role.MAIN_ADMIN, is_active=True):
            Notification.objects.create(
                recipient=admin,
                type=Notification.Type.SYSTEM,
                title=f"طلب تسجيل جديد في حلقة {circle.name}",
                message=f"الطالب {request.user.full_name_ar} يطلب الانضمام إلى حلقة {circle.name}",
                link=reverse("accounts:admin_circle_detail", args=[circle.pk]),
            )

        messages.success(request, 'تم إرسال طلب التسجيل. سيتم مراجعته من قبل الإدارة.')
        return redirect('accounts:student_circles')

    return redirect('accounts:student_circles')
def _memorization_plan_data(user):
    """Per-circle hifz/murajaa breakdown built exclusively from what the
    teacher recorded in sessions (ProgressLog) — no status-derived stats.
    Shared by the standalone plan page and the merged الإحصائيات workspace
    tab. Returns (progress_data, json)."""
    from apps.memorization.models import ProgressLog

    enrollments = CircleEnrollment.objects.filter(
        student=user, status=CircleEnrollment.Status.ACTIVE
    ).select_related('circle', 'current_surah')

    logs = list(
        ProgressLog.objects.filter(student=user)
        .select_related('surah', 'session')
        .order_by('-created_at')
    )

    progress_data = []
    for en in enrollments:
        circle_logs = [l for l in logs if l.session_id and l.session.circle_id == en.circle_id]
        hifz_records = [l for l in circle_logs if l.log_category == ProgressLog.Category.HIFDH]
        murajaa_records = [l for l in circle_logs if l.log_category == ProgressLog.Category.MURAJAAH]

        def thumns_of(records):
            ranges = [(r.surah_id, r.start_ayah, r.end_ayah) for r in records if r.surah_id]
            amounts = sum(r.total_thumns for r in records if not r.surah_id)
            return count_thumns(ranges) + amounts

        hifz_total = thumns_of(hifz_records)
        murajaa_total = thumns_of(murajaa_records)

        progress_data.append({
            'enrollment': en,
            'circle_name': en.circle.name,
            'current_surah': en.current_surah.name_ar if en.current_surah else '—',
            'hifz_records': hifz_records,
            'murajaa_records': murajaa_records,
            # All totals are thumn counts (the platform tracking unit).
            'hifz_total': hifz_total,
            'hifz_units': format_hizb_thumn(hifz_total),
            'murajaa_total': murajaa_total,
            'muj_units': format_hizb_thumn(murajaa_total),
        })

    import json
    progress_data_json = json.dumps([{
        'hifz_total': d['hifz_total'],
        'murajaa_total': d['murajaa_total'],
    } for d in progress_data])
    return progress_data, progress_data_json


@login_required
@role_required(User.Role.STUDENT)
def student_memorization(request):
    progress_data, progress_data_json = _memorization_plan_data(request.user)
    return render(request, 'dashboard/student/memorization.html', {
        'progress_data': progress_data,
        'progress_data_json': progress_data_json,
    })
@login_required
@role_required(User.Role.STUDENT)
def student_session_detail(request, pk):
    session = get_object_or_404(Session.objects.select_related("circle"), pk=pk)
    if not CircleEnrollment.objects.filter(
        student=request.user, circle=session.circle, status=CircleEnrollment.Status.ACTIVE
    ).exists():
        raise PermissionDenied

    attendance = Attendance.objects.filter(session=session, student=request.user).first()

    from apps.circles.models import SessionTurn
    user_turn = SessionTurn.objects.filter(session=session, student=request.user).first()
    turns = SessionTurn.objects.filter(session=session).select_related("student").order_by("turn_number")

    from apps.memorization.models import RecitationGrade
    grades = RecitationGrade.objects.filter(session=session, student=request.user).select_related("criterion")

    from apps.references.models import EvaluationCriterion
    all_criteria = EvaluationCriterion.objects.filter(is_active=True)

    from apps.memorization.engine import session_report_data
    report_rows, todo_rows = session_report_data(session, student=request.user)

    return render(request, "dashboard/student/session_detail.html", {
        "session": session,
        "attendance": attendance,
        "user_turn": user_turn,
        "turns": turns,
        "grades": grades,
        "all_criteria": all_criteria,
        "report_rows": report_rows,
        "todo_rows": todo_rows,
        "can_confirm": session.status not in (Session.Status.DRAFT, Session.Status.ENDED)
            and not session.turns_closed
            and session.session_date and session.session_date >= timezone.localdate()
            and (attendance is None or attendance.status in (
                Attendance.Status.NOT_RESPONDED, Attendance.Status.ABSENT_UNJUSTIFIED, Attendance.Status.ABSENT,
            )),
        "can_claim_turn": session.status not in (Session.Status.DRAFT, Session.Status.ENDED)
            and not session.turns_closed
            and session.session_date and session.session_date >= timezone.localdate()
            and attendance and attendance.status in (
                Attendance.Status.NOT_RESPONDED, Attendance.Status.CONFIRMED,
            ),
        "can_join_live": session.status == Session.Status.LIVE
            and attendance and attendance.status in (
                Attendance.Status.NOT_RESPONDED, Attendance.Status.CONFIRMED,
            ),
        "can_submit_justification": attendance and (
            attendance.status in (Attendance.Status.ABSENT_UNJUSTIFIED, Attendance.Status.ABSENT)
            or (session.status not in (Session.Status.DRAFT, Session.Status.ENDED)
                and not session.turns_closed and session.session_date
                and session.session_date >= timezone.localdate()
                and attendance.status == Attendance.Status.NOT_RESPONDED)
        ) and attendance.justification_status in (
            Attendance.JustificationStatus.NONE, Attendance.JustificationStatus.REFUSED,
        ),
        "session_is_live": session.status == Session.Status.LIVE,
        "session_is_ended": session.status == Session.Status.ENDED,
    })
@login_required
@role_required(User.Role.STUDENT)
def student_confirm_attendance(request, pk):
    session = get_object_or_404(Session.objects.select_related("circle"), pk=pk)
    if not CircleEnrollment.objects.filter(
        student=request.user, circle=session.circle, status=CircleEnrollment.Status.ACTIVE
    ).exists():
        raise PermissionDenied

    if session.status in (Session.Status.DRAFT, Session.Status.ENDED) or session.turns_closed:
        messages.error(request, "تأكيد الحضور غير متاح حالياً")
        return redirect("accounts:student_session_detail", pk=pk)

    att, created = Attendance.objects.get_or_create(
        session=session, student=request.user,
        defaults={"status": Attendance.Status.CONFIRMED},
    )
    if not created:
        if att.status == Attendance.Status.NOT_RESPONDED:
            att.status = Attendance.Status.CONFIRMED
            att.save(update_fields=["status"])
        elif att.status == Attendance.Status.CONFIRMED:
            messages.info(request, "لقد أكدت حضورك مسبقاً")
            return redirect("accounts:student_session_detail", pk=pk)
        else:
            messages.info(request, "تم تحديث حالتك مسبقاً")
            return redirect("accounts:student_session_detail", pk=pk)

    messages.success(request, "تم تأكيد حضورك")
    return redirect("accounts:student_session_detail", pk=pk)


@login_required
@role_required(User.Role.STUDENT)
def student_claim_turn(request, pk):
    from apps.circles.models import Session, CircleEnrollment, SessionTurn
    session = get_object_or_404(Session.objects.select_related("circle"), pk=pk)
    if not CircleEnrollment.objects.filter(
        student=request.user, circle=session.circle, status=CircleEnrollment.Status.ACTIVE
    ).exists():
        raise PermissionDenied
    if session.turns_closed or not (session.session_date and session.session_date >= timezone.localdate()):
        return JsonResponse({"success": False, "message": "التسجيل في الأدوار غير متاح حالياً"}, status=403)

    attendance = Attendance.objects.filter(session=session, student=request.user).first()
    if not attendance or attendance.status not in (Attendance.Status.NOT_RESPONDED, Attendance.Status.CONFIRMED):
        return JsonResponse({"success": False, "message": "يجب تأكيد الحضور أولاً"}, status=403)
    if attendance.status == Attendance.Status.NOT_RESPONDED:
        attendance.status = Attendance.Status.CONFIRMED
        attendance.save(update_fields=["status"])

    existing = SessionTurn.objects.filter(session=session, student=request.user).first()
    if existing:
        return JsonResponse({"success": False, "message": "لديك دور بالفعل"}, status=400)

    from django.db import IntegrityError, transaction
    try:
        with transaction.atomic():
            locked = SessionTurn.objects.select_for_update().filter(session=session)
            taken = set(locked.values_list("turn_number", flat=True))
            n = 1
            while n in taken:
                n += 1
            SessionTurn.objects.create(session=session, student=request.user, turn_number=n)
    except IntegrityError:
        return JsonResponse({"success": False, "message": "تم أخذ هذا الدور للتو، حاول مرة أخرى"}, status=409)

    return JsonResponse({"success": True, "turn_number": n})

@login_required
@role_required(User.Role.STUDENT)
def student_release_turn(request, pk):
    from apps.circles.models import Session, CircleEnrollment, SessionTurn
    session = get_object_or_404(Session.objects.select_related("circle"), pk=pk)
    if not CircleEnrollment.objects.filter(
        student=request.user, circle=session.circle, status=CircleEnrollment.Status.ACTIVE
    ).exists():
        raise PermissionDenied

    if session.status == Session.Status.DRAFT:
        return JsonResponse({"success": False, "message": "لا يمكن تحرير الدور حالياً"}, status=403)

    deleted, _ = SessionTurn.objects.filter(session=session, student=request.user).delete()
    if not deleted:
        return JsonResponse({"success": False, "message": "ليس لديك دور"}, status=400)

    return JsonResponse({"success": True})

@login_required
@role_required(User.Role.STUDENT)
def student_requests(request):
    qs = SupportRequest.objects.filter(submitted_by=request.user).select_related("submitted_by").order_by("-created_at")
    req_type = request.GET.get("type", "")
    if req_type:
        qs = qs.filter(type=req_type)
    req_status = request.GET.get("status", "")
    if req_status:
        qs = qs.filter(status=req_status)
    paginator = Paginator(qs, 15)
    page_obj = paginator.get_page(request.GET.get("page", 1))
    return render(request, "dashboard/student/requests.html", {
        "requests": page_obj,
        "page_obj": page_obj,
    })
# student_request_create removed — support/بلاغ tickets are now created through
# the single unified request form (student_review_request_create, type=support).
@login_required
@role_required(User.Role.STUDENT)
def student_announcements(request):
    qs = Announcement.objects.all().select_related("author").order_by("-created_at")
    search = request.GET.get("search", "")
    if search:
        qs = qs.filter(Q(title__icontains=search) | Q(body__icontains=search))
    paginator = Paginator(qs, 15)
    page_obj = paginator.get_page(request.GET.get("page", 1))
    return render(request, "dashboard/student/announcements.html", {
        "announcements": page_obj,
        "page_obj": page_obj,
    })
@login_required
@role_required(User.Role.STUDENT)
def student_notifications(request):
    qs = Notification.objects.filter(recipient=request.user).order_by("-created_at")
    notif_type = request.GET.get("type", "")
    if notif_type:
        qs = qs.filter(type=notif_type)
    is_read = request.GET.get("is_read", "")
    if is_read in ("true", "false"):
        qs = qs.filter(is_read=(is_read == "true"))
    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get("page", 1))
    return render(request, "dashboard/student/notifications.html", {
        "notifications": page_obj,
        "page_obj": page_obj,
    })
@login_required
@role_required(User.Role.STUDENT)
def student_attendance(request):
    qs = Attendance.objects.filter(student=request.user).select_related("session__circle", "session").order_by("-session__session_date")
    status_filter = request.GET.get("status", "")
    if status_filter:
        qs = qs.filter(status=status_filter)
    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get("page", 1))
    stats = request.user.attendance_stats()
    return render(request, "dashboard/student/attendance.html", {
        "attendance": page_obj,
        "page_obj": page_obj,
        "present_count": stats["present"],
        "total_count": stats["total"],
        "absent_count": stats["absent"],
        "excused_count": stats["excused"],
    })
@login_required
@role_required(User.Role.STUDENT)
def student_review_requests(request):
    qs = ReviewRequest.objects.filter(student=request.user).select_related("circle", "surah").order_by("-created_at")
    status_filter = request.GET.get("status", "")
    if status_filter:
        qs = qs.filter(status=status_filter)
    type_filter = request.GET.get("type", "")
    if type_filter == "question":
        qs = qs.filter(type=ReviewRequest.Type.QUESTION)
    elif type_filter in ("recitation", "review"):
        # the تسميع tab excludes plain questions
        qs = qs.exclude(type=ReviewRequest.Type.QUESTION)
    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get("page", 1))
    return render(request, "dashboard/student/review_requests.html", {
        "requests": page_obj,
        "page_obj": page_obj,
        "current_type": type_filter,
    })
@login_required
@role_required(User.Role.STUDENT)
def student_private_sessions(request):
    """The student's private (1-on-1) تسميع sessions — link, time, results."""
    from apps.memorization.models import PrivateSession
    sessions = PrivateSession.objects.filter(
        student=request.user,
    ).select_related("teacher", "circle").order_by("-scheduled_date", "-created_at")
    paginator = Paginator(sessions, 20)
    page_obj = paginator.get_page(request.GET.get("page", 1))
    return render(request, "dashboard/student/private_sessions.html", {
        "sessions": page_obj,
        "page_obj": page_obj,
    })
@login_required
@role_required(User.Role.STUDENT)
def student_review_request_create(request):
    enrollments = CircleEnrollment.objects.filter(
        student=request.user, status=CircleEnrollment.Status.ACTIVE
    ).select_related("circle")
    surahs = Surah.objects.all().order_by("id")
    if request.method == "POST":
        from django.core.exceptions import ValidationError
        req_type = request.POST.get("type", "recitation")
        try:
            if req_type == "support":
                # دعم / بلاغ — routed to the support-ticket system.
                request.user.submit_support_request(
                    title=request.POST.get("title", "").strip(),
                    body=request.POST.get("notes", "").strip(),
                    type=request.POST.get("support_type", "other"),
                    priority=request.POST.get("priority", "normal"),
                )
                messages.success(request, "تم إرسال البلاغ بنجاح")
                return redirect("accounts:student_requests")
            request.user.submit_review_request(
                circle=request.POST.get("circle"),
                type=req_type,
                surah=request.POST.get("surah"),
                ayah_from=request.POST.get("ayah_from"),
                ayah_to=request.POST.get("ayah_to"),
                notes=request.POST.get("notes", "").strip(),
                preferred_days=request.POST.getlist("preferred_days"),
                preferred_times=request.POST.getlist("preferred_times"),
            )
        except ValidationError as e:
            return render(request, "dashboard/student/review_request_create.html", {
                "error": " ".join(e.messages),
                "enrollments": enrollments,
                "surahs": surahs,
                "form_data": request.POST,
            })
        messages.success(request, "تم إرسال الطلب بنجاح")
        return redirect("accounts:student_review_requests")
    return render(request, "dashboard/student/review_request_create.html", {
        "enrollments": enrollments,
        "surahs": surahs,
        "day_choices": [
            ("sat", "السبت"), ("sun", "الأحد"), ("mon", "الإثنين"),
            ("tue", "الثلاثاء"), ("wed", "الأربعاء"), ("thu", "الخميس"), ("fri", "الجمعة"),
        ],
        "time_choices": [
            ("fajr", "الفجر"), ("dhuhr", "الظهر"), ("asr", "العصر"),
            ("maghrib", "المغرب"), ("isha", "العشاء"),
        ],
        "support_type_choices": [
            ("technical", "دعم فني"), ("administrative", "إداري"),
            ("academic", "أكاديمي"), ("other", "أخرى"),
        ],
        "priority_choices": [
            ("low", "منخفضة"), ("normal", "متوسطة"),
            ("high", "عالية"), ("urgent", "عاجلة"),
        ],
    })
@login_required
@role_required(User.Role.STUDENT)
def student_circle_detail(request, pk):
    enrollment = get_object_or_404(CircleEnrollment, circle_id=pk, student=request.user, status=CircleEnrollment.Status.ACTIVE)
    circle = enrollment.circle
    upcoming_sessions = Session.objects.filter(
        circle=circle,
        status__in=[Session.Status.SCHEDULED, Session.Status.CONFIRMATION_OPEN,
                     Session.Status.TURN_TAKING_OPEN, Session.Status.LIVE],
        turns_closed=False,
        session_date__gte=timezone.localdate(),
    ).order_by("session_date")[:10]
    past_sessions = Session.objects.filter(circle=circle, status=Session.Status.ENDED).order_by("-session_date")[:10]
    next_session = upcoming_sessions.first()
    from apps.memorization.models import RecitationGrade
    past_ids = [s.id for s in past_sessions]
    grade_qs = RecitationGrade.objects.filter(
        session_id__in=past_ids, student=request.user,
    ).values("session_id", "criterion__name_ar", "score", "max_score")
    grades_by_session = {}
    for g in grade_qs:
        sid = g["session_id"]
        if sid not in grades_by_session:
            grades_by_session[sid] = []
        grades_by_session[sid].append(g)
    return render(request, "dashboard/student/circle_detail.html", {
        "circle": circle,
        "enrollment": enrollment,
        "upcoming_sessions": upcoming_sessions,
        "past_sessions": past_sessions,
        "next_session": next_session,
        "grades_by_session": grades_by_session,
    })
@login_required
@role_required(User.Role.STUDENT)
def student_sessions(request):
    circle_ids = CircleEnrollment.objects.filter(
        student=request.user, status=CircleEnrollment.Status.ACTIVE
    ).values_list("circle_id", flat=True)
    upcoming = Session.objects.filter(
        circle_id__in=circle_ids,
        status__in=[Session.Status.SCHEDULED, Session.Status.CONFIRMATION_OPEN,
                     Session.Status.TURN_TAKING_OPEN, Session.Status.LIVE],
        turns_closed=False,
        session_date__gte=timezone.localdate(),
    ).select_related("circle").order_by("session_date", "session_time")
    past = Session.objects.filter(
        circle_id__in=circle_ids, status=Session.Status.ENDED,
    ).select_related("circle").order_by("-session_date", "-session_time")[:30]
    from apps.attendance.models import SessionAttendanceIntent
    intents = {
        i.session_id: i
        for i in SessionAttendanceIntent.objects.filter(
            session__in=upcoming, student=request.user,
        )
    }
    from apps.memorization.models import RecitationGrade
    past_ids = [s.id for s in past]
    grade_qs = RecitationGrade.objects.filter(
        session_id__in=past_ids, student=request.user,
    ).values("session_id", "criterion__name_ar", "score", "max_score")
    grades_by_session = {}
    for g in grade_qs:
        sid = g["session_id"]
        if sid not in grades_by_session:
            grades_by_session[sid] = []
        grades_by_session[sid].append(g)

    past_attendance = {
        a.session_id: a
        for a in Attendance.objects.filter(
            session_id__in=past_ids, student=request.user,
        )
    }
    return render(request, "dashboard/student/sessions.html", {
        "upcoming": upcoming,
        "past": past,
        "intents": intents,
        "grades_by_session": grades_by_session,
        "past_attendance": past_attendance,
    })
@login_required
@role_required(User.Role.STUDENT)
def student_exam_results(request):
    from apps.exams.services import get_student_marks
    from apps.certificates.models import Certificate
    results = get_student_marks(request.user)
    # Merged workspace: exam results + issued certificates on one page.
    certificates = Certificate.objects.filter(
        student=request.user, status="issued",
    ).select_related("template", "issued_by").order_by("-issue_date")
    return render(request, "dashboard/exams/student_results.html", {
        "results": results,
        "certificates": certificates,
    })
@login_required
@role_required(User.Role.STUDENT)
def student_achievements(request):
    achievement = getattr(request.user, "achievement", None)
    from apps.memorization.models import ProgressLog
    _logs = ProgressLog.objects.filter(student=request.user)
    hifz_thumns = _logs.filter(log_category=ProgressLog.Category.HIFDH).thumn_total()
    murajaa_thumns = _logs.filter(log_category=ProgressLog.Category.MURAJAAH).thumn_total()
    recent_progress = _logs.select_related('surah').order_by('-created_at')[:10]
    return render(request, "dashboard/student/achievements.html", {
        "achievement": achievement,
        "hifz_thumns": hifz_thumns,
        "murajaa_thumns": murajaa_thumns,
        "hifz_units": format_hizb_thumn(hifz_thumns),
        "murajaa_units": format_hizb_thumn(murajaa_thumns),
        "recent_progress": recent_progress,
    })
@login_required
@role_required(User.Role.STUDENT)
def student_request_detail(request, pk):
    req = get_object_or_404(SupportRequest, pk=pk, submitted_by=request.user)
    comments = req.comments.select_related("author").order_by("created_at")
    return render(request, "dashboard/student/request_detail.html", {
        "request": req,
        "comments": comments,
    })
@login_required
@role_required(User.Role.STUDENT)
def student_unenroll(request, pk):
    enrollment = get_object_or_404(
        CircleEnrollment, circle_id=pk, student=request.user, status=CircleEnrollment.Status.ACTIVE
    )
    if request.method == "POST":
        enrollment.status = CircleEnrollment.Status.DROPPED
        enrollment.left_at = timezone.now()
        enrollment.save()
        messages.success(request, "تم الانسحاب من الحلقة بنجاح")
        return redirect("accounts:student_circles")
    return redirect("accounts:student_circle_detail", pk=pk)
@login_required
@role_required(User.Role.STUDENT)
def student_justifications(request):
    qs = Attendance.objects.filter(
        student=request.user,
    ).exclude(
        justification_status=Attendance.JustificationStatus.NONE,
    ).select_related("session__circle", "reviewed_by").order_by("-updated_at")
    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get("page", 1))
    return render(request, "dashboard/student/justifications.html", {
        "justifications": page_obj,
        "page_obj": page_obj,
    })
@login_required
@role_required(User.Role.STUDENT)
def student_request_reschedule(request, pk):
    session = get_object_or_404(Session.objects.select_related("circle"), pk=pk)
    if not CircleEnrollment.objects.filter(
        student=request.user, circle=session.circle, status=CircleEnrollment.Status.ACTIVE
    ).exists():
        raise PermissionDenied
    if request.method == "POST":
        proposed_date = request.POST.get("proposed_date")
        proposed_time = request.POST.get("proposed_time") or None
        reason = request.POST.get("reason", "").strip()
        if not proposed_date or not reason:
            messages.error(request, "يرجى ملء جميع الحقول المطلوبة")
            return redirect("accounts:student_session_detail", pk=pk)
        SessionRescheduleRequest.objects.create(
            session=session,
            requested_by=request.user,
            proposed_date=proposed_date,
            proposed_time=proposed_time,
            reason=reason,
        )
        messages.success(request, "تم إرسال طلب تعديل الموعد بنجاح")
        return redirect("accounts:student_session_detail", pk=pk)
    return redirect("accounts:student_session_detail", pk=pk)

@login_required
@role_required(User.Role.STUDENT)
def student_reschedule_requests(request):
    """The student's own session-reschedule requests and their status."""
    reschedule_reqs = SessionRescheduleRequest.objects.filter(
        requested_by=request.user,
    ).select_related("session", "session__circle", "reviewed_by").order_by("-created_at")
    status_filter = request.GET.get("status", "")
    if status_filter:
        reschedule_reqs = reschedule_reqs.filter(status=status_filter)
    paginator = Paginator(reschedule_reqs, 20)
    page_obj = paginator.get_page(request.GET.get("page", 1))
    return render(request, "dashboard/student/reschedule_requests.html", {
        "requests": page_obj,
        "page_obj": page_obj,
    })

@login_required
@role_required(User.Role.STUDENT)
def student_stats(request):
    achievement = getattr(request.user, "achievement", None)

    att_counts = Attendance.objects.filter(student=request.user).aggregate(
        present=Sum(Case(When(status=Attendance.Status.PRESENT, then=1), default=0, output_field=IntegerField())),
        late=Sum(Case(When(status=Attendance.Status.LATE, then=1), default=0, output_field=IntegerField())),
        absent=Sum(Case(When(status__in=[Attendance.Status.ABSENT_UNJUSTIFIED, Attendance.Status.ABSENT], then=1), default=0, output_field=IntegerField())),
        justified=Sum(Case(When(justification_status=Attendance.JustificationStatus.ACCEPTED, then=1), default=0, output_field=IntegerField())),
        total=Count('id'),
    )
    present_count = att_counts['present'] or 0
    total_att = att_counts['total'] or 0
    attendance_rate = round(present_count / total_att * 100, 1) if total_att else 0

    # Totals come exclusively from what the teacher recorded in sessions
    # (ProgressLog) — the deprecated MemorizationProgress tracker and its
    # mastered/memorizing statuses are no longer surfaced here.
    from apps.references.utils import thumn_start_keys
    from apps.memorization.models import ProgressLog
    _keys = thumn_start_keys()
    _my_logs = ProgressLog.objects.filter(student=request.user)

    def _my_thumns(category):
        return _my_logs.filter(log_category=category).thumn_total(_keys=_keys)

    memo_data = {
        'hifz_thumns': _my_thumns(ProgressLog.Category.HIFDH),
        'murajaa_thumns': _my_thumns(ProgressLog.Category.MURAJAAH),
    }

    grade_avg = RecitationGrade.objects.filter(student=request.user).aggregate(
        avg=Sum(F('score') * 1.0) / Count('id'),
    )['avg'] or 0

    enrollments = CircleEnrollment.objects.filter(
        student=request.user, status=CircleEnrollment.Status.ACTIVE
    ).select_related('circle', 'circle__teacher', 'current_surah')

    rankings = []
    for enr in enrollments:
        cid = enr.circle_id
        circle_students = CircleEnrollment.objects.filter(circle_id=cid, status='active').values_list('student_id', flat=True)
        c_hifz = _thumn_totals_by_student(
            ProgressLog.objects.filter(
                session__circle_id=cid, student_id__in=list(circle_students)
            ),
            key=lambda sid: str(sid),
        )

        c_att = {}
        c_att_qs = Attendance.objects.filter(session__circle_id=cid, student_id__in=list(circle_students)).values('student_id').annotate(
            present=Count('id', filter=Q(status=Attendance.Status.PRESENT)),
            total=Count('id'),
        )
        for a in c_att_qs:
            c_att[str(a['student_id'])] = {'present': a['present'], 'total': a['total'], 'rate': round(a['present'] / a['total'] * 100) if a['total'] else 0}

        c_grades = {}
        c_grade_qs = RecitationGrade.objects.filter(session__circle_id=cid, student_id__in=list(circle_students)).values('student_id').annotate(
            avg=Sum(F('score') * 1.0) / Count('id'),
        )
        for g in c_grade_qs:
            c_grades[str(g['student_id'])] = round(g['avg'], 1)

        members = []
        for sid in circle_students:
            ssid = str(sid)
            h = c_hifz.get(ssid, {})
            a = c_att.get(ssid, {})
            # Same weighting as the leaderboards: mastered thumn = 20 pts.
            score = h.get('mastered_thumns', 0) * 20 + a.get('present', 0) * 10 + (c_grades.get(ssid, 0) or 0)
            members.append({'student_id': sid, 'score': score})

        members.sort(key=lambda x: x['score'], reverse=True)
        cur_user_id = request.user.id
        user_rank = next((i + 1 for i, m in enumerate(members) if m['student_id'] == cur_user_id), None)
        user_score = next((m['score'] for m in members if m['student_id'] == cur_user_id), 0)

        rankings.append({'circle': enr.circle, 'rank': user_rank, 'total': len(members), 'score': user_score})

    # Merged workspace: الإحصائيات now also carries the memorized-rubs progress,
    # the completion estimator (حاسبة الختم), and the detailed hifz plan.
    from apps.memorization.models import MemorizationRecord
    from apps.memorization.views import _estimator_context
    memorized_rubs = MemorizationRecord.objects.memorized(request.user).select_related("rub")
    memorized_rub_count = memorized_rubs.count()
    progress_data, progress_data_json = _memorization_plan_data(request.user)

    return render(request, "dashboard/student/stats.html", {
        'attendance_rate': attendance_rate,
        'present_count': present_count,
        'absent_count': att_counts['absent'] or 0,
        'late_count': att_counts['late'] or 0,
        'justified_count': att_counts['justified'] or 0,
        'total_attendance': total_att,
        'hifz_units': format_hizb_thumn(memo_data['hifz_thumns']),
        'murajaa_units': format_hizb_thumn(memo_data['murajaa_thumns']),
        'avg_grade': round(grade_avg, 1),
        'achievement': achievement,
        'rankings': rankings,
        'memorized_rubs': memorized_rubs,
        'memorized_total': memorized_rub_count,
        'memorized_thumns': memorized_rub_count * 2,
        'memorized_units': format_hizb_thumn(memorized_rub_count * 2),
        'progress_data': progress_data,
        'progress_data_json': progress_data_json,
        **_estimator_context(request.user),
    })

def _thumn_totals_by_student(log_qs, key=lambda sid: sid):
    """Per-student memorization totals in thumns (the tracking unit) from a
    ProgressLog queryset — i.e. exclusively what teachers recorded in
    sessions. `mastered_thumns` (kept for the shared scoring formula:
    hifdh thumn = 20 pts) now equals the distinct hifdh thumns covered.
    Returns {key(student_id): {'total_thumns', 'mastered_thumns',
    'murajaa_thumns', 'total_units', 'mastered_units', 'murajaa_units'}}."""
    from apps.memorization.models import ProgressLog
    from apps.references.utils import thumn_start_keys

    keys = thumn_start_keys()
    buckets = {}  # sid -> {'hifz': [...], 'murajaa': [...], 'hifz_amt': 0, 'murajaa_amt': 0}
    rows = log_qs.values_list(
        'student_id', 'surah_id', 'start_ayah', 'end_ayah', 'log_category', 'total_thumns'
    )
    for sid, surah_id, a_from, a_to, category, amount in rows:
        b = buckets.setdefault(sid, {'hifz': [], 'murajaa': [], 'hifz_amt': 0, 'murajaa_amt': 0})
        if category == ProgressLog.Category.HIFDH:
            if surah_id:
                b['hifz'].append((surah_id, a_from, a_to))
            else:
                b['hifz_amt'] += amount
        elif category == ProgressLog.Category.MURAJAAH:
            if surah_id:
                b['murajaa'].append((surah_id, a_from, a_to))
            else:
                b['murajaa_amt'] += amount

    data = {}
    for sid, b in buckets.items():
        total = count_thumns(b['hifz'], _keys=keys) + b['hifz_amt']
        murajaa = count_thumns(b['murajaa'], _keys=keys) + b['murajaa_amt']
        data[key(sid)] = {
            'total_thumns': total,
            'mastered_thumns': total,
            'murajaa_thumns': murajaa,
            'total_units': format_hizb_thumn(total),
            'mastered_units': format_hizb_thumn(total),
            'murajaa_units': format_hizb_thumn(murajaa),
        }
    return data


@login_required
@role_required(User.Role.STUDENT)
def student_circle_leaderboard(request, pk):
    circle = get_object_or_404(Circle, pk=pk)
    if not CircleEnrollment.objects.filter(
        student=request.user, circle=circle, status=CircleEnrollment.Status.ACTIVE
    ).exists():
        raise PermissionDenied

    enrollments = CircleEnrollment.objects.filter(circle=circle, status='active').select_related('student', 'current_surah')
    student_ids = [e.student_id for e in enrollments]

    from apps.memorization.models import ProgressLog
    hifz_data = _thumn_totals_by_student(
        ProgressLog.objects.filter(
            session__circle=circle, student_id__in=student_ids
        ),
        key=lambda sid: str(sid),
    )

    att_counts = Attendance.objects.filter(
        session__circle=circle, student_id__in=student_ids
    ).values('student_id').annotate(
        present=Count('id', filter=Q(status=Attendance.Status.PRESENT)),
        total=Count('id'),
    )
    att_data = {}
    for a in att_counts:
        sid = str(a['student_id'])
        att_data[sid] = {
            'present': a['present'],
            'total': a['total'],
            'rate': round(a['present'] / a['total'] * 100) if a['total'] else 0,
        }

    grade_data = {}
    grades = RecitationGrade.objects.filter(
        session__circle=circle, student_id__in=student_ids
    ).values('student_id').annotate(
        avg_score=Sum(F('score') * 1.0) / Count('id'),
    )
    for g in grades:
        sid = str(g['student_id'])
        grade_data[sid] = round(g['avg_score'], 1)

    leaderboard = []
    for enrollment in enrollments:
        sid = str(enrollment.student_id)
        hifz = hifz_data.get(sid, {})
        att = att_data.get(sid, {})
        leaderboard.append({
            'student': enrollment.student,
            'current_surah': enrollment.current_surah,
            'total_thumns': hifz.get('total_thumns', 0),
            'mastered_thumns': hifz.get('mastered_thumns', 0),
            'total_units': hifz.get('total_units', '0'),
            'mastered_units': hifz.get('mastered_units', '0'),
            'murajaa_units': hifz.get('murajaa_units', '0'),
            'attendance_rate': att.get('rate', 0),
            'avg_grade': grade_data.get(sid),
            # One mastered thumn outweighs one attendance (20 vs 10 points).
            'score': hifz.get('mastered_thumns', 0) * 20 + att.get('present', 0) * 10 + (grade_data.get(sid, 0) or 0),
        })

    leaderboard.sort(key=lambda x: x['score'], reverse=True)
    for i, entry in enumerate(leaderboard, 1):
        entry['rank'] = i

    return render(request, "dashboard/student/leaderboard.html", {
        "circle": circle,
        "leaderboard": leaderboard,
    })


@login_required
@role_required(User.Role.STUDENT)
def student_leaderboard(request):
    enrollments = CircleEnrollment.objects.filter(
        student=request.user, status=CircleEnrollment.Status.ACTIVE
    ).values_list('circle_id', flat=True)

    active_enrollments = CircleEnrollment.objects.filter(
        circle_id__in=list(enrollments), status='active'
    ).select_related('student', 'current_surah', 'circle')

    if not active_enrollments:
        return render(request, "dashboard/student/global_leaderboard.html", {"leaderboard": [], "circles": []})

    student_ids = list(active_enrollments.values_list('student_id', flat=True))

    from apps.memorization.models import ProgressLog
    hifz_data = _thumn_totals_by_student(
        ProgressLog.objects.filter(student_id__in=student_ids),
    )

    att_counts = Attendance.objects.filter(
        student_id__in=student_ids
    ).values('student_id').annotate(
        present=Count('id', filter=Q(status=Attendance.Status.PRESENT)),
        total=Count('id'),
    )
    att_data = {}
    for a in att_counts:
        sid = a['student_id']
        att_data[sid] = {
            'present': a['present'],
            'total': a['total'],
            'rate': round(a['present'] / a['total'] * 100) if a['total'] else 0,
        }

    grade_data = {}
    grades = RecitationGrade.objects.filter(
        student_id__in=student_ids
    ).values('student_id').annotate(
        avg_score=Sum(F('score') * 1.0) / Count('id'),
    )
    for g in grades:
        grade_data[g['student_id']] = round(g['avg_score'], 1)

    seen_students = set()
    leaderboard = []
    for enr in active_enrollments:
        sid = enr.student_id
        if sid in seen_students:
            continue
        seen_students.add(sid)
        hifz = hifz_data.get(sid, {})
        att = att_data.get(sid, {})
        leaderboard.append({
            'student': enr.student,
            'circle': enr.circle,
            'total_thumns': hifz.get('total_thumns', 0),
            'mastered_thumns': hifz.get('mastered_thumns', 0),
            'total_units': hifz.get('total_units', '0'),
            'mastered_units': hifz.get('mastered_units', '0'),
            'attendance_rate': att.get('rate', 0),
            'avg_grade': grade_data.get(sid),
            # One mastered thumn outweighs one attendance (20 vs 10 points).
            'score': hifz.get('mastered_thumns', 0) * 20 + att.get('present', 0) * 10 + (grade_data.get(sid, 0) or 0),
        })

    leaderboard.sort(key=lambda x: x['score'], reverse=True)
    for i, entry in enumerate(leaderboard, 1):
        entry['rank'] = i

    circles = Circle.objects.filter(id__in=list(enrollments))

    return render(request, "dashboard/student/global_leaderboard.html", {
        "leaderboard": leaderboard,
        "circles": circles,
    })


@login_required
@role_required(User.Role.STUDENT)
def student_tasks(request):
    tasks = StudyTask.objects.for_student(request.user)
    status_filter = request.GET.get("status")
    if status_filter in ("pending", "done", "validated", "rejected"):
        tasks = tasks.filter(status=status_filter)
    my_tasks = StudyTask.objects.for_student(request.user)
    return render(request, "dashboard/student/tasks.html", {
        "tasks": tasks.select_related("surah", "assigned_by", "session"),
        "current_filter": status_filter,
        "counts": {
            "all": my_tasks.count(),
            "pending": my_tasks.pending().count(),
            "overdue": my_tasks.overdue().count(),
            "done": my_tasks.done().count(),
            "validated": my_tasks.validated().count(),
            "rejected": my_tasks.filter(status=StudyTask.Status.REJECTED).count(),
        },
    })





@login_required
@role_required(User.Role.STUDENT)
def student_task_mark_done(request, pk):
    task = get_object_or_404(StudyTask, pk=pk, student=request.user)
    if task.status == StudyTask.Status.PENDING:
        task.mark_done(by=request.user)
        messages.success(request, "تم تأكيد إنجاز المهمة")
    return redirect("accounts:student_tasks")
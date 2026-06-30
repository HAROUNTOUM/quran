from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from apps.accounts.decorators import role_required
from django.http import JsonResponse
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q, F, IntegerField, Case, When, Prefetch
from django.core.paginator import Paginator
from datetime import date
from django.utils import timezone

from apps.accounts.models import User
from apps.circles.models import Circle, CircleEnrollment, Session
from apps.attendance.models import Attendance
from apps.requests.models import SupportRequest
from apps.announcements.models import Announcement
from apps.notifications.models import Notification
from apps.memorization.models import MemorizationProgress, ReviewRequest
from apps.certificates.models import Certificate
from apps.references.models import Surah
from apps.references.utils import ayahs_to_hizb_quarters

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
        present=Sum(Case(When(status__in=['present', 'late', 'left_early'], then=1), default=0, output_field=IntegerField())),
        absent=Sum(Case(When(status='absent', then=1), default=0, output_field=IntegerField())),
        total=Count('id'),
    )
    present_count = att_counts['present'] or 0
    total_attendance = att_counts['total'] or 0
    attendance_rate = round(present_count / total_attendance * 100, 1) if total_attendance else 0
    absent_count = att_counts['absent'] or 0

    memo_counts = MemorizationProgress.objects.filter(
        enrollment__student=request.user
    ).values('type').annotate(cnt=Count('id'))
    hifz_count = next((m['cnt'] for m in memo_counts if m['type'] == 'hifz'), 0)
    murajaa_count = next((m['cnt'] for m in memo_counts if m['type'] == 'murajaa'), 0)

    recent_announcements = Announcement.objects.all().order_by('-created_at')[:5]

    upcoming_sessions = Session.objects.filter(
        circle_id__in=circle_ids, session_date__gte=date.today()
    ).select_related('circle').order_by('session_date', 'session_time')[:5]

    pending_review_count = ReviewRequest.objects.filter(
        student=request.user, status=ReviewRequest.Status.PENDING
    ).count()

    unread_notif_count = Notification.objects.filter(
        recipient=request.user, is_read=False
    ).count()

    recent_certificates = Certificate.objects.filter(
        student=request.user, status="issued",
    ).select_related("template").order_by("-issue_date")[:3]

    return render(request, 'dashboard/student/home.html', {
        'circles': [en.circle for en in enrollments],
        'enrollments': enrollments,
        'recent_attendance': recent_attendance,
        'attendance_rate': attendance_rate,
        'present_count': present_count,
        'total_attendance': total_attendance,
        'absent_count': absent_count,
        'hifz_count': hifz_count,
        'murajaa_count': murajaa_count,
        'recent_announcements': recent_announcements,
        'upcoming_sessions': upcoming_sessions,
        'pending_review_count': pending_review_count,
        'unread_notif_count': unread_notif_count,
        'recent_certificates': recent_certificates,
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
        from apps.notifications.models import Notification
        for admin in User.objects.filter(role=User.Role.ADMIN, is_active=True):
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
@login_required
@role_required(User.Role.STUDENT)
def student_memorization(request):

    enrollments = CircleEnrollment.objects.filter(
        student=request.user, status=CircleEnrollment.Status.ACTIVE
    ).select_related('circle', 'current_surah').prefetch_related(
        Prefetch(
            'memorization_progress',
            queryset=MemorizationProgress.objects.select_related('surah'),
        )
    )

    progress_data = []
    for en in enrollments:
        all_records = list(en.memorization_progress.all())
        hifz_records = [r for r in all_records if r.type == 'hifz']
        murajaa_records = [r for r in all_records if r.type == 'murajaa']

        def sum_ayahs(records):
            return sum((r.ayah_to - r.ayah_from + 1) for r in records)

        def sum_ayahs_mastered(records):
            return sum((r.ayah_to - r.ayah_from + 1) for r in records if r.status == 'mastered')

        hifz_total = sum_ayahs(hifz_records)
        hifz_mastered = sum_ayahs_mastered(hifz_records)
        murajaa_total = sum_ayahs(murajaa_records)
        murajaa_mastered = sum_ayahs_mastered(murajaa_records)

        hifz_hizb, hifz_qua = ayahs_to_hizb_quarters(hifz_total)
        hifz_mas_hizb, hifz_mas_qua = ayahs_to_hizb_quarters(hifz_mastered)
        muj_hizb, muj_qua = ayahs_to_hizb_quarters(murajaa_total)
        muj_mas_hizb, muj_mas_qua = ayahs_to_hizb_quarters(murajaa_mastered)

        progress_data.append({
            'enrollment': en,
            'circle_name': en.circle.name,
            'current_surah': en.current_surah.name_ar if en.current_surah else '—',
            'hifz_records': hifz_records,
            'murajaa_records': murajaa_records,
            'hifz_total': hifz_total,
            'hifz_mastered': hifz_mastered,
            'hifz_progress': round(hifz_mastered / hifz_total * 100) if hifz_total else 0,
            'hifz_hizb': hifz_hizb, 'hifz_quarters': hifz_qua,
            'hifz_mas_hizb': hifz_mas_hizb, 'hifz_mas_quarters': hifz_mas_qua,
            'murajaa_total': murajaa_total,
            'murajaa_mastered': murajaa_mastered,
            'murajaa_progress': round(murajaa_mastered / murajaa_total * 100) if murajaa_total else 0,
            'muj_hizb': muj_hizb, 'muj_quarters': muj_qua,
            'muj_mas_hizb': muj_mas_hizb, 'muj_mas_quarters': muj_mas_qua,
        })

    import json
    progress_data_json = json.dumps([{
        'hifz_total': d['hifz_total'],
        'hifz_mastered': d['hifz_mastered'],
        'murajaa_total': d['murajaa_total'],
        'murajaa_mastered': d['murajaa_mastered'],
    } for d in progress_data])

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

    return render(request, "dashboard/student/session_detail.html", {
        "session": session,
        "attendance": attendance,
        "user_turn": user_turn,
        "turns": turns,
        "can_justify": attendance and attendance.status in ("absent", "pending_justification"),
    })
@login_required
@role_required(User.Role.STUDENT)
def student_claim_turn(request, pk):
    from apps.circles.models import Session, CircleEnrollment, SessionTurn
    session = get_object_or_404(Session.objects.select_related("circle"), pk=pk)
    if not CircleEnrollment.objects.filter(
        student=request.user, circle=session.circle, status=CircleEnrollment.Status.ACTIVE
    ).exists():
        raise PermissionDenied
    if not session.is_unlocked:
        from django.http import JsonResponse
        return JsonResponse({"success": False, "message": "الحصة غير متاحة بعد"}, status=403)

    existing = SessionTurn.objects.filter(session=session, student=request.user).first()
    if existing:
        from django.http import JsonResponse
        return JsonResponse({"success": False, "message": "لديك دور بالفعل"}, status=400)

    taken = set(SessionTurn.objects.filter(session=session).values_list("turn_number", flat=True))
    n = 1
    while n in taken:
        n += 1
    SessionTurn.objects.create(session=session, student=request.user, turn_number=n)

    from django.http import JsonResponse
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

    deleted, _ = SessionTurn.objects.filter(session=session, student=request.user).delete()
    if not deleted:
        from django.http import JsonResponse
        return JsonResponse({"success": False, "message": "ليس لديك دور"}, status=400)

    from django.http import JsonResponse
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
@login_required
@role_required(User.Role.STUDENT)
def student_request_create(request):
    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        body = request.POST.get("body", "").strip()
        req_type = request.POST.get("type", "other")
        priority = request.POST.get("priority", "normal")
        if not title or not body:
            return render(request, "dashboard/student/request_create.html", {
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
        return redirect("accounts:student_requests")
    return render(request, "dashboard/student/request_create.html")
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
    present_count = Attendance.objects.filter(student=request.user, status__in=["present", "late", "left_early"]).count()
    total_count = Attendance.objects.filter(student=request.user).count()
    absent_count = Attendance.objects.filter(student=request.user, status="absent").count()
    excused_count = Attendance.objects.filter(student=request.user, status="excused").count()
    return render(request, "dashboard/student/attendance.html", {
        "attendance": page_obj,
        "page_obj": page_obj,
        "present_count": present_count,
        "total_count": total_count,
        "absent_count": absent_count,
        "excused_count": excused_count,
    })
@login_required
@role_required(User.Role.STUDENT)
def student_review_requests(request):
    qs = ReviewRequest.objects.filter(student=request.user).select_related("circle", "surah").order_by("-created_at")
    status_filter = request.GET.get("status", "")
    if status_filter:
        qs = qs.filter(status=status_filter)
    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get("page", 1))
    return render(request, "dashboard/student/review_requests.html", {
        "requests": page_obj,
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
        circle_id = request.POST.get("circle")
        req_type = request.POST.get("type", "review")
        surah_id = request.POST.get("surah")
        ayah_from = request.POST.get("ayah_from")
        ayah_to = request.POST.get("ayah_to")
        notes = request.POST.get("notes", "").strip()
        if not circle_id:
            return render(request, "dashboard/student/review_request_create.html", {
                "error": "يرجى اختيار الحلقة",
                "enrollments": enrollments,
                "surahs": surahs,
                "form_data": request.POST,
            })
        ReviewRequest.objects.create(
            student=request.user,
            circle_id=circle_id,
            type=req_type,
            surah_id=surah_id or None,
            ayah_from=ayah_from or None,
            ayah_to=ayah_to or None,
            notes=notes,
        )
        messages.success(request, "تم إرسال الطلب بنجاح")
        return redirect("accounts:student_review_requests")
    return render(request, "dashboard/student/review_request_create.html", {
        "enrollments": enrollments,
        "surahs": surahs,
    })
@login_required
@role_required(User.Role.STUDENT)
def student_circle_detail(request, pk):
    enrollment = get_object_or_404(CircleEnrollment, circle_id=pk, student=request.user, status=CircleEnrollment.Status.ACTIVE)
    circle = enrollment.circle
    upcoming_sessions = Session.objects.filter(circle=circle, session_date__gte=date.today()).order_by("session_date")[:10]
    past_sessions = Session.objects.filter(circle=circle, session_date__lt=date.today()).order_by("-session_date")[:10]
    next_session = upcoming_sessions.first()
    return render(request, "dashboard/student/circle_detail.html", {
        "circle": circle,
        "enrollment": enrollment,
        "upcoming_sessions": upcoming_sessions,
        "past_sessions": past_sessions,
        "next_session": next_session,
    })
@login_required
@role_required(User.Role.STUDENT)
def student_sessions(request):
    circle_ids = CircleEnrollment.objects.filter(
        student=request.user, status=CircleEnrollment.Status.ACTIVE
    ).values_list("circle_id", flat=True)
    upcoming = Session.objects.filter(circle_id__in=circle_ids, session_date__gte=date.today()).select_related("circle").order_by("session_date", "session_time")
    past = Session.objects.filter(circle_id__in=circle_ids, session_date__lt=date.today()).select_related("circle").order_by("-session_date", "-session_time")[:30]
    from apps.attendance.models import SessionAttendanceIntent
    intents = {
        i.session_id: i
        for i in SessionAttendanceIntent.objects.filter(
            session__in=upcoming, student=request.user,
        )
    }
    return render(request, "dashboard/student/sessions.html", {
        "upcoming": upcoming,
        "past": past,
        "today": date.today(),
        "intents": intents,
    })
@login_required
@role_required(User.Role.STUDENT)
def student_exam_results(request):
    from apps.exams.services import get_student_marks
    results = get_student_marks(request.user)
    return render(request, "dashboard/exams/student_results.html", {"results": results})
@login_required
@role_required(User.Role.STUDENT)
def student_achievements(request):
    achievement = getattr(request.user, "achievement", None)
    total_hifz = MemorizationProgress.objects.filter(
        enrollment__student=request.user, type='hifz', status='mastered'
    ).aggregate(t=Sum(F('ayah_to') - F('ayah_from') + 1))['t'] or 0
    total_murajaa = MemorizationProgress.objects.filter(
        enrollment__student=request.user, type='murajaa', status='mastered'
    ).aggregate(t=Sum(F('ayah_to') - F('ayah_from') + 1))['t'] or 0
    hifz_hizb, hifz_qua = ayahs_to_hizb_quarters(total_hifz)
    murajaa_hizb, murajaa_qua = ayahs_to_hizb_quarters(total_murajaa)
    recent_progress = MemorizationProgress.objects.filter(
        enrollment__student=request.user
    ).select_related('surah').order_by('-created_at')[:10]
    return render(request, "dashboard/student/achievements.html", {
        "achievement": achievement,
        "total_hifz_ayahs": total_hifz,
        "total_murajaa_ayahs": total_murajaa,
        "hifz_hizb": hifz_hizb,
        "hifz_quarters": hifz_qua,
        "murajaa_hizb": murajaa_hizb,
        "murajaa_quarters": murajaa_qua,
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
        student=request.user, justification__gt=""
    ).select_related("session__circle", "reviewed_by").order_by("-updated_at")
    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get("page", 1))
    return render(request, "dashboard/student/justifications.html", {
        "justifications": page_obj,
        "page_obj": page_obj,
    })
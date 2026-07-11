from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db.models import Sum, F, IntegerField, Case, When, Count, Q
from django.utils.http import url_has_allowed_host_and_scheme


def _safe_redirect_target(request, url, fallback="/dashboard/"):
    """Only follow same-host / relative URLs — prevents an open redirect via a
    notification.link (admin-settable) or a spoofed Referer header."""
    if url and url_has_allowed_host_and_scheme(
        url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return url
    return fallback

from apps.accounts.models import User, TeacherAbsence
from apps.accounts.forms import ProfileForm
from apps.circles.models import Circle, CircleEnrollment, Session
from apps.memorization.models import MemorizationProgress, ProgressLog
from apps.attendance.models import Attendance
from apps.references.utils import count_thumns, format_hizb_thumn, thumns_to_hizb

@login_required
def profile_view(request):
    user = request.user

    profile_stats = []
    if user.role == User.Role.MAIN_ADMIN:
        profile_stats = [
            {"label": "الطلاب المعتمدون", "value": User.objects.filter(
                role=User.Role.STUDENT, is_approved=User.ApprovalStatus.APPROVED
            ).count()},
            {"label": "المعلمون المعتمدون", "value": User.objects.filter(
                role=User.Role.TEACHER, is_approved=User.ApprovalStatus.APPROVED
            ).count()},
            {"label": "الحلقات النشطة", "value": Circle.objects.filter(status=Circle.Status.ACTIVE).count()},
            {"label": "الحصص المنتهية", "value": Session.objects.filter(status=Session.Status.ENDED).count()},
        ]
    elif user.role == User.Role.SUB_ADMIN:
        profile_stats = [
            {"label": "الطلاب المعتمدون", "value": User.objects.filter(
                role=User.Role.STUDENT, is_approved=User.ApprovalStatus.APPROVED
            ).count()},
            {"label": "الحلقات النشطة", "value": Circle.objects.filter(status=Circle.Status.ACTIVE).count()},
        ]
    elif user.role == User.Role.TEACHER:
        hifz_thumns = count_thumns(
            MemorizationProgress.objects.filter(
                enrollment__circle__teacher=user, type='hifz', status='mastered'
            ).values_list('surah_id', 'ayah_from', 'ayah_to')
        )
        profile_stats = [
            {"label": "حلقات التدريس", "value": Circle.objects.filter(teacher=user).count()},
            {"label": "الطلاب", "value": CircleEnrollment.objects.filter(circle__teacher=user, status='active').count()},
            {"label": "إجمالي حفظ الطلاب", "value": format_hizb_thumn(hifz_thumns)},
            {"label": "طلبات الغياب", "value": TeacherAbsence.objects.filter(teacher=user).count()},
        ]
    else:
        enrollments = CircleEnrollment.objects.filter(student=user, status='active')
        attended = Attendance.objects.filter(student=user, status=Attendance.Status.PRESENT).count()
        total_att = Attendance.objects.filter(student=user).count()
        att_rate = round(attended / total_att * 100) if total_att else 0
        hifz_thumns = count_thumns(
            MemorizationProgress.objects.filter(
                enrollment__student=user, type='hifz', status='mastered'
            ).values_list('surah_id', 'ayah_from', 'ayah_to')
        )
        murajaa_thumns = count_thumns(
            MemorizationProgress.objects.filter(
                enrollment__student=user, type='murajaa', status='mastered'
            ).values_list('surah_id', 'ayah_from', 'ayah_to')
        )
        hifz_hizb, hifz_rem = thumns_to_hizb(hifz_thumns)
        mura_hizb, mura_rem = thumns_to_hizb(murajaa_thumns)
        recent_grades = ProgressLog.objects.filter(
            student=user
        ).select_related('surah', 'session__circle').order_by('-created_at')[:5]
        profile_stats = [
            {"label": "الحلقات المسجّل بها", "value": enrollments.count()},
            {"label": "نسبة الحضور", "value": f"{att_rate}%"},
            {"label": "", "value": ""},
            {"label": "", "value": ""},
        ]
        # Return extra context for students
        return render(request, "dashboard/profile.html", {
            "profile_user": user,
            "profile_stats": profile_stats,
            "recent_login": user.last_login,
            "is_student": True,
            "hifz_thumns": hifz_thumns,
            "murajaa_thumns": murajaa_thumns,
            "hifz_units": format_hizb_thumn(hifz_thumns),
            "murajaa_units": format_hizb_thumn(murajaa_thumns),
            "total_thumns": hifz_thumns + murajaa_thumns,
            "hifz_hizb": hifz_hizb,
            "hifz_thumn_rem": hifz_rem,
            "murajaa_hizb": mura_hizb,
            "murajaa_thumn_rem": mura_rem,
            "recent_grades": recent_grades,
            "enrollments": enrollments.select_related('circle__teacher', 'current_surah'),
        })

    return render(request, "dashboard/profile.html", {
        "profile_user": user,
        "profile_stats": profile_stats,
        "recent_login": user.last_login,
        "is_student": False,
    })
@login_required
def profile_edit_view(request):
    form = ProfileForm(instance=request.user, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم تحديث ملفك الشخصي بنجاح")
        return redirect("accounts:profile")

    return render(request, "dashboard/profile_edit.html", {
        "form": form,
        "profile_user": request.user,
    })
@login_required
def notification_list(request):
    from apps.notifications.models import Notification
    notifications = Notification.objects.filter(recipient=request.user)[:10]
    return render(request, "dashboard/partials/notification_items.html", {"notifications": notifications})
@login_required
def notification_mark_read(request, pk):
    from apps.notifications.models import Notification
    from apps.notifications.signals import _send_unread_count_ws
    notification = get_object_or_404(Notification, pk=pk, recipient=request.user)
    notification.mark_as_read()
    _send_unread_count_ws(request.user.id)
    return redirect(_safe_redirect_target(request, notification.link))
@login_required
def notification_mark_all_read(request):
    if request.method == "POST":
        from apps.notifications.models import Notification
        from apps.notifications.signals import _send_unread_count_ws
        Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
        _send_unread_count_ws(request.user.id)
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"status": "ok"})
        messages.success(request, "تم تحديد جميع الإشعارات كمقروءة")
        return redirect(_safe_redirect_target(request, request.META.get("HTTP_REFERER")))
    return redirect("/dashboard/")
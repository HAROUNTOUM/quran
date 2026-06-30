from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse

from apps.accounts.models import User, TeacherAbsence
from apps.accounts.forms import ProfileForm
from apps.circles.models import Circle, CircleEnrollment

@login_required
def profile_view(request):
    user = request.user

    profile_stats = []
    if user.role == User.Role.ADMIN:
        profile_stats = [
            {"label": "الطلاب المعتمدون", "value": User.objects.filter(
                role=User.Role.STUDENT, is_approved=User.ApprovalStatus.APPROVED
            ).count()},
            {"label": "المعلمون المعتمدون", "value": User.objects.filter(
                role=User.Role.TEACHER, is_approved=User.ApprovalStatus.APPROVED
            ).count()},
            {"label": "الحلقات النشطة", "value": Circle.objects.filter(status=Circle.Status.ACTIVE).count()},
        ]
    elif user.role == User.Role.SUPERVISOR:
        profile_stats = [
            {"label": "الطلاب المعتمدون", "value": User.objects.filter(
                role=User.Role.STUDENT, is_approved=User.ApprovalStatus.APPROVED
            ).count()},
            {"label": "الحلقات النشطة", "value": Circle.objects.filter(status=Circle.Status.ACTIVE).count()},
        ]
    elif user.role == User.Role.TEACHER:
        profile_stats = [
            {"label": "حلقات التدريس", "value": Circle.objects.filter(teacher=user).count()},
            {"label": "طلبات الغياب", "value": TeacherAbsence.objects.filter(teacher=user).count()},
        ]
    else:
        profile_stats = [
            {"label": "الحلقات المسجّل بها", "value": CircleEnrollment.objects.filter(student=user).count()},
        ]

    return render(request, "dashboard/profile.html", {
        "profile_user": user,
        "profile_stats": profile_stats,
        "recent_login": user.last_login,
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
    notification = get_object_or_404(Notification, pk=pk, recipient=request.user)
    notification.is_read = True
    notification.save(update_fields=["is_read"])
    return redirect(notification.link or "/dashboard/")
@login_required
def notification_mark_all_read(request):
    if request.method == "POST":
        from apps.notifications.models import Notification
        Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"status": "ok"})
        messages.success(request, "تم تحديد جميع الإشعارات كمقروءة")
        return redirect(request.META.get("HTTP_REFERER", "/dashboard/"))
    return redirect("/dashboard/")
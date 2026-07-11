"""Admin communications & support views: support requests, announcements,
and broadcast notifications.

Extracted from accounts/views/admin.py as part of the strangler refactor
(see docs/architecture-audit-2026-07-11.md). URL names are unchanged
(accounts:admin_requests / admin_announcements / admin_notifications / …);
this module is re-exported from accounts.views.

admin_requests / admin_request_detail / admin_notifications are batch-scoped
via apps.accounts.scoping so a SUB_ADMIN only sees support requests submitted
by, and notifications sent to, users in the batches they supervise.
"""
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts import scoping
from apps.accounts.decorators import role_required
from apps.accounts.models import User
from apps.announcements.models import Announcement
from apps.notifications.models import Notification
from apps.requests.models import Comment, SupportRequest


@login_required
@role_required(User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN)
def admin_requests(request):
    search = request.GET.get("search", "")
    req_type = request.GET.get("type", "")
    req_status = request.GET.get("status", "")
    req_priority = request.GET.get("priority", "")

    scoped = scoping.scoped_requests(
        request.user,
        SupportRequest.objects.select_related('submitted_by'),
    )
    reqs = scoped.order_by('-created_at')

    if search:
        reqs = reqs.filter(Q(title__icontains=search) | Q(body__icontains=search) | Q(submitted_by__full_name_ar__icontains=search))
    if req_type:
        reqs = reqs.filter(type=req_type)
    if req_status:
        reqs = reqs.filter(status=req_status)
    if req_priority:
        reqs = reqs.filter(priority=req_priority)

    total_count = scoped.count()
    under_review_count = scoped.filter(status='under_review').count()
    approved_count = scoped.filter(status__in=['approved', 'resolved']).count()
    urgent_count = scoped.filter(priority__in=['urgent', 'high']).count()

    paginator = Paginator(reqs, 15)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'dashboard/requests/list.html', {
        'requests': page_obj,
        'page_obj': page_obj,
        'total_count': total_count,
        'under_review_count': under_review_count,
        'approved_count': approved_count,
        'urgent_count': urgent_count,
    })


@login_required
@role_required(User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN)
def admin_request_detail(request, pk):
    request_obj = get_object_or_404(
        scoping.scoped_requests(
            request.user,
            SupportRequest.objects.select_related('submitted_by'),
        ),
        pk=pk,
    )

    if request.method == "POST":
        comment_body = request.POST.get("comment_body", "").strip()
        if comment_body:
            Comment.objects.create(
                request=request_obj,
                author=request.user,
                body=comment_body,
            )
            return redirect("accounts:admin_request_detail", pk=pk)

        new_status = request.POST.get("status")
        if new_status:
            try:
                request_obj.transition_to(new_status, by=request.user)
            except ValidationError as e:
                messages.error(request, " ".join(e.messages))
        return redirect("accounts:admin_request_detail", pk=pk)

    comments = request_obj.comments.select_related("author").all()

    return render(request, "dashboard/requests/detail.html", {
        "request_obj": request_obj,
        "comments": comments,
    })


@login_required
@role_required(User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN)
def admin_announcements(request):
    search = request.GET.get("search", "")
    announcements = Announcement.objects.select_related('author').order_by('-created_at')

    if search:
        announcements = announcements.filter(Q(title__icontains=search) | Q(body__icontains=search))

    paginator = Paginator(announcements, 15)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'dashboard/announcements/list.html', {'announcements': page_obj, 'page_obj': page_obj})


@login_required
@role_required(User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN)
def admin_announcement_create(request):
    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        body = request.POST.get("body", "").strip()
        if title and body:
            Announcement.objects.create(
                author=request.user,
                title=title,
                body=body,
            )
            return redirect("accounts:admin_announcements")
        return render(request, "dashboard/announcements/create.html", {"error": "يرجى ملء جميع الحقول"})

    return render(request, "dashboard/announcements/create.html")


@login_required
@role_required(User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN)
def admin_notifications(request):
    qs = scoping.scoped_notifications(
        request.user,
        Notification.objects.select_related("recipient"),
    ).order_by("-created_at")

    search = request.GET.get("search", "")
    if search:
        qs = qs.filter(Q(title__icontains=search) | Q(message__icontains=search))

    is_read = request.GET.get("is_read", "")
    if is_read in ("true", "false"):
        qs = qs.filter(is_read=(is_read == "true"))

    notif_type = request.GET.get("type", "")
    if notif_type:
        qs = qs.filter(type=notif_type)

    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    return render(request, "dashboard/notifications/list.html", {
        "notifications": page_obj,
        "page_obj": page_obj,
    })


@login_required
@role_required(User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN)
def admin_notification_create(request):
    if request.method == "POST":
        notif_type = request.POST.get("type", "").strip()
        title = request.POST.get("title", "").strip()
        message = request.POST.get("message", "").strip()
        link = request.POST.get("link", "").strip()
        target = request.POST.get("target", "all").strip()

        if not (notif_type and title and message):
            return render(request, "dashboard/notifications/create.html", {
                "error": "يرجى ملء جميع الحقول المطلوبة",
                "form_data": request.POST,
            })

        if notif_type not in dict(Notification.Type.choices):
            return render(request, "dashboard/notifications/create.html", {
                "error": "نوع الإشعار غير صحيح",
                "form_data": request.POST,
            })

        role_map = {
            "admins": User.Role.MAIN_ADMIN,
            "supervisors": User.Role.SUB_ADMIN,
            "teachers": User.Role.TEACHER,
            "students": User.Role.STUDENT,
        }
        if target == "all":
            users = User.objects.filter(
                is_approved=User.ApprovalStatus.APPROVED, is_active=True
            )
        elif target in role_map:
            users = User.objects.filter(
                role=role_map[target],
                is_approved=User.ApprovalStatus.APPROVED,
                is_active=True,
            )
        else:
            return render(request, "dashboard/notifications/create.html", {
                "error": "الهدف غير صحيح",
                "form_data": request.POST,
            })

        notifications = [
            Notification(recipient=u, type=notif_type, title=title, message=message, link=link)
            for u in users
        ]
        Notification.objects.bulk_create(notifications, batch_size=500)
        return redirect("accounts:admin_notifications")

    return render(request, "dashboard/notifications/create.html")

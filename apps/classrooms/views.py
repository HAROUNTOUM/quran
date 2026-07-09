from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.decorators import role_required
from apps.accounts.models import User
from apps.classrooms.models import TeacherRoom
from apps.classrooms.services import is_moderator, mint_jitsi_jwt


@login_required
def my_classroom(request):
    user = request.user

    if user.role == "teacher":
        room = user.get_or_create_room()
        return render(request, "dashboard/classrooms/teacher_room.html", {
            "room": room,
            "jitsi_domain": settings.JITSI_DOMAIN,
            "jitsi_jwt": mint_jitsi_jwt(user, room.room_name, moderator=True),
            "roster_count": user.get_roster().count(),
        })

    if user.role == "student":
        from apps.circles.models import CircleEnrollment
        enrollments = CircleEnrollment.objects.filter(
            student=user,
            status=CircleEnrollment.Status.ACTIVE,
            circle__teacher__room__isnull=False,
        ).select_related("circle__teacher__room")

        rooms = list({e.circle.teacher.room for e in enrollments if e.circle.teacher.room.is_active})

        if not rooms:
            messages.info(request, "لا توجد قاعات افتراضية متاحة حالياً — القاعات تظهر تلقائياً عند تسجيلك في حلقة")
            return redirect("accounts:student_dashboard")

        if len(rooms) == 1:
            return redirect("classrooms:join", slug=rooms[0].slug)

        return render(request, "dashboard/classrooms/student_rooms.html", {
            "rooms": rooms,
            "jitsi_domain": settings.JITSI_DOMAIN,
        })

    if user.role in (User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN):
        return redirect("classrooms:admin_list")

    raise PermissionDenied


@login_required
def join_room(request, slug):
    """Public (slug) entry point. Access order per Section C:
    authenticated (decorator) → room exists → active → allowed → render.
    Denials redirect to the dashboard with a message, never a bare 403."""
    room = get_object_or_404(TeacherRoom.objects.select_related("teacher"), slug=slug)

    if not room.is_active or not room.teacher.is_active:
        messages.error(request, "هذه القاعة غير متاحة حالياً")
        return redirect("accounts:dashboard")

    if not room.can_join(request.user):
        messages.error(request, "لا تملك صلاحية دخول هذه القاعة — القاعات متاحة لطلاب المعلم المسجلين فقط")
        return redirect("accounts:dashboard")

    is_owner = request.user.pk == room.teacher_id
    return render(request, "dashboard/classrooms/join.html", {
        "room": room,
        "jitsi_domain": settings.JITSI_DOMAIN,
        "jitsi_jwt": mint_jitsi_jwt(
            request.user, room.room_name,
            moderator=is_owner or is_moderator(request.user),
        ),
        "is_owner": is_owner,
    })


@login_required
@role_required(User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN)
def rooms_admin_list(request):
    """Admin oversight: all rooms + activate/deactivate."""
    if request.method == "POST":
        room = get_object_or_404(TeacherRoom, pk=request.POST.get("room_id"))
        room.is_active = not room.is_active
        room.save(update_fields=["is_active", "updated_at"])
        messages.success(
            request,
            f"تم {'تفعيل' if room.is_active else 'تعطيل'} قاعة {room.teacher.full_name_ar}",
        )
        return redirect("classrooms:admin_list")

    rooms = TeacherRoom.objects.select_related("teacher").order_by("teacher__full_name_ar")
    paginator = Paginator(rooms, 20)
    page_obj = paginator.get_page(request.GET.get("page", 1))
    return render(request, "dashboard/classrooms/admin_list.html", {
        "rooms": page_obj,
        "page_obj": page_obj,
    })

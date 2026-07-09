from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.dateparse import parse_datetime

from apps.accounts.decorators import role_required
from apps.accounts.models import User
from apps.usersettings.models import SystemSettings
from apps.usersettings.services import get_system_setting
from apps.webinars.models import Webinar, parse_stream_embed


def _feature_enabled() -> bool:
    return bool(get_system_setting("feature_webinars_enabled"))


def _feature_gate(request):
    """Non-admins are turned away while the module flag is off; admins pass
    so they can prepare webinars before enabling it platform-wide."""
    if request.user.role != User.Role.MAIN_ADMIN and not _feature_enabled():
        messages.info(request, "وحدة الندوات غير مفعلة حالياً")
        return redirect("accounts:dashboard")
    return None


# ── Audience ──────────────────────────────────────────────────────────

@login_required
def webinar_list(request):
    gate = _feature_gate(request)
    if gate:
        return gate
    webinars = Webinar.objects.filter(is_active=True).exclude(
        status=Webinar.Status.ENDED,
    )
    paginator = Paginator(webinars, 12)
    page_obj = paginator.get_page(request.GET.get("page", 1))
    return render(request, "dashboard/webinars/list.html", {
        "webinars": page_obj,
        "page_obj": page_obj,
    })


@login_required
def webinar_watch(request, pk):
    gate = _feature_gate(request)
    if gate:
        return gate
    webinar = get_object_or_404(Webinar, pk=pk)
    if not webinar.can_view(request.user):
        messages.error(request, "هذه الندوة غير متاحة")
        return redirect("webinars:list")
    if not webinar.is_watchable:
        messages.info(request, "البث غير متاح حالياً — تابع الموعد المعلن")
        return redirect("webinars:list")
    embed_url, chat_url = parse_stream_embed(webinar.stream_url, request.get_host())
    return render(request, "dashboard/webinars/watch.html", {
        "webinar": webinar,
        "embed_url": embed_url,
        "chat_url": chat_url,
    })


@login_required
def speaker_room(request, pk):
    """The real Jitsi call — admins + designated co-speakers only.
    The audience never reaches this view."""
    webinar = get_object_or_404(Webinar, pk=pk)
    if not webinar.can_join_speaker_room(request.user):
        messages.error(request, "غرفة المتحدثين مخصصة للمشرفين والمتحدثين المعينين فقط")
        return redirect("accounts:dashboard")
    if webinar.status not in (Webinar.Status.SCHEDULED, Webinar.Status.LIVE):
        messages.info(request, "هذه الندوة انتهت — غرفة المتحدثين مغلقة")
        return redirect("webinars:admin_list" if request.user.role == User.Role.MAIN_ADMIN else "accounts:dashboard")
    from apps.classrooms.services import mint_jitsi_jwt
    return render(request, "dashboard/webinars/speaker.html", {
        "webinar": webinar,
        "jitsi_domain": settings.JITSI_DOMAIN,
        "jitsi_jwt": mint_jitsi_jwt(request.user, webinar.speaker_room_name, moderator=True),
    })


# ── Admin management ─────────────────────────────────────────────────

@login_required
@role_required(User.Role.MAIN_ADMIN)
def webinar_admin_list(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "toggle_feature":
            settings = SystemSettings.load()
            current = _feature_enabled()
            settings.set("feature_webinars_enabled", not current, changed_by=request.user)
            messages.success(request, "تم تحديث حالة وحدة الندوات")

    webinars = Webinar.objects.select_related("created_by").all()
    paginator = Paginator(webinars, 20)
    page_obj = paginator.get_page(request.GET.get("page", 1))
    return render(request, "dashboard/webinars/admin_list.html", {
        "webinars": page_obj,
        "page_obj": page_obj,
        "feature_enabled": _feature_enabled(),
    })


@login_required
@role_required(User.Role.MAIN_ADMIN)
def webinar_create(request):
    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        scheduled_at = parse_datetime(request.POST.get("scheduled_at", "") or "")
        if not title or scheduled_at is None:
            return render(request, "dashboard/webinars/form.html", {
                "error": "يرجى إدخال العنوان وموعد صالح للبث",
                "form_data": request.POST,
            })
        webinar = Webinar.objects.create(
            title=title,
            description=request.POST.get("description", "").strip(),
            scheduled_at=scheduled_at,
            stream_url=request.POST.get("stream_url", "").strip(),
            created_by=request.user,
        )
        messages.success(request, "تم إنشاء الندوة")
        return redirect("webinars:admin_manage", pk=webinar.pk)
    return render(request, "dashboard/webinars/form.html", {})


@login_required
@role_required(User.Role.MAIN_ADMIN)
def webinar_manage(request, pk):
    """Single management surface: edit details, manage co-speakers,
    drive the lifecycle (start / end / replay)."""
    webinar = get_object_or_404(Webinar, pk=pk)

    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "start":
                webinar.start(by=request.user)
                messages.success(request, "الندوة الآن مباشرة")
            elif action == "end":
                webinar.end(by=request.user)
                messages.success(request, "تم إنهاء الندوة")
            elif action == "replay":
                webinar.enable_replay(by=request.user)
                messages.success(request, "أصبحت الندوة متاحة كإعادة")
            elif action == "update":
                webinar.title = request.POST.get("title", webinar.title).strip() or webinar.title
                webinar.description = request.POST.get("description", "").strip()
                webinar.stream_url = request.POST.get("stream_url", "").strip()
                new_dt = parse_datetime(request.POST.get("scheduled_at", "") or "")
                if new_dt is not None:
                    webinar.scheduled_at = new_dt
                webinar.save()
                messages.success(request, "تم حفظ التعديلات")
            elif action == "add_speaker":
                speaker = get_object_or_404(User, pk=request.POST.get("user_id"))
                webinar.co_speakers.add(speaker)
                messages.success(request, f"أضيف {speaker.full_name_ar} كمتحدث")
            elif action == "remove_speaker":
                webinar.co_speakers.remove(get_object_or_404(User, pk=request.POST.get("user_id")))
                messages.success(request, "أزيل المتحدث")
        except ValidationError as e:
            messages.error(request, " ".join(e.messages))
        return redirect("webinars:admin_manage", pk=pk)

    candidate_speakers = User.objects.filter(
        role__in=(User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN, User.Role.TEACHER), is_active=True,
    ).exclude(pk__in=webinar.co_speakers.values_list("pk", flat=True)).order_by("full_name_ar")

    return render(request, "dashboard/webinars/manage.html", {
        "webinar": webinar,
        "co_speakers": webinar.co_speakers.all(),
        "candidate_speakers": candidate_speakers,
        "jitsi_domain": settings.JITSI_DOMAIN,
    })

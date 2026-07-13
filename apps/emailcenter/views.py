"""Admin email center: compose a broadcast, review campaigns, audit the log,
and toggle the automatic-mail categories."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
import logging

logger = logging.getLogger(__name__)

from apps.accounts.decorators import role_required
from apps.accounts.models import User
from apps.circles.models import Circle
from apps.emailcenter import services
from apps.emailcenter.models import Audience, EmailCampaign, EmailCategory, EmailLog, GmailAccount
from apps.emailcenter import gmail as gmail_svc
from apps.usersettings.models import SystemSettings

_AUTOMAIL_KEYS = (
    "automail_enabled", "automail_approvals", "automail_reminders",
    "automail_updates", "automail_certificates",
)


@login_required
@role_required(User.Role.MAIN_ADMIN)
def email_compose(request):
    if request.method == "POST":
        subject = request.POST.get("subject", "").strip()
        body = request.POST.get("body", "").strip()
        audience = request.POST.get("audience", Audience.ALL).strip()

        errors = []
        if not subject or not body:
            errors.append("الموضوع والنص مطلوبان.")
        if audience not in Audience.values:
            errors.append("جمهور غير صالح.")

        campaign = EmailCampaign(
            subject=subject, body=body, audience=audience, created_by=request.user,
        )
        if request.POST.get("sender") == "gmail":
            gmail_account = GmailAccount.objects.filter(
                user=request.user, is_active=True
            ).first()
            if gmail_account is None:
                errors.append("لا يوجد حساب Gmail مرتبط بحسابك — اربطه من صفحة حساب المرسل.")
            campaign.sender_account = gmail_account
        if audience == Audience.ROLE:
            role = request.POST.get("audience_role", "").strip()
            if role not in User.Role.values:
                errors.append("اختر دوراً صالحاً.")
            campaign.audience_role = role
        elif audience == Audience.CIRCLE:
            circle_id = request.POST.get("audience_circle") or None
            if not circle_id:
                errors.append("اختر حلقة.")
            campaign.audience_circle_id = circle_id
        elif audience == Audience.USER:
            email = request.POST.get("audience_email", "").strip()
            target = User.objects.filter(email__iexact=email, is_active=True).first()
            if target is None:
                errors.append("لا يوجد مستخدم فعّال بهذا البريد.")
            else:
                campaign.audience_user = target

        if errors:
            for e in errors:
                messages.error(request, e)
            return render(request, "dashboard/emailcenter/compose.html",
                          _compose_context(form_data=request.POST, user=request.user))

        campaign.save()
        services.queue_campaign(campaign)
        messages.success(request, "تم جدولة الرسالة للإرسال.")
        return redirect("emailcenter:campaigns")

    return render(request, "dashboard/emailcenter/compose.html", _compose_context(user=request.user))


def _compose_context(form_data=None, user=None):
    connected_gmail = None
    if user is not None:
        connected_gmail = GmailAccount.objects.filter(user=user, is_active=True).first()
    return {
        "roles": User.Role.choices,
        "circles": Circle.objects.order_by("name").only("id", "name"),
        "audiences": Audience.choices,
        "form_data": form_data or {},
        "connected_gmail": connected_gmail,
    }


@login_required
@role_required(User.Role.MAIN_ADMIN)
def campaign_list(request):
    qs = EmailCampaign.objects.for_list()
    page_obj = Paginator(qs, 20).get_page(request.GET.get("page", 1))
    return render(request, "dashboard/emailcenter/campaigns.html", {
        "campaigns": page_obj, "page_obj": page_obj,
    })


@login_required
@role_required(User.Role.MAIN_ADMIN)
def campaign_detail(request, pk):
    campaign = get_object_or_404(EmailCampaign.objects.for_list(), pk=pk)
    logs = campaign.logs.select_related("recipient").all()
    return render(request, "dashboard/emailcenter/campaign_detail.html", {
        "campaign": campaign, "logs": logs,
    })


@login_required
@role_required(User.Role.MAIN_ADMIN)
def email_log(request):
    qs = EmailLog.objects.select_related("recipient", "campaign")
    status = request.GET.get("status", "")
    if status in EmailLog.Status.values:
        qs = qs.filter(status=status)
    category = request.GET.get("category", "")
    if category in EmailCategory.values:
        qs = qs.filter(category=category)
    page_obj = Paginator(qs, 30).get_page(request.GET.get("page", 1))
    return render(request, "dashboard/emailcenter/log.html", {
        "logs": page_obj, "page_obj": page_obj,
        "statuses": EmailLog.Status.choices, "categories": EmailCategory.choices,
    })


@login_required
@role_required(User.Role.MAIN_ADMIN)
def automail_controls(request):
    store = SystemSettings.load()
    if request.method == "POST":
        submitted = request.POST
        try:
            for key in _AUTOMAIL_KEYS:
                store.set(key, key in submitted, changed_by=request.user)
        except ValidationError as e:
            messages.error(request, "; ".join(e.messages))
        else:
            messages.success(request, "تم حفظ إعدادات البريد التلقائي.")
        return redirect("emailcenter:controls")

    toggles = [
        {"key": k, "label": _AUTOMAIL_LABELS[k], "value": store.get(k)}
        for k in _AUTOMAIL_KEYS
    ]
    return render(request, "dashboard/emailcenter/controls.html", {"toggles": toggles})


_AUTOMAIL_LABELS = {
    "automail_enabled": "تفعيل البريد التلقائي (المفتاح الرئيسي)",
    "automail_approvals": "بريد اعتماد/رفض الحسابات",
    "automail_reminders": "بريد التذكيرات",
    "automail_updates": "بريد التحديثات والإعلانات",
    "automail_certificates": "بريد الشهادات",
}


# ── Gmail sender accounts (admins + sub-admins) ─────────────────────────
# Any admin connects their own Gmail via OAuth; the email center can then
# send campaigns *as* that address (gmail.send scope, no password stored).

@login_required
@role_required(User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN)
def gmail_settings(request):
    account = GmailAccount.objects.filter(user=request.user).first()
    return render(request, "dashboard/emailcenter/gmail_settings.html", {
        "account": account,
        "oauth_enabled": gmail_svc.oauth_enabled(),
    })


@login_required
@role_required(User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN)
def gmail_connect(request):
    if not gmail_svc.oauth_enabled():
        messages.error(request, "ربط Gmail غير مهيّأ بعد — أضف GOOGLE_OAUTH_CLIENT_ID/SECRET في إعدادات الخادم")
        return redirect("emailcenter:gmail_settings")
    redirect_uri = request.build_absolute_uri(reverse("emailcenter:gmail_callback"))
    return redirect(gmail_svc.build_authorize_url(request, redirect_uri))


@login_required
@role_required(User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN)
def gmail_callback(request):
    state = request.GET.get("state", "")
    if not state or state != request.session.pop(gmail_svc.STATE_SESSION_KEY, None):
        messages.error(request, "جلسة الربط غير صالحة — أعد المحاولة")
        return redirect("emailcenter:gmail_settings")
    if request.GET.get("error"):
        messages.error(request, "أُلغي الربط من صفحة Google")
        return redirect("emailcenter:gmail_settings")
    code = request.GET.get("code", "")
    if not code:
        messages.error(request, "لم يصل رمز التفويض من Google")
        return redirect("emailcenter:gmail_settings")

    redirect_uri = request.build_absolute_uri(reverse("emailcenter:gmail_callback"))
    try:
        tokens = gmail_svc.exchange_code(code, redirect_uri)
        refresh_token = tokens.get("refresh_token", "")
        if not refresh_token:
            raise ValueError("no refresh token")
        email = gmail_svc.fetch_email(tokens["access_token"])
    except Exception:
        logger.exception("Gmail OAuth callback failed for %s", request.user.email)
        messages.error(request, "تعذر إتمام الربط مع Google — أعد المحاولة")
        return redirect("emailcenter:gmail_settings")

    from datetime import timedelta
    from django.utils import timezone as tz

    account = GmailAccount.objects.filter(user=request.user).first() or GmailAccount(user=request.user)
    account.email = email
    account.is_active = True
    account.access_token = tokens["access_token"]
    account.access_token_expires_at = tz.now() + timedelta(seconds=int(tokens.get("expires_in", 3600)))
    account.set_refresh_token(refresh_token)
    account.save()
    messages.success(request, f"تم ربط {email} — يمكن الآن الإرسال باسمه من مركز البريد")
    return redirect("emailcenter:gmail_settings")


@login_required
@role_required(User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN)
def gmail_disconnect(request):
    if request.method == "POST":
        deleted, _ = GmailAccount.objects.filter(user=request.user).delete()
        if deleted:
            messages.success(request, "تم فصل حساب Gmail")
    return redirect("emailcenter:gmail_settings")

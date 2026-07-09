"""Admin email center: compose a broadcast, review campaigns, audit the log,
and toggle the automatic-mail categories."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.decorators import role_required
from apps.accounts.models import User
from apps.circles.models import Circle
from apps.emailcenter import services
from apps.emailcenter.models import Audience, EmailCampaign, EmailCategory, EmailLog
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
                          _compose_context(form_data=request.POST))

        campaign.save()
        services.queue_campaign(campaign)
        messages.success(request, "تم جدولة الرسالة للإرسال.")
        return redirect("emailcenter:campaigns")

    return render(request, "dashboard/emailcenter/compose.html", _compose_context())


def _compose_context(form_data=None):
    return {
        "roles": User.Role.choices,
        "circles": Circle.objects.order_by("name").only("id", "name"),
        "audiences": Audience.choices,
        "form_data": form_data or {},
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

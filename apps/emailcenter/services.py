"""The one place email leaves the platform.

Both admin broadcasts and automatic mails (approval, reminders, …) go through
:func:`deliver`, so every send is gated by its category toggle and logged. No
view or app should call ``send_html_email`` directly for categorised mail.
"""
import logging

from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.utils.email import send_html_email
from apps.emailcenter.models import Audience, EmailCampaign, EmailCategory, EmailLog

logger = logging.getLogger(__name__)

# Categories whose delivery an admin can switch off. BROADCAST is a deliberate
# manual action and is intentionally absent — it always sends.
_GATED = {
    EmailCategory.APPROVAL,
    EmailCategory.REMINDER,
    EmailCategory.UPDATE,
    EmailCategory.CERTIFICATE,
}


def category_enabled(category) -> bool:
    """Whether mail of this category may be sent, per the system toggles.

    Fails soft to enabled so a settings glitch never silently swallows mail.
    """
    value = getattr(category, "value", category)
    if value not in {c.value for c in _GATED}:
        return True
    from apps.usersettings.services import get_system_setting

    try:
        if get_system_setting("automail_enabled") is False:
            return False
        return get_system_setting(f"automail_{value}") is not False
    except Exception:
        return True


def deliver(category, subject, template_name, context, recipients, *, campaign=None):
    """Send one categorised email to each recipient and log every attempt.

    ``recipients`` is an iterable of ``User`` (must have ``.email``). Returns a
    ``(sent, failed, skipped)`` tuple. When the category is disabled every
    recipient is logged ``SKIPPED`` and nothing is sent.
    """
    enabled = category_enabled(category)
    sent = failed = skipped = 0
    logs = []

    for user in recipients:
        email = getattr(user, "email", None) or (user if isinstance(user, str) else None)
        if not email:
            continue

        if not enabled:
            skipped += 1
            status = EmailLog.Status.SKIPPED
            error = "الفئة معطّلة من إعدادات النظام"
        else:
            ok = send_html_email(subject, template_name, context, [email])
            if ok:
                sent += 1
                status = EmailLog.Status.SENT
                error = ""
            else:
                failed += 1
                status = EmailLog.Status.FAILED
                error = "فشل الإرسال — راجع سجل الخادم أو إعداد Brevo"

        logs.append(EmailLog(
            campaign=campaign,
            category=getattr(category, "value", category),
            recipient=user if isinstance(user, User) else None,
            to_email=email,
            subject=subject,
            status=status,
            error=error,
        ))

    if logs:
        EmailLog.objects.bulk_create(logs)
    return sent, failed, skipped


def resolve_recipients(campaign: EmailCampaign):
    """Active, email-bearing users the campaign targets."""
    qs = User.objects.filter(is_active=True).exclude(email="")

    if campaign.audience == Audience.ROLE and campaign.audience_role:
        qs = qs.filter(role=campaign.audience_role)
    elif campaign.audience == Audience.CIRCLE and campaign.audience_circle_id:
        qs = qs.filter(
            enrollments__circle_id=campaign.audience_circle_id,
            enrollments__status="active",
        ).distinct()
    elif campaign.audience == Audience.USER and campaign.audience_user_id:
        qs = qs.filter(pk=campaign.audience_user_id)

    return qs


def send_campaign(campaign_id: int):
    """Deliver a queued campaign. Idempotent-ish: only acts on QUEUED rows."""
    campaign = (
        EmailCampaign.objects.filter(pk=campaign_id, status=EmailCampaign.Status.QUEUED)
        .first()
    )
    if campaign is None:
        return

    campaign.status = EmailCampaign.Status.SENDING
    campaign.save(update_fields=["status"])

    recipients = list(resolve_recipients(campaign))
    context = {"subject": campaign.subject, "body": campaign.body,
               "site_name": "الطبيب الحافظ"}
    sent, failed, _ = deliver(
        EmailCategory.BROADCAST, campaign.subject,
        "emails/broadcast.html", context, recipients, campaign=campaign,
    )

    campaign.total_recipients = len(recipients)
    campaign.sent_count = sent
    campaign.failed_count = failed
    campaign.sent_at = timezone.now()
    campaign.status = (
        EmailCampaign.Status.SENT if failed == 0 else EmailCampaign.Status.FAILED
    )
    campaign.save(update_fields=[
        "total_recipients", "sent_count", "failed_count", "sent_at", "status",
    ])
    return campaign


def queue_campaign(campaign: EmailCampaign):
    """Dispatch async when a Celery broker is configured, else send inline so
    the feature works in local dev without a running worker."""
    from django.conf import settings as dj_settings

    if getattr(dj_settings, "CELERY_BROKER_URL", None):
        from apps.emailcenter.tasks import send_campaign_task
        send_campaign_task.delay(campaign.id)
    else:
        send_campaign(campaign.id)

import logging
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


def send_html_email(subject, template_name, context, recipient_list, from_email=None):
    if not recipient_list:
        return False

    from_email = from_email or settings.DEFAULT_FROM_EMAIL

    html_content = render_to_string(template_name, context)
    text_content = strip_tags(html_content)

    try:
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=from_email,
            to=recipient_list,
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        return True
    except Exception as e:
        logger.exception("Failed to send email to %s: %s", recipient_list, e)
        return False


def send_verification_email(user, verification_url):
    return send_html_email(
        subject="تأكيد بريدك الإلكتروني — الطبيب الحافظ",
        template_name="emails/verification.html",
        context={
            "user": user,
            "verification_url": verification_url,
            "site_name": "الطبيب الحافظ",
        },
        recipient_list=[user.email],
    )


def _deliver_approval(user, subject, template_name, context):
    """Route account-approval mail through the email center so it is gated by
    the `automail_approvals` toggle and written to the delivery log. Imported
    lazily to avoid a circular import (emailcenter.services imports this module)."""
    from apps.emailcenter.models import EmailCategory
    from apps.emailcenter.services import deliver

    sent, _failed, _skipped = deliver(
        EmailCategory.APPROVAL, subject, template_name, context, [user]
    )
    return bool(sent)


def send_approval_email(user, login_url):
    return _deliver_approval(
        user,
        subject="تم اعتماد حسابك في منصة الطبيب الحافظ",
        template_name="emails/approval.html",
        context={
            "user": user,
            "login_url": login_url,
            "site_name": "الطبيب الحافظ",
        },
    )


def send_rejection_email(user, reason=""):
    return _deliver_approval(
        user,
        subject="بخصوص طلب انضمامك لمنصة الطبيب الحافظ",
        template_name="emails/rejection.html",
        context={
            "user": user,
            "reason": reason,
            "site_name": "الطبيب الحافظ",
        },
    )


def send_password_reset_code(email, code):
    return send_html_email(
        subject="رمز استعادة كلمة المرور — الطبيب الحافظ",
        template_name="emails/password_reset_code.html",
        context={
            "code": code,
            "site_name": "الطبيب الحافظ",
        },
        recipient_list=[email],
    )

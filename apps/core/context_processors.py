from django.conf import settings

from apps.accounts.models import User
from apps.notifications.models import Notification


def mobile_app(request):
    """Expose the student mobile APK download URL to templates. The landing
    page's install button only renders when MOBILE_APK_URL is configured."""
    return {"mobile_apk_url": getattr(settings, "MOBILE_APK_URL", "")}


def unread_messages(request):
    """Unread direct-message count for the header/sidebar chat badge."""
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        from apps.chat.services import unread_count
        return {"unread_messages": unread_count(user)}
    return {"unread_messages": 0}


def pending_count(request):
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated and user.role in (User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN):
        count = User.objects.filter(is_approved=User.ApprovalStatus.PENDING).count()
        return {"pending_count": count}
    return {"pending_count": 0}


def unread_notifications(request):
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        count = Notification.objects.filter(recipient=request.user, is_read=False).count()
        return {"unread_count": count}
    return {"unread_count": 0}


def feature_flags(request):
    """Expose optional-module toggles to templates as `features.*` so the
    sidebar can hide links for disabled modules (HAF-05). Enforcement itself
    is central in FeatureFlagMiddleware — this only affects visibility."""
    from apps.usersettings.services import feature_enabled
    return {"features": {
        "exams": feature_enabled("exams"),
        "certificates": feature_enabled("certificates"),
        "leaderboard": feature_enabled("leaderboard"),
        "webinars": feature_enabled("webinars"),
    }}

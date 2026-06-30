from apps.accounts.models import User
from apps.notifications.models import Notification


def pending_count(request):
    if request.user.is_authenticated and request.user.role in (User.Role.ADMIN, User.Role.SUPERVISOR):
        count = User.objects.filter(is_approved=User.ApprovalStatus.PENDING).count()
        return {"pending_count": count}
    return {"pending_count": 0}


def unread_notifications(request):
    if request.user.is_authenticated:
        count = Notification.objects.filter(recipient=request.user, is_read=False).count()
        return {"unread_count": count}
    return {"unread_count": 0}

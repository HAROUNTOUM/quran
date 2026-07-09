"""Who may message whom.

Central policy shared by the inbox views and the WebSocket consumer, so the
socket can never open a thread the HTTP layer would forbid.

Rules:
  - admin / supervisor may message anyone (and be messaged by anyone).
  - teacher ↔ their actively-enrolled students, and ↔ admin/supervisor.
  - student ↔ their active teachers, and ↔ admin/supervisor.
"""
from apps.accounts.models import User

STAFF_ROLES = (User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN)


def can_message(sender, recipient) -> bool:
    if sender is None or recipient is None or sender.pk == recipient.pk:
        return False
    if not recipient.is_active:
        return False

    # Staff talk to everyone; everyone talks to staff.
    if sender.role in STAFF_ROLES or recipient.role in STAFF_ROLES:
        return True

    if sender.role == User.Role.TEACHER and recipient.role == User.Role.STUDENT:
        return sender.teaches_student(recipient)
    if sender.role == User.Role.STUDENT and recipient.role == User.Role.TEACHER:
        return recipient.teaches_student(sender)

    # teacher↔teacher and student↔student are not permitted.
    return False


def messageable_users(user):
    """Queryset of users `user` is allowed to start a conversation with."""
    if user.role in STAFF_ROLES:
        return User.objects.filter(is_active=True).exclude(pk=user.pk)

    staff_ids = User.objects.filter(
        role__in=STAFF_ROLES, is_active=True
    ).values_list("id", flat=True)

    if user.role == User.Role.TEACHER:
        peer_ids = user.get_assigned_students().values_list("id", flat=True)
    elif user.role == User.Role.STUDENT:
        peer_ids = user.get_assigned_teachers().values_list("id", flat=True)
    else:
        return User.objects.none()

    # Union the ids first (both are lazy value lists), then one clean query —
    # avoids combining a .distinct() queryset with a plain one.
    allowed = set(staff_ids) | set(peer_ids)
    allowed.discard(user.pk)
    return User.objects.filter(id__in=allowed, is_active=True)

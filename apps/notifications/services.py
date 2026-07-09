"""Single write path for notifications (HAF-04).

Every notification the platform sends is created through ``notify()``. This is
the one place notification-type validation, per-user channel preferences, and
future fan-out (email digest, etc.) are enforced. Never call
``Notification.objects.create()`` directly from views or services.

WebSocket delivery is handled automatically by the ``post_save`` signal on
``Notification`` (see ``apps.notifications.signals``); this service only needs
to create the row.
"""
from apps.notifications.models import Notification

_VALID_TYPES = set(Notification.Type.values)


def notify(recipient, type, title, message="", link=""):
    """Create an in-app notification for ``recipient``.

    ``type`` must be a valid ``Notification.Type`` (value or enum member) — an
    unknown type raises ``ValueError`` so dead/typo'd types fail loudly instead
    of silently storing garbage (the previous ``.create()`` sprawl allowed
    invalid strings like ``"progress_update"`` that no template renders).

    Respects a student recipient's ``notify_channel_inapp`` preference; any
    lookup failure fails soft (the notification is still created).
    """
    if recipient is None:
        return None

    type_value = getattr(type, "value", type)
    if type_value not in _VALID_TYPES:
        raise ValueError(f"Unknown notification type: {type_value!r}")

    if getattr(recipient, "role", None) == "student":
        try:
            from apps.usersettings.services import get_user_setting
            if get_user_setting(recipient, "notify_channel_inapp") is False:
                return None
        except Exception:
            pass  # fail soft — never drop a notification on a settings error

    return Notification.objects.create(
        recipient=recipient,
        type=type_value,
        title=title,
        message=message or "",
        link=link or "",
    )

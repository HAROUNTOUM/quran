"""Jitsi JWT minting for the self-hosted deployment.

When JITSI_APP_SECRET is configured, every embed is authorised with a short-lived
per-user token so the Jitsi server (prosody token auth) refuses anyone who did not
pass our Django permission checks — closing the "open room name" hole of the public
meet.jit.si server. When the secret is unset (dev), no token is minted and the embed
falls back to the public server unchanged.
"""
import time

from django.conf import settings

from apps.accounts.models import User

try:
    import jwt
except ImportError:  # pragma: no cover
    jwt = None


def jitsi_auth_enabled():
    return bool(getattr(settings, "JITSI_APP_SECRET", "")) and jwt is not None


def mint_jitsi_jwt(user, room_name, moderator=False):
    """Return a signed Jitsi JWT for `user` scoped to `room_name`, or None when
    JWT auth is not configured (dev/public-server fallback)."""
    if not jitsi_auth_enabled():
        return None

    now = int(time.time())
    ttl = int(getattr(settings, "JITSI_JWT_TTL", 7200))
    app_id = getattr(settings, "JITSI_APP_ID", "hafez")

    payload = {
        "iss": app_id,
        "aud": "jitsi",
        "sub": getattr(settings, "JITSI_DOMAIN", "meet.jit.si"),
        "room": room_name,
        "iat": now,
        "nbf": now - 5,
        "exp": now + ttl,
        "context": {
            "user": {
                "id": str(user.pk),
                "name": user.full_name_ar or user.get_username(),
                "moderator": "true" if moderator else "false",
            },
        },
    }
    return jwt.encode(
        payload, settings.JITSI_APP_SECRET, algorithm="HS256",
        headers={"kid": app_id},
    )


def is_moderator(user):
    """Teachers/admins/supervisors moderate; students are participants."""
    return getattr(user, "role", None) in (User.Role.TEACHER, User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN)

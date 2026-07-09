"""Read helpers used across apps (middleware, request models, reports).

Fails soft: before the app is migrated (or in edge deploy states) callers
get registry defaults instead of a crash.
"""
from apps.usersettings import registry


def get_system_setting(key):
    spec = registry.get_spec(key)
    try:
        from apps.usersettings.models import SystemSettings
        store = SystemSettings.objects.filter(pk=1).only("data").first()
    except Exception:
        return spec.default
    if store is None:
        return spec.default
    return store.data.get(key, spec.default)


def feature_enabled(feature: str) -> bool:
    """Whether an optional module is on. `feature` is the short name
    (exams | certificates | leaderboard | webinars); maps to the
    `feature_<name>_enabled` system setting. Fails soft to enabled-by-default."""
    return bool(get_system_setting(f"feature_{feature}_enabled"))


def get_user_setting(user, key):
    """Effective value of a user-scope setting for `user` (default if unset
    or the user has no settings row yet)."""
    spec = registry.get_spec(key)
    us = getattr(user, "settings", None)
    if us is None:
        return spec.default
    return us.data.get(key, spec.default)

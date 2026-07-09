"""Batch (دفعة) scoping — the single source of truth for what a Sub Admin
may see. Every admin-panel queryset that can contain cross-batch data must
pass through one of these helpers.

Policy:
- MAIN_ADMIN sees everything (queryset returned unchanged).
- SUB_ADMIN sees only rows belonging to their managed batch.
- SUB_ADMIN with no managed batch sees nothing (qs.none()), never an error.
- Pending signups are the one exception: they have batch=NULL until approval,
  so `scoped_pending_users` keeps them visible to sub-admins (who assign
  their own batch on approval).
"""

from django.db.models import Q

from .models import User


def scoped_batch(user):
    """The batch this Sub Admin manages. Deterministic: prefers the active
    batch, then the newest — a sub-admin listed on several batches always
    resolves to the same one."""
    if user.role != User.Role.SUB_ADMIN:
        return None
    return (
        user.managed_batch
        .order_by("status", "-created_at")  # "active" < "archived"/"inactive"
        .first()
    )


def _scope(user, qs, batch_filter):
    """MAIN_ADMIN → unchanged; SUB_ADMIN → filtered by batch; no batch → none."""
    if user.role == User.Role.MAIN_ADMIN:
        return qs
    batch = scoped_batch(user)
    if batch is None:
        return qs.none()
    return qs.filter(**{batch_filter: batch})


def scoped_users(user, qs):
    return _scope(user, qs, "batch")


def scoped_pending_users(user, qs):
    """Pending signups have no batch yet — sub-admins must still see them
    (plus any pending user already placed in their batch)."""
    if user.role == User.Role.MAIN_ADMIN:
        return qs
    batch = scoped_batch(user)
    if batch is None:
        return qs.none()
    return qs.filter(Q(batch__isnull=True) | Q(batch=batch))


def scoped_circles(user, qs):
    return _scope(user, qs, "batch")


def scoped_sessions(user, qs):
    return _scope(user, qs, "circle__batch")


def scoped_exams(user, qs):
    return _scope(user, qs, "circle__batch")


def scoped_requests(user, qs):
    return _scope(user, qs, "submitted_by__batch")


def scoped_attendance(user, qs):
    return _scope(user, qs, "student__batch")

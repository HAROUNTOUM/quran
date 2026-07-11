"""Batch (دفعة) scoping — the single source of truth for what a Sub Admin
may see. Every admin-panel queryset that can contain cross-batch data must
pass through one of these helpers.

Policy:
- MAIN_ADMIN sees everything (queryset returned unchanged).
- SUB_ADMIN sees rows belonging to any batch they supervise.
- SUB_ADMIN with no managed batches sees nothing (qs.none()), never an error.
- Pending signups are the one exception: they have batch=NULL until approval,
  so `scoped_pending_users` keeps them visible to sub-admins (who assign
  their own batch on approval).
"""

from django.core.exceptions import PermissionDenied
from django.db.models import Q

from .models import Batch, User


def scoped_batches(user):
    """All batches a Sub Admin supervises.

    Supports both the legacy single `sub_admin` field and the newer
    multi-supervisor `sub_admins` relation during the transition.
    """
    if user.role != User.Role.SUB_ADMIN:
        return Batch.objects.none()
    return Batch.objects.filter(
        Q(sub_admin=user) | Q(sub_admins=user)
    ).distinct().order_by("status", "-created_at")


def scoped_batch(user):
    """Primary batch for legacy callers. Deterministic: prefers active, newest."""
    return scoped_batches(user).first()


def scoped_batch_ids(user):
    if user.role == User.Role.MAIN_ADMIN:
        return None
    return list(
        scoped_batches(user).values_list("pk", flat=True)
    )


def check_batch_access(user, batch_id):
    """Object-level guard for detail/edit views: MAIN_ADMIN always passes;
    a SUB_ADMIN must supervise the row's batch. A sub-admin with zero
    supervised batches is always denied (never fail-open), and rows without
    a batch are not theirs to touch."""
    ids = scoped_batch_ids(user)
    if ids is None:
        return
    if batch_id is None or batch_id not in ids:
        raise PermissionDenied


def _scope(user, qs, batch_filter):
    """MAIN_ADMIN → unchanged; SUB_ADMIN → filtered by supervised batches."""
    if user.role == User.Role.MAIN_ADMIN:
        return qs
    batch_ids = scoped_batch_ids(user)
    if not batch_ids:
        return qs.none()
    return qs.filter(**{f"{batch_filter}__in": batch_ids})


def scoped_users(user, qs):
    return _scope(user, qs, "batch")


def scoped_pending_users(user, qs):
    """Pending signups have no batch yet — sub-admins must still see them
    (plus any pending user already placed in their batch)."""
    if user.role == User.Role.MAIN_ADMIN:
        return qs
    batch_ids = scoped_batch_ids(user)
    if not batch_ids:
        return qs.none()
    return qs.filter(Q(batch__isnull=True) | Q(batch_id__in=batch_ids))


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

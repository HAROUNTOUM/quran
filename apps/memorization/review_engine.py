"""Spaced-repetition scheduling for Quran memorization (Rub-level).

The schedule is computed from an evaluation of a recitation. Rather than a fixed
interval ladder, the next interval is derived by a multiplier on the current
interval, so a student who consistently recites well spaces reviews out quickly,
while mistakes pull the interval back to the start.

The two scalar knobs (first interval, max cap) and the weak-section thresholds are
read from the settings registry; the per-evaluation multipliers below encode the
pedagogical algorithm itself and are engine constants.
"""
from datetime import timedelta

from django.utils import timezone

# Evaluation → interval behavior. Multiplier is applied to the current interval;
# `reset` sends the rub back to the first interval (re-learn).
EVALUATION_MULTIPLIERS = {
    "ممتاز": 2.5,
    "جيد جداً": 2.0,
    "جيد": 1.5,
    "مقبول": 1.0,      # hold
    "ضعيف": None,      # reset
    "راسب": None,      # reset
}

# Evaluations at or below this weaken the rub's status.
WEAKENING_EVALUATIONS = {"ضعيف", "راسب"}


def _setting(key, fallback):
    try:
        from apps.usersettings.services import get_system_setting
        val = get_system_setting(key)
        return int(val) if val is not None else fallback
    except Exception:  # noqa: BLE001 — fail soft to sane defaults
        return fallback


def first_interval_days():
    return _setting("srs_first_interval_days", 1)


def max_interval_days():
    return _setting("srs_max_interval_days", 365)


def calculate_next_interval(current_interval, evaluation, mistakes_count=0):
    """Return the next review interval in days.

    current_interval: the interval that was just completed (0 for a first memorize).
    evaluation: one of EVALUATION_MULTIPLIERS keys.
    """
    first = first_interval_days()
    cap = max_interval_days()

    multiplier = EVALUATION_MULTIPLIERS.get(evaluation)
    if multiplier is None:
        return first  # reset / re-learn

    base = current_interval if current_interval and current_interval > 0 else first
    nxt = int(round(base * multiplier))
    if nxt < first:
        nxt = first
    return min(nxt, cap)


def next_review_date(from_date, interval_days):
    return from_date + timedelta(days=interval_days)


def status_after_evaluation(evaluation, current_status):
    """Derive the new MemorizationRecord status from an evaluation."""
    # Imported lazily to avoid a cycle at module import time.
    from .models import MemorizationRecord as MR

    if evaluation in WEAKENING_EVALUATIONS:
        return MR.Status.WEAK
    if evaluation == "مقبول":
        return MR.Status.NEEDS_REVIEW
    # good / very good / excellent
    if current_status in (MR.Status.NOT_MEMORIZED, MR.Status.IN_PROGRESS):
        return MR.Status.MEMORIZED
    if evaluation == "ممتاز" and current_status == MR.Status.MEMORIZED:
        return MR.Status.MASTERED
    return MR.Status.MEMORIZED


def get_weak_sections(student):
    """MemorizationRecord queryset for a student that needs attention:
    explicitly WEAK, or overdue beyond the configured window."""
    from .models import MemorizationRecord as MR

    overdue_days = _setting("srs_weak_overdue_days", 7)
    cutoff = timezone.localdate() - timedelta(days=overdue_days)
    from django.db.models import Q
    return (
        MR.objects.filter(student=student)
        .filter(Q(status=MR.Status.WEAK)
                | Q(next_review_date__isnull=False, next_review_date__lt=cutoff))
        .select_related("rub__hizb__juz")
        .order_by("next_review_date")
    )

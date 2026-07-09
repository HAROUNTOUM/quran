"""Memorization views. Student hifdh progress + completion estimator."""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.accounts.decorators import role_required
from apps.accounts.models import User
from apps.references.models import Ayah

from .models import MemorizationRecord

TOTAL_AYAHS = 6236
TOTAL_PAGES = 604
TOTAL_RUBS = 240


def _estimator_context(user):
    """Remaining ayahs/pages/rubs for the completion estimator. Shared by the
    progress page (merged tab) and the standalone estimator URL."""
    memorized_rubs = list(
        MemorizationRecord.objects.memorized(user)
        .values_list("rub__number", flat=True)
    )
    memorized_ayahs = (
        Ayah.objects.filter(rub__number__in=memorized_rubs).count()
        if memorized_rubs else 0
    )
    memorized_pages = (
        Ayah.objects.filter(rub__number__in=memorized_rubs)
        .values("page").distinct().count()
        if memorized_rubs else 0
    )
    return {
        "remaining_ayahs": TOTAL_AYAHS - memorized_ayahs,
        "remaining_pages": TOTAL_PAGES - memorized_pages,
        "remaining_rubs": TOTAL_RUBS - len(memorized_rubs),
    }


@login_required
@role_required(User.Role.STUDENT)
def student_progress(request):
    """Student's memorization progress page — includes the merged completion
    estimator (حاسبة الختم) as an in-page section."""
    from apps.references.utils import format_hizb_thumn
    memorized_rubs = MemorizationRecord.objects.memorized(request.user).select_related("rub")
    memorized_total = memorized_rubs.count()
    return render(request, "dashboard/memorization/student_progress.html", {
        "memorized_rubs": memorized_rubs,
        "memorized_total": memorized_total,
        # Tracking unit: 1 rub = 2 athman.
        "memorized_thumns": memorized_total * 2,
        "memorized_units": format_hizb_thumn(memorized_total * 2),
        **_estimator_context(request.user),
    })


@login_required
@role_required(User.Role.STUDENT)
def completion_estimator(request):
    """Reactive estimator: how long to finish the Quran at a chosen daily pace.
    The view supplies the student's actual remaining totals; the arithmetic is
    done client-side (no page reload)."""
    return render(request, "dashboard/memorization/estimator.html",
                  _estimator_context(request.user))

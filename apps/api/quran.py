"""Read-only Quran reference API for the QuranSelector component.

All structural data is immutable after seeding, so list endpoints are cached.
The per-student status endpoint (rub → memorization status) is wired in Phase 3;
until MemorizationRecord exists it returns an empty map and the selector renders
every rub as NOT_MEMORIZED (graceful degradation).
"""
from django.core.cache import cache
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.references.models import Ayah, Hizb, Juz, Rub, Surah, Thumn

from .utils import api_response

_CACHE_TTL = 60 * 60 * 24  # 24h; data is static


class JuzListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        data = cache.get("quran:juz")
        if data is None:
            data = [
                {
                    "number": j.number,
                    "hizbs": list(
                        j.hizbs.order_by("number").values_list("number", flat=True)
                    ),
                }
                for j in Juz.objects.prefetch_related("hizbs").order_by("number")
            ]
            cache.set("quran:juz", data, _CACHE_TTL)
        return api_response(data=data)


class HizbListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Hizb.objects.order_by("number")
        juz = request.query_params.get("juz")
        if juz:
            qs = qs.filter(juz__number=juz)
        data = [
            {"number": h.number, "juz": h.juz_id, "number_in_juz": h.number_in_juz}
            for h in qs
        ]
        return api_response(data=data)


class RubListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Rub.objects.select_related("hizb").order_by("number")
        juz = request.query_params.get("juz")
        hizb = request.query_params.get("hizb")
        if hizb:
            qs = qs.filter(hizb__number=hizb)
        elif juz:
            qs = qs.filter(hizb__juz__number=juz)
        # Precompute first-ayah page per rub in one query
        data = []
        for rub in qs.prefetch_related("ayahs__surah"):
            first, last = rub.ayah_bounds()
            data.append({
                "number": rub.number,
                "hizb": rub.hizb.number,
                "number_in_hizb": rub.number_in_hizb,
                "label": rub.label(),
                "page": first.page if first else None,
                "first": first.verse_key if first else None,
                "last": last.verse_key if last else None,
            })
        return api_response(data=data)


class ThumnListView(APIView):
    """Warsh thumn boundaries (480 eighths). Finer-grained selection unit than
    Rub; each rub = thumns 2n-1 and 2n, so selector UIs can offer either."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Thumn.objects.select_related("rub__hizb", "start_surah").order_by("number")
        juz = request.query_params.get("juz")
        hizb = request.query_params.get("hizb")
        rub = request.query_params.get("rub")
        if rub:
            qs = qs.filter(rub__number=rub)
        elif hizb:
            qs = qs.filter(rub__hizb__number=hizb)
        elif juz:
            qs = qs.filter(rub__hizb__juz__number=juz)
        data = [
            {
                "number": t.number,
                "rub": t.rub.number,
                "hizb": t.rub.hizb.number,
                "number_in_hizb": t.number_in_hizb,
                "label": t.label(),
                "page": t.page,
                "start": f"{t.start_surah_id}:{t.start_ayah_number}",
                "start_surah_name": t.start_surah.name_ar,
                "ayah_id_global": t.ayah_id_global,
            }
            for t in qs
        ]
        return api_response(data=data)


class QuranSurahListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        data = cache.get("quran:surahs")
        if data is None:
            data = [
                {
                    "id": s.id,
                    "name_ar": s.name_ar,
                    "name_en": s.name_en,
                    "ayah_count": s.ayah_count,
                    "revelation_type": s.revelation_type,
                }
                for s in Surah.objects.order_by("id")
            ]
            cache.set("quran:surahs", data, _CACHE_TTL)
        return api_response(data=data)


class AyahListView(APIView):
    """Ayahs filtered by surah, page, or rub — used for the passage view and
    the by-page / by-surah selector modes."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        surah = request.query_params.get("surah")
        page = request.query_params.get("page")
        rub = request.query_params.get("rub")
        if not (surah or page or rub):
            return api_response(
                message="حدد surah أو page أو rub", success=False, status=400
            )
        qs = Ayah.objects.select_related("surah").order_by("surah_id", "number_in_surah")
        if surah:
            qs = qs.filter(surah_id=surah)
        if page:
            qs = qs.filter(page=page)
        if rub:
            qs = qs.filter(rub__number=rub)
        data = [
            {
                "verse_key": a.verse_key,
                "surah": a.surah_id,
                "surah_name": a.surah.name_ar,
                "ayah": a.number_in_surah,
                "page": a.page,
                "sajdah": a.sajdah,
                "text": a.text_uthmani,
            }
            for a in qs[:500]
        ]
        return api_response(data=data)


class StudentRubStatusView(APIView):
    """Map of rub number → memorization status for the requesting student,
    consumed by the selector to colour each rub. Filled in Phase 3."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        status_map = {}
        try:
            from apps.memorization.models import MemorizationRecord
        except ImportError:
            MemorizationRecord = None
        if MemorizationRecord is not None:
            student_id = request.query_params.get("student") or request.user.id
            # Teachers/admins may inspect a student; students only themselves
            if request.user.role == "student":
                student_id = request.user.id
            rows = MemorizationRecord.objects.filter(
                student_id=student_id
            ).values_list("rub__number", "status")
            status_map = {num: st for num, st in rows}
        return api_response(data=status_map)

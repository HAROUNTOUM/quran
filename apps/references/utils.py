import re
from bisect import bisect_right

from django.core.exceptions import ValidationError

from .models import Juz

# ─── Arabic text normalization (for diacritic-insensitive search) ──────────────
# Strip harakat / tanwin / superscript alef / small marks, tatweel, then fold
# alef & hamza-carrier variants to a canonical form.
_DIACRITICS = re.compile(
    "[ؐ-ًؚ-ٰٟۖ-ۜ۟-۪ۨ-ۭ]"
)
_TATWEEL = "ـ"


def normalize_arabic(text):
    """Return a diacritic-free, folded form of `text` for search indexing/matching."""
    if not text:
        return ""
    text = _DIACRITICS.sub("", text)
    text = text.replace(_TATWEEL, "")
    # Fold alef/hamza carriers
    for src, dst in (("أإآٱ", "ا"), ("ى", "ي"), ("ؤ", "و"), ("ئ", "ي"), ("ة", "ه")):
        for ch in src:
            text = text.replace(ch, dst)
    return re.sub(r"\s+", " ", text).strip()


# ─── Quran hierarchy helpers ───────────────────────────────────────────────────


def validate_ayah_range(surah, ayah_from, ayah_to):
    """Validate an ayah range against the surah's real ayah_count.
    `surah` may be a Surah instance or its pk. Raises ValidationError on failure.
    Returns (ayah_from, ayah_to) as ints on success."""
    from .models import Surah

    if not isinstance(surah, Surah):
        try:
            surah = Surah.objects.get(pk=surah)
        except Surah.DoesNotExist:
            raise ValidationError("السورة غير موجودة")
    try:
        a_from = int(ayah_from)
        a_to = int(ayah_to)
    except (TypeError, ValueError):
        raise ValidationError("أرقام الآيات غير صحيحة")
    if a_from < 1 or a_to < 1:
        raise ValidationError("رقم الآية يجب أن يكون 1 أو أكثر")
    if a_from > a_to:
        raise ValidationError("آية البداية يجب أن تكون قبل آية النهاية")
    if a_to > surah.ayah_count:
        raise ValidationError(
            f"سورة {surah.name_ar} تحتوي على {surah.ayah_count} آية فقط"
        )
    return a_from, a_to


def rubs_in(container):
    """Return the Rub queryset contained in a Juz or Hizb instance."""
    from .models import Hizb, Rub

    if isinstance(container, Juz):
        return Rub.objects.filter(hizb__juz=container).order_by("number")
    if isinstance(container, Hizb):
        return container.rubs.order_by("number")
    raise TypeError("container must be a Juz or Hizb instance")


def ayahs_on_page(page):
    from .models import Ayah

    return Ayah.objects.filter(page=page).select_related("surah").order_by(
        "surah_id", "number_in_surah"
    )



def seed_juz_data():
    if Juz.objects.count() >= 30:
        return
    from .management.commands.seed_references import JUZ_AYAH_COUNTS
    for i, count in enumerate(JUZ_AYAH_COUNTS, start=1):
        Juz.objects.get_or_create(number=i, defaults={"ayah_count": count})


# ─── Thumn/Hizb progress units ─────────────────────────────────────────────
# The platform's tracking unit is the thumn (ثمن الحزب, 1/8 hizb) and the hizb.
# Conversions resolve against the real Warsh thumn boundaries in the Thumn
# table (480 rows) — never against ayah-count arithmetic. Reports still show
# the ayah range (from surah/ayah to surah/ayah) alongside these units.

THUMNS_PER_HIZB = 8
TOTAL_THUMNS = 480
TOTAL_HIZBS = 60
# Fallback only, for databases without seeded thumn boundaries (unit tests):
# 6236 ayahs / 480 athman ≈ 13 ayahs per thumn.
_AYAHS_PER_THUMN_ESTIMATE = 6236 / 480


def thumn_start_keys():
    """[(start_surah_id, start_ayah_number), ...] ordered by thumn number
    (index i holds thumn i+1). Empty when the Thumn table is unseeded.
    Fetch once and pass to count_thumns(_keys=...) in per-student loops."""
    from .models import Thumn

    return list(
        Thumn.objects.order_by("number").values_list(
            "start_surah_id", "start_ayah_number"
        )
    )


_thumn_start_keys = thumn_start_keys


def thumn_span(surah_id, ayah_from, ayah_to, _keys=None):
    """(first, last) 1-based thumn numbers covered by a single-surah ayah
    range, resolved against real thumn boundaries. None when unseeded."""
    keys = _thumn_start_keys() if _keys is None else _keys
    if not keys:
        return None
    first = bisect_right(keys, (surah_id, ayah_from)) or 1
    last = bisect_right(keys, (surah_id, ayah_to)) or 1
    return first, last


def covered_thumns(ranges, _keys=None):
    """Set of distinct thumn numbers covered by an iterable of
    (surah_id, ayah_from, ayah_to) ranges. Empty set when unseeded."""
    keys = thumn_start_keys() if _keys is None else _keys
    covered = set()
    if not keys:
        return covered
    for surah_id, a_from, a_to in ranges:
        first, last = thumn_span(surah_id, a_from, a_to, _keys=keys)
        covered.update(range(first, last + 1))
    return covered


def count_thumns(ranges, _keys=None):
    """Exact number of distinct athman covered by an iterable of
    (surah_id, ayah_from, ayah_to) ranges — overlapping ranges count once.
    Falls back to an ayah-count estimate when the Thumn table is unseeded.
    Batch callers pass `_keys=thumn_start_keys()` to avoid a query per call."""
    ranges = [r for r in ranges if r[0]]
    if not ranges:
        return 0
    keys = thumn_start_keys() if _keys is None else _keys
    if not keys:
        total_ayahs = sum(a_to - a_from + 1 for _sid, a_from, a_to in ranges)
        return round(total_ayahs / _AYAHS_PER_THUMN_ESTIMATE)
    return len(covered_thumns(ranges, _keys=keys))


def thumns_to_hizb(thumn_count):
    """(full ahzab, remaining athman). 8 athman per hizb."""
    return thumn_count // THUMNS_PER_HIZB, thumn_count % THUMNS_PER_HIZB


def format_hizb_thumn(thumn_count):
    """Human label like '3 أحزاب و 5 أثمان' from a thumn count."""
    hizb, rem = thumns_to_hizb(thumn_count)
    parts = []
    if hizb:
        parts.append(f"{hizb} " + ("حزب" if hizb <= 2 or hizb > 10 else "أحزاب"))
    if rem:
        parts.append(f"{rem} " + ("ثمن" if rem <= 2 else "أثمان"))
    return " و".join(parts) if parts else "0"


def ayah_range_bounds(ranges):
    """Overall mushaf span of an iterable of (surah_id, ayah_from, ayah_to)
    ranges: ((first_surah_id, first_ayah), (last_surah_id, last_ayah)) or None."""
    ranges = [r for r in ranges if r[0]]
    if not ranges:
        return None
    start = min((sid, a_from) for sid, a_from, _ in ranges)
    end = max((sid, a_to) for sid, _, a_to in ranges)
    return start, end

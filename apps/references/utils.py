from .models import Juz


def seed_juz_data():
    if Juz.objects.count() >= 30:
        return
    from .management.commands.seed_references import JUZ_AYAH_COUNTS
    for i, count in enumerate(JUZ_AYAH_COUNTS, start=1):
        Juz.objects.get_or_create(number=i, defaults={"ayah_count": count})


def ayahs_to_juz_quarters(total_ayahs):
    if total_ayahs <= 0:
        return 0, 0

    juz_list = list(Juz.objects.all().order_by("number"))
    if not juz_list:
        return 0, 0

    remaining = total_ayahs
    full_juz = 0

    for juz in juz_list:
        if remaining >= juz.ayah_count:
            full_juz += 1
            remaining -= juz.ayah_count
        else:
            break

    current_juz = juz_list[full_juz] if full_juz < len(juz_list) else juz_list[-1]
    quarter_size = current_juz.ayah_count / 8
    quarters = int(remaining / quarter_size) if quarter_size > 0 else 0

    return full_juz, quarters


def format_juz_quarters(total_ayahs):
    juz_count, quarter_count = ayahs_to_juz_quarters(total_ayahs)
    if juz_count == 0 and quarter_count == 0:
        return "0"
    parts = []
    if juz_count > 0:
        parts.append(f"{juz_count} أحزاب")
    if quarter_count > 0:
        parts.append(f"{quarter_count} أرباع")
    return " و ".join(parts) if parts else "0"


# ─── Hizb / Quarter conversion ────────────────
# 1 Juz = 8 quarters (1/8 juz)
# 1 Hizb = 4 quarters = 1/2 Juz


def ayahs_to_hizb_quarters(total_ayahs):
    if total_ayahs <= 0:
        return 0, 0

    juz_list = list(Juz.objects.all().order_by("number"))
    if not juz_list:
        return 0, 0

    remaining = total_ayahs
    total_quarters = 0

    for juz in juz_list:
        if remaining >= juz.ayah_count:
            total_quarters += 8
            remaining -= juz.ayah_count
        else:
            quarter_size = juz.ayah_count / 8
            total_quarters += int(remaining / quarter_size) if quarter_size > 0 else 0
            remaining = 0
            break

    hizbs = total_quarters // 4
    quarters = total_quarters % 4
    return hizbs, quarters


def format_hizb_quarters(total_ayahs):
    hizb_count, quarter_count = ayahs_to_hizb_quarters(total_ayahs)
    if hizb_count == 0 and quarter_count == 0:
        return "0"
    parts = []
    if hizb_count > 0:
        parts.append(f"{hizb_count} أحزاب")
    if quarter_count > 0:
        parts.append(f"{quarter_count} أرباع")
    return " و ".join(parts) if parts else "0"

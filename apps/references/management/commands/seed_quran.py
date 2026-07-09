"""Seed the full Quran reference hierarchy (Juz → Hizb → Rub → Ayah) and Surahs
from the validated static dataset in apps/references/data/quran_seed.json.

Idempotent: structural rows (Juz/Hizb/Rub) are upserted by their stable number so
existing foreign keys (e.g. memorization records → Rub) survive a re-seed. Ayahs
carry no inbound FKs and are fully rebuilt.

Source of the dataset: Quran.com API v4 (Tanzil/QUL metadata), fetched and validated
against the invariants 114 surahs / 6236 ayahs / 30 juz / 60 hizb / 240 rub /
pages 1–604. See docs/improvement-plan.md Phase 1.
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.references.models import Ayah, Hizb, Juz, Rub, Surah
from apps.references.utils import normalize_arabic

DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "quran_seed.json"

# Ayah row layout: [surah, ayah, juz, hizb, rub, page, sajdah, text_uthmani]
S, A, J, H, R, P, SJ, T = range(8)


class Command(BaseCommand):
    help = "Seed Quran hierarchy (Juz/Hizb/Rub/Ayah) + Surahs from static dataset"

    def add_arguments(self, parser):
        parser.add_argument(
            "--file", default=str(DATA_FILE),
            help="Path to the quran_seed.json dataset",
        )

    def handle(self, *args, **opts):
        path = Path(opts["file"])
        if not path.exists():
            raise CommandError(f"Dataset not found: {path}")

        payload = json.loads(path.read_text(encoding="utf-8"))
        surahs = payload["surahs"]
        rows = payload["ayahs"]

        # ---- Validate invariants before writing anything ----
        if len(surahs) != 114:
            raise CommandError(f"expected 114 surahs, got {len(surahs)}")
        if len(rows) != 6236:
            raise CommandError(f"expected 6236 ayahs, got {len(rows)}")
        juz_nums = {r[J] for r in rows}
        hizb_nums = {r[H] for r in rows}
        rub_nums = {r[R] for r in rows}
        pages = {r[P] for r in rows}
        if juz_nums != set(range(1, 31)):
            raise CommandError("juz numbers are not 1..30")
        if hizb_nums != set(range(1, 61)):
            raise CommandError("hizb numbers are not 1..60")
        if rub_nums != set(range(1, 241)):
            raise CommandError("rub numbers are not 1..240")
        if min(pages) != 1 or max(pages) != 604:
            raise CommandError(f"pages must span 1..604, got {min(pages)}..{max(pages)}")

        # ---- Derive parentage from the data (rub→hizb, hizb→juz) ----
        rub_to_hizb, hizb_to_juz, juz_ayah_count = {}, {}, {}
        for r in rows:
            rub_to_hizb.setdefault(r[R], r[H])
            hizb_to_juz.setdefault(r[H], r[J])
            juz_ayah_count[r[J]] = juz_ayah_count.get(r[J], 0) + 1
        for rub, hz in rub_to_hizb.items():
            if not (1 <= rub <= 240) or not (1 <= hz <= 60):
                raise CommandError(f"invalid rub→hizb mapping {rub}->{hz}")

        # number_in_juz per hizb, number_in_hizb per rub (rank within parent)
        hizb_pos = {}
        for juz in range(1, 31):
            for i, hz in enumerate(sorted(h for h, j in hizb_to_juz.items() if j == juz), 1):
                hizb_pos[hz] = i
        rub_pos = {}
        for hz in range(1, 61):
            for i, rub in enumerate(sorted(r for r, h in rub_to_hizb.items() if h == hz), 1):
                rub_pos[rub] = i

        with transaction.atomic():
            # Surahs
            for s in surahs:
                Surah.objects.update_or_create(
                    id=s["id"],
                    defaults={
                        "name_ar": s["name_ar"],
                        "name_en": s["name_en"],
                        "ayah_count": s["ayah_count"],
                        "revelation_type": s["revelation_type"],
                    },
                )

            # Juz (keep existing ayah_count field populated)
            juz_by_num = {}
            for num in range(1, 31):
                juz, _ = Juz.objects.update_or_create(
                    number=num, defaults={"ayah_count": juz_ayah_count[num]},
                )
                juz_by_num[num] = juz

            # Hizb
            hizb_by_num = {}
            for num in range(1, 61):
                hizb, _ = Hizb.objects.update_or_create(
                    number=num,
                    defaults={
                        "juz": juz_by_num[hizb_to_juz[num]],
                        "number_in_juz": hizb_pos[num],
                    },
                )
                hizb_by_num[num] = hizb

            # Rub
            rub_by_num = {}
            for num in range(1, 241):
                rub, _ = Rub.objects.update_or_create(
                    number=num,
                    defaults={
                        "hizb": hizb_by_num[rub_to_hizb[num]],
                        "number_in_hizb": rub_pos[num],
                    },
                )
                rub_by_num[num] = rub

            # Ayahs — rebuild wholesale (no inbound FKs)
            Ayah.objects.all().delete()
            batch = []
            for r in rows:
                batch.append(Ayah(
                    surah_id=r[S],
                    number_in_surah=r[A],
                    rub=rub_by_num[r[R]],
                    page=r[P],
                    text_uthmani=r[T],
                    text_normalized=normalize_arabic(r[T]),
                    sajdah=bool(r[SJ]),
                ))
            Ayah.objects.bulk_create(batch, batch_size=1000)

        self.stdout.write(self.style.SUCCESS(
            f"Seeded {Surah.objects.count()} surahs, {Juz.objects.count()} juz, "
            f"{Hizb.objects.count()} hizb, {Rub.objects.count()} rub, "
            f"{Ayah.objects.count()} ayahs."
        ))

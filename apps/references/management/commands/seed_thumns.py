"""Seed the 480 thumn (ثُمن الحزب) boundaries from the validated Warsh dataset
in apps/references/data/thumn_index_warsh.json.

The file stores only the irreducible columns per thumn —
[page, surah_no, ayah_no, ayah_id_global_warsh] — the structural position is
derived here and validated: hizb = ceil(n/8), thumn_in_hizb = ((n-1) % 8) + 1,
rub = ceil(n/2) (each rub' = 2 thumns).

Idempotent: rows are upserted by their stable `number`, so any future inbound
FKs survive a re-seed. Requires seed_quran to have run first (needs Rub/Surah).
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.references.models import Rub, Surah, Thumn

DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "thumn_index_warsh.json"

# Row layout: [page, surah_no, ayah_no, ayah_id_global_warsh]
PAGE, SURAH, AYAH, GLOBAL_ID = range(4)


class Command(BaseCommand):
    help = "Seed the 480 Warsh thumn boundaries (idempotent upsert by number)."

    @transaction.atomic
    def handle(self, *args, **options):
        if not DATA_FILE.exists():
            raise CommandError(f"dataset missing: {DATA_FILE}")
        rows = json.loads(DATA_FILE.read_text())["rows"]

        # ── Invariants (fail loudly rather than seed garbage) ────────────
        if len(rows) != 480:
            raise CommandError(f"expected 480 thumns, got {len(rows)}")
        ids = [r[GLOBAL_ID] for r in rows]
        if any(a >= b for a, b in zip(ids, ids[1:])):
            raise CommandError("ayah_id_global must be strictly increasing")
        if any(r[PAGE] > nxt[PAGE] for r, nxt in zip(rows, rows[1:])):
            raise CommandError("pages must be non-decreasing")

        rubs = {r.number: r for r in Rub.objects.all()}
        surahs = set(Surah.objects.values_list("pk", flat=True))
        if len(rubs) != 240:
            raise CommandError("Rub table not seeded (run seed_quran first)")

        created = updated = 0
        for i, row in enumerate(rows, start=1):
            if row[SURAH] not in surahs:
                raise CommandError(f"thumn {i}: unknown surah {row[SURAH]}")
            rub_number = (i + 1) // 2  # thumns 1,2 → rub 1; 3,4 → rub 2; …
            _, was_created = Thumn.objects.update_or_create(
                number=i,
                defaults={
                    "rub": rubs[rub_number],
                    "number_in_hizb": ((i - 1) % 8) + 1,
                    "page": row[PAGE],
                    "start_surah_id": row[SURAH],
                    "start_ayah_number": row[AYAH],
                    "ayah_id_global": row[GLOBAL_ID],
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(self.style.SUCCESS(
            f"Thumns seeded: {created} created, {updated} updated (480 total)"
        ))

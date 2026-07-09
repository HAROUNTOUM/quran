# Improvement Plan v2 — Hafez Platform

Unified roadmap agreed 2026-07-03: merges the stabilization/infrastructure plan (v1)
with the Quran Memorization System Redesign, refined. Parent role: **dropped** —
students are adults.

**Execution order:** 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7, with the **Jitsi track (J)**
runnable in parallel at any point (independent docker/infra work). Structural cleanup
(8) and security/settings (9, 10) close the program.

Each phase ends with: full test suite + short review summary before the next.

---

## Phase 0 — Stabilize (baseline must be green) — 0.5–1 day

1. Fix the 4 failing committed tests in `apps/api/tests.py` (session-turn claim/release,
   submit-attendance — 403/400 vs 200). Per-case: stale test vs real regression from
   commit `3ca19b5`.
2. Re-pin `requirements/base.txt` `Django==5.1.*` → `6.0.*` (venv runs 6.0.6);
   sanity-import all pins.
3. Delete empty apps `apps/messaging` (no-chat rule) + `apps/lessons`; remove from
   `INSTALLED_APPS`.
4. Gate `apps.mockup` include behind `settings.DEBUG` in `config/urls.py`.
5. Remove duplicate `venv/` (keep `.venv/`); verify gitignore.
6. Review + commit WIP (multi-role `my_classroom`, `student_rooms.html`, student tabs).

**Done when:** check clean, suite green, boot OK.

---

## Phase 1 — Quran Reference Hierarchy (extend `apps/references`) — 2–3 days

**Single source of truth for Quran structure. NOT a new app** — `references` already
holds `Surah` (114, with `ayah_count`) and `Juz` (30), and `ReviewRequest`,
`MemorizationProgress`, `ProgressLog`, `CircleEnrollment` FK to `references.Surah`.
Grow the hierarchy in place; existing FKs untouched.

### New models (apps/references/models.py)

```
Hizb (60)   — number, juz FK, number_in_juz
Rub (240)   — number, hizb FK, number_in_hizb   # ربع الحزب — the memorization unit
Ayah (6236) — surah FK, number_in_surah, rub FK, page (1–604),
              text_uthmani, text_normalized (diacritics-stripped), sajdah (bool)
```

**DEVIATION (implemented):** dropped the redesign's `Thumn` (480, 1/8-hizb). No
authoritative ayah-boundary dataset exists for a 480-way split, and fabricating one
violates non-negotiable #6. `Rub al-hizb` (240, marked in every mushaf, ~2.5 pages)
is the authoritative atomic unit and the SRS/memorization granularity instead.
Data seeded from Quran.com API v4 (Tanzil/QUL), validated against all invariants,
committed offline as `apps/references/data/quran_seed.json`. **Status: DONE.**

**Normalization rules (no duplicated metadata):**
- `Ayah` carries only `surah` + `thumn` FKs — juz/hizb/rub reached by traversal
  (`ayah.thumn.rub.hizb.juz`). No `*_number` denormalized columns.
- One display text (Uthmani). `text_normalized` exists solely for search and is
  derived, regenerable by the seed command.
- Existing `Surah.ayah_count` stays; add `Surah` helpers (`first_page`, ordering)
  only if needed.

### Seed strategy — static JSON (decided)

- `apps/references/data/quran.json` committed to the repo (offline, deterministic).
- `manage.py seed_quran` — idempotent (update_or_create), validates totals
  (114/30/60/240/480/6236) and page range 1–604 before commit.
- `apps/references/utils.py`: `validate_ayah_range(surah, from, to)`,
  `thumns_in(hizb|juz)`, `resolve_range(...)` traversal helpers.

**Blocks:** everything below.

---

## Phase 2 — QuranSelector Component + Quran API — 1–2 days

One Alpine.js component replaces every manual surah/ayah entry
(today: plain 114-option selects + unbounded number inputs; `ayah_count` unused).

### `templates/components/quran_selector.html`

- Modes: by Juz → Hizbs → Thumns; by Hizb → Rubs/Thumns; by Surah → bounded ayah
  range; by mushaf page.
- Per-thumn status colors (gray unmemorized / green memorized / orange due /
  red weak) fed by a per-student status endpoint — component degrades gracefully
  when no student context (e.g. admin forms).
- Select-all per Hizb; shows surah names, ayah ranges, page numbers inline;
  client bounds from data attributes + server `validate_ayah_range` in every
  consumer's `clean()`.

### API (`/api/v1/quran/`)

- `juz/`, `hizb/`, `rub/`, `thumn/`, `surah/`, `ayah/` list endpoints
  (read-only, cached — data never changes after seed).
- `student-status/` — thumn → status map for the selector colors.

### Consumers to convert

`review_request_create.html` **[DONE]** (+ server-side `validate_ayah_range` in
`User.submit_review_request`); teacher progress-log form and memorization pages
convert as they are rebuilt in Phases 3–4. (Exams are marks-based — not a consumer.)

**Status: DONE** — `templates/components/quran_selector.html` (emit=range | rub,
by-surah + by-rub modes, live ayah bounds, per-rub status colours),
`apps/api/quran.py` read endpoints (`/api/v1/quran/{juz,hizb,rub,surahs,ayahs,student-status}/`,
cached), 7 API tests.

---

## Phase 3 — Memorization Core: Records + SRS Engine — 3–4 days

Merges redesign Phases 3+4+7. **Parallel/additive** — existing
`MemorizationProgress`, `ProgressLog`, `ReviewRequest` keep working untouched;
backfill command bridges old data when ready (non-negotiable #5).

### Models (apps/memorization)

```python
class MemorizationRecord:      # one row per (student, thumn)
    student FK, thumn FK('references.Thumn'), circle FK null
    status: NOT_MEMORIZED / IN_PROGRESS / MEMORIZED / NEEDS_REVIEW / WEAK / MASTERED
    memorized_at, last_reviewed_at, next_review_date, review_interval_days,
    review_count
    unique_together (student, thumn)
    # NO surah_start/ayah_start/... columns — derive from thumn (single source of truth)

class ReviewHistory:           # append-only, never updated/deleted
    record FK, reviewer FK, evaluation, mistakes_count,
    mistake_types JSONField(default=list), teacher_notes,
    previous_interval, new_interval, previous_status, new_status,
    session FK null, created_at
```

**Evaluation scale:** ONE scale shared with `ProgressLog.Grade` (ممتاز/جيد جداً/جيد/
مقبول/ضعيف + راسب) — no third grading vocabulary.

### SRS engine (`apps/memorization/review_engine.py`)

- `calculate_next_review(current_interval, evaluation, mistakes)`:
  weak/failed → reset 1d; acceptable → hold; good ×1.5; very good ×2;
  excellent ×2.5; capped.
- Intervals/multipliers/cap are **settings-registry entries**
  (`review_intervals` default `[1,3,7,15,30,60,120,180,365]`,
  `review_max_interval_days` 365, reset threshold) — admin-editable, audited.
  **No ReviewSettings model.**
- **No DailyPlan model, no midnight Celery job** — the daily plan is a live
  queryset: `MemorizationRecord.objects.due(student)`
  (`next_review_date <= today`, ordered overdue-first) + today's memorization
  target. Always fresh, zero batch-failure surface. Persist plans later only if
  offline mobile demands it.
- `get_weak_sections(student)` queryset (redesign Phase 8, folded in):
  2+ consecutive weak/failed, overdue > N days, mistakes > threshold, or
  teacher-flagged — thresholds from settings registry.

### Fat-model transitions

`record.mark_memorized(by)`, `record.evaluate(by, evaluation, mistakes, notes,
session=None)` → appends ReviewHistory + recalculates schedule atomically;
`teaches_student` enforced on the teacher path.

### Views live in `apps/memorization/views.py` + own urls.py from day one
(never in the accounts god-app). **[views are Phase 4]**

**Status: DONE (core)** — `MemorizationRecord` (unique student+rub, status lifecycle,
`mark_memorized`/`evaluate` fat-model transitions, `record_for` upsert),
append-only `ReviewHistory`, `review_engine.py` (multiplier SRS + `get_weak_sections`),
`MemorizationRecordQuerySet.due()` = the live daily plan. SRS tunables
(`srs_first_interval_days`, `srs_max_interval_days`, `srs_weak_overdue_days`,
`srs_weak_mistakes_threshold`) added to the settings registry; per-evaluation
multipliers stay as documented engine constants (registry has no float type).
Evaluation scale = canonical Arabic grades (ممتاز/جيد جداً/جيد/مقبول/ضعيف/راسب),
sharing four values with `ProgressLog.Grade`. Admin + 15 tests. student-status API
now returns real per-rub colours. **Migration/backfill from old ProgressLog: deferred
to a bridge command (Phase 6/8).**

---

## Phase 4 — Review Workflow UI — 1–2 days

Actor-correct flows (refined from redesign Phase 5):

- **Teacher — evaluation surface** (`/dashboard/reviews/evaluate/…`): from the live
  session (integrates with the existing turn queue: student's turn → their due
  thumns + evaluation form) or from the roster. Records evaluation → engine
  reschedules → history appended.
- **Student — today** (`/dashboard/student/reviews/`): due reviews grouped
  today/overdue/upcoming by Hizb→Thumn, plus today's memorization target; passage
  text shown (Ayah.text_uthmani); self-mark "reviewed alone" (does NOT advance the
  SRS interval — only teacher evaluation does).
- **Student — history** (`/dashboard/student/reviews/history/`): read-only
  chronological log per thumn.

Templates under `templates/dashboard/memorization/`; QuranSelector reused.

---

## Phase 5 — Action-Oriented Dashboards + Estimator — 1.5–2 days   **[DONE]**

**Status: DONE** — review workflow (teacher evaluation + student daily-plan/history),
completion estimator, and both home dashboards rewritten action-first: student leads
with today's due reviews + memorized/240 + next review + weak sections (dropped the
absence/stat grids); teacher leads with the evaluation queue + today's counts
(dropped the past-sessions table). Details below retained for reference.

Rewrite both home dashboards from statistics → actions
(remove Chart.js doughnuts, 4-col stat grids, absence tables):

- **Student home:** today's memorization (Hizb/Thumn) · today's reviews · next
  scheduled review · progress wheel (thumns by status) + streak · upcoming session ·
  classroom join button (kept).
- **Teacher home:** today's students with ready/evaluated states · completed vs
  remaining evaluations · weak-memorization alert list (`get_weak_sections`) ·
  permanent-room banner (kept).
- `templates/components/progress_wheel.html` (SVG, no chart lib).
- **Completion estimator** (redesign Phase 9, folded in — quick win):
  `/dashboard/student/estimator/` — inputs (daily amount unit, frequency weekdays,
  skip-memorized) → instant outputs (remaining ayahs/hizbs/pages, estimated date,
  duration). Pure computation from Phase 1 counts + student's records; Alpine
  reactive, one small API endpoint.

---

## Phase 6 — Practical Reports + Feature Trim + Page Consolidation — 2–3 days

Merges redesign Phase 11 with v1 Phase I.

1. **Reports simplified** (`apps/reports`): Student report (current position,
   today's reviews, weak sections, attendance, last comments) · Teacher report
   (evaluated today, behind-schedule students, weak counts) · Association report
   (actives, completed hizb counts, completion/attendance rates, overdue reviews).
   CSV export. Remove chart-heavy partials.
2. **Remove achievements** (certificates = the recognition system): nav + view +
   url + template now; `StudentAchievement` model dropped after data check.
3. **Merge leaderboards** → one page with circle/global toggle, behind
   `feature_leaderboard_enabled`.
4. **Student pages 20 → ~12** (old URLs redirect): requests + review_requests +
   justifications → "طلباتي" hub with tabs · memorization + stats + weekly_goals →
   one progress page (Phase 4/5 surfaces) · notifications + announcements → one
   inbox.
5. **Component extraction** to `templates/components/`: stat card, filter bar,
   status chip, table shell, page header.

**Deprecations:** `WeeklyGoal` superseded by SRS daily plan (keep read-only, retire
UI); `ReviewRequest` legacy flow kept working, hidden from primary nav.

---

---

## Track J — Self-Hosted Jitsi + JWT (parallel, anytime) — 1–2 days

Independent infra track; can run alongside Phases 1–7.

1. docker-compose: `jitsi/web`, `jitsi/prosody`, `jitsi/jicofo`, `jitsi/jvb`
   (pinned tags, own network, 10000/udp), prosody JWT auth
   (`ENABLE_AUTH=1`, `AUTH_TYPE=jwt`), env `JITSI_APP_ID`/`JITSI_APP_SECRET`.
2. `apps/classrooms/services.py::mint_jitsi_jwt(user, room, moderator)` (PyJWT);
   claims: room, exp (~2h), displayName=`full_name_ar`, moderator for
   teacher/admin/supervisor. No token if `can_join()` fails.
3. `_jitsi_embed.html` appends `?jwt=`; webinar speaker room reuses the helper.
4. **Fallback:** unset `JITSI_APP_SECRET` → current meet.jit.si behavior (dev
   unchanged).
5. `docs/jitsi-selfhost.md` (sizing, DNS, certs, env).

**Decision needed:** target domain/server.

---

## Phase 8 — Session Revamp + Structural De-duplication — 3–4 days

Merges v1 Phases H + C.

1. **Session `content_type`** (hifz/murajaa/tathbit/exam/tajweed/mixed) chosen at
   creation; chips in lists.
2. **Online sessions default to the teacher's permanent Jitsi room**
   (`meeting_source`: classroom/external) — no manual Zoom/Meet URL+password;
   external kept as fallback.
3. **Remove `Circle.surah_range`** (form + column). **`CircleEnrollment.current_surah`
   becomes derived** — now cleanly from `MemorizationRecord` (student's frontier
   thumn → surah): property first, backfill, swap ~10 references, drop FK one
   release later.
4. **Break up the accounts god-app** (120 urls / 4,640 view lines): views move to
   `apps/circles`, `apps/exams`, `apps/requests`, `apps/notifications`; URL names
   stable via namespaced includes + redirect shims.
5. One `role_required` (keep accounts version, delete core copy) ·
   `notifications/services.py::notify()` replacing 42 scattered creates
   (fold `ExamNotification` in with a type field, data migration) ·
   shared Tailwind widget mixin (kills ~30 repeated class strings in forms) ·
   split `apps/api/views.py` (2,195 lines) into a package.

---

## Phase 9 — Security Hardening — 1–2 days

Session timeout from `default_session_timeout_minutes` · lockout after N failed
logins (extend `LoginRateLimitMiddleware`) + stronger validators · upload
validation (content-type + size) · full `teacher_of_student_required` /
`IsTeacherOfStudent` sweep · re-auth for critical settings writes · DRF throttles.

---

## Phase 10 — Settings UI + Flags + Tests + Docs — 2–3 days

1. Per-role settings pages on the registry (`specs_for_role`/`clean_value`,
   writes through `UserSettings.set`/`SystemSettings.set` → audit preserved);
   critical settings get a confirmation step. **Registry cleanup:** remove
   `grades_visible_to_parents` (no parent role); add the Phase 3 SRS keys.
2. Enforce `feature_exams/certificates/leaderboard_enabled` in views + sidebar.
3. Tests: references hierarchy + seed validation, memorization engine
   (interval math, transitions, weak detection), quran API, circles, exams,
   certificates, reports.
4. Docs: deployment, `docs/webinars-streaming.md`, architecture overview.
5. **Program deliverable:** consolidated changelog + decisions/deviations +
   next-improvements list.

---

## Effort & dependencies

```
0  Stabilize        0.5–1d   [—]           gate for everything
1  Quran hierarchy  2–3d     [0]           blocks 2–7
2  QuranSelector    1–2d     [1]
3  SRS core         3–4d     [1,2]
4  Review UI        1–2d     [3]
5  Dashboards+Est.  1.5–2d   [3,4]
6  Reports+Trim     2–3d     [3,4]
7  [removed — folded into QuranSelector]
J  Jitsi selfhost   1–2d     [—]           parallel track, anytime
8  Sessions+Dedup   3–4d     [3 for surah derivation]
9  Security         1–2d     [8 preferred]
10 Settings+Tests   2–3d     [all]
─────────────────────────────
Total ≈ 19–27 days
```

## Decisions

| # | Decision | Status |
|---|---|---|
| 1 | Parent role | **Dropped** — students are adults; remove `grades_visible_to_parents` setting |
| 2 | New app vs extend references | **Extend `apps/references`** — existing FKs untouched, no duplicate Surah |
| 3 | Ayah text source | **Static JSON in repo**, idempotent validated seed command |
| 4 | Old memorization models | **Parallel/additive**; backfill bridge later; WeeklyGoal retired read-only |
| 5 | DailyPlan persistence | **No** — live queryset; revisit only for offline mobile |
| 6 | SRS config | **Settings registry**, not a model |
| 7 | Grading scale | **One scale** aligned with ProgressLog.Grade |
| 8 | Jitsi domain/server | **Pending user** |

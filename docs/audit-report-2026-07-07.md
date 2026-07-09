# تقرير التدقيق الشامل — Quran LMS Full Audit Report

**Date:** 2026-07-07 · **Auditor role:** Senior QA / Product Owner / UX audit
**Scope:** tracking units, Todo system, session types, reports, dead buttons, workflows, permissions
**Verification:** 296 automated tests green (16 added by this audit) · 110 pages smoke-rendered × 4 roles

---

## Executive summary

| # | Issue | Severity | Status |
|---|-------|----------|--------|
| 1 | Progress measured/displayed in **ayah counts** with arithmetic hizb estimates | Critical | **Fixed** |
| 2 | Todo (StudyTask) missing **due date** and **linked session** | High | **Fixed** |
| 3 | Session marking missing the **Recitation** type | High | **Fixed** |
| 4 | No REST API for the Todo workflow | High | **Fixed** |
| 5 | Student reschedule-requests page **500 on every visit** (missing template) | Critical | **Fixed** |
| 6 | Circle leaderboard "آيات المراجعة" column always dead ("—") | Medium | **Fixed** |
| 7 | Achievement engine used a **wrong hardcoded surah→juz map** (juz 16–20 missing surahs) | High | **Fixed** |
| 8 | Hifz report used **6236** (Hafs count) as completion denominator on a Warsh platform | Medium | **Fixed** |
| 9 | Dead password-reset email templates referencing a nonexistent URL | Medium | **Fixed** (deleted) |
| 10 | Reports lacked thumn/hizb columns and explicit from/to ayah range columns | High | **Fixed** |
| 11 | Supervisor board reports only حفظ/مراجعة page volumes (no recitation column) | Low | Open (by design — board is a hifz/murajaa matrix) |
| 12 | `MemorizationProgress` (legacy) vs `MemorizationRecord` (canonical) dual-model debt | Medium | Open (needs data migration, tracked in models.py docstring) |

---

## 1. Tracking-unit audit (Thumn / Hizb) — FIXED

**Expected:** the tracking unit everywhere is the **thumn (ثمن الحزب, 1/8 hizb)** and the **hizb** — never raw ayah counts. Reports still show the actual Quran range (from surah/ayah → to surah/ayah).

**Was:** displays summed `ayah_to − ayah_from + 1` and converted the total to "hizb.quarters" through juz-size arithmetic (`ayahs_to_juz_quarters` / `ayahs_to_hizb_quarters`) — an *estimate*, mislabeled (juz counts were labeled أحزاب), and inconsistent across pages.

**Now:** `apps/references/utils.py` resolves any ayah range against the **real 480 Warsh thumn boundaries** (`Thumn` table):

- `thumn_span(surah, from, to)` → exact first/last thumn of a range
- `count_thumns(ranges)` → distinct athman covered (overlaps count once); verified: whole Quran = exactly 480
- `covered_thumns()` → the set, used for exact juz-completion
- `thumns_to_hizb` / `format_hizb_thumn` → "X أحزاب وY أثمان" labels
- Graceful ayah-estimate fallback only when the Thumn table is unseeded (unit-test DBs)

**Converted surfaces** (view + template + API):
student profile, student stats, achievements, memorization plan (per-circle totals/mastered), both leaderboards (incl. scoring: 1 mastered thumn = 20 pts), admin dashboard stats, admin student detail, admin hifz/murajaa/circles reports, PDF + Excel exports, CSV exports, teacher profile stat, teacher student-progress achievement tiles, DashboardStats/TeacherStats API, memorization workspace (rub→thumn ×2), completion estimator (thumn is now the default pace unit).

`StudentAchievement` gained `total_hifdh_thumns` / `total_murajaah_thumns` (migration `memorization.0016`), recomputed on every progress log; `completed_juz`/`current_juz` are now derived from exact thumn coverage (16 athman per juz) instead of the broken surah map.

## 2. Tracking validation — VERIFIED

- Create/read/update/delete via `/api/v1/memorization-progress/` and `/api/v1/progress-logs/` (role-scoped querysets confirmed).
- Duplicate-safety: `MemorizationRecord` has a DB unique constraint (student, rub); thumn counting is idempotent w.r.t. overlapping ranges.
- Totals, percentages and dashboards recomputed from the same shared helpers — single source of truth.
- New tests: whole-Quran=480, overlap counted once, hizb decomposition, formatting, fallback, range bounds.

## 3. Todo system — WAS PARTIAL, NOW COMPLETE

The Todo system exists as `StudyTask` (assign → student marks done → teacher validates/rejects → validated hifz feeds MemorizationRecord). The audit found it lacked required fields and any API.

Added:
- **`due_date`** (+ `is_overdue` property, `overdue()` queryset, red "متأخرة" badges in student and teacher lists, overdue count in the student view context).
- **`session` FK** — the teaching session the assignment follows; selectable in the teacher form (last 30 sessions of the student's circles), shown in lists/validate page.
- **`recitation` task type** alongside hifz/murajaa (recitation todos do not advance memorization records on validation — verified by test).
- **REST API `/api/v1/tasks/`**: list (filter by status/type/student/circle/session/`?overdue=1`), retrieve, create, patch, delete, `POST /{id}/done/`, `POST /{id}/validate/` — teacher/admin scoped writes, students see only their own; covered by lifecycle + permission tests.
- Todos appear in the student dashboard (pending count + tasks page with status filters) — pre-existing, verified.
- New **tasks CSV report** (`/dashboard/reports/export/csv/?type=tasks`).

## 4. Session marking types — FIXED

`ProgressLog.Category` now = **HIFDH (حفظ جديد) / MURAJAAH (مراجعة) / RECITATION (تلاوة)**.
- Field exists, required on every recorded log (unchanged), stored, editable, and filterable (`?log_category=` on `/api/v1/progress-logs/`).
- Marking modal (teacher session progress) offers all three types.
- Reports/history use `get_log_category_display` so the new type flows through automatically; verified by API tests (create + filter).
- Note: HIFDH label corrected from "تسميع جديد" to "حفظ جديد" to distinguish memorization from recitation.

## 5. Report audit — FIXED

- **CSV hifz/murajaa:** now include من سورة/من آية/إلى سورة/إلى آية + الثمن (span) + المقدار (حزب/ثمن), keeping status/dates.
- **CSV grades:** adds نوع الحصة (session type incl. تلاوة) + the same range/thumn columns.
- **CSV tasks:** new — student, type, range, due date, status, circle, linked session, assigner, dates.
- **Admin report pages (hifz/murajaa/circles):** headline totals, per-student rows and PDF/Excel exports all in hizb/thumn; mastery % = mastered thumns / 480. Per-surah breakdown intentionally keeps ayah coverage (range detail, as required for reports).
- Wrong calculations fixed: 6236 denominator; murajaa "weak parts = ayahs//20" heuristic replaced with exact weak thumns.

## 6. Dead-button / navigation audit — CLEAN AFTER FIXES

- Every `{% url %}` in all templates checked against the URLconf (437 names): 1 failure → dead password-reset templates (old link-based flow) **deleted**; active OTP flow unaffected.
- 110 no-arg pages rendered as all 4 roles (440 requests): 1 failure → **student reschedule-requests page had no template (500)**; template created, renders 200 with filters/pagination/empty state.
- No handler-less buttons found; the report export buttons' dynamic `href="#"` pattern is functional; "قريباً" on scheduled webinars is a legitimate state, not a dead button.
- Leaderboard murajaa column was a hardcoded "—" → now shows real murajaa thumn units.

## 7. Workflow validation — VERIFIED

- Todo: assign → notify → student done → notify teacher (deep-link to validate) → validate/reject → notify student → hifz feeds MemorizationRecord → CircleEnrollment.current_surah refresh. Tested end-to-end via API.
- Review request (تسميع) → approval spawns PrivateSession with link/reminders/marking — pre-existing, tests green.
- Session lifecycle, attendance confirmation, turn-taking: guarded by `is_unlocked`; state guards raise clean validation errors.

## 8. Permission audit — PASS

- All student object views re-check active enrollment before acting (session detail/confirm/turns/reschedule/leaderboards).
- All teacher object views scope by `circle__teacher=request.user` or verify assignment (exams) or enrollment-in-my-circles (tasks, progress).
- API querysets scope by role (progress logs, memorization, new tasks endpoint); teacher writes re-check `teaches_student` at the model layer (defense in depth).
- Cross-student access via the tasks API returns 404 (verified by test); student create/delete → 403 (verified).

---

## Remaining known debt (not blocking)

1. **C03/C04** — retire legacy `MemorizationProgress` in favor of rub/thumn-keyed `MemorizationRecord` (needs backfill migration; read-paths now isolated behind shared helpers, which makes the swap much smaller).
2. Supervisor board recitation column (product decision).
3. `StudentAchievement.total_*_ayahs/pages` kept for the legacy export; displays no longer use them.

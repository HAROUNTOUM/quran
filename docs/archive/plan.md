# Quran Memorization System — Build Plan

## Overview

A comprehensive redesign of the Quran memorization platform, replacing the stats-heavy `WeeklyGoal` system with an action-oriented task workflow, spaced repetition engine, and unified Quran reference database. Multi-tenant Django, Arabic-first RTL.

---

## Phase 0: Task System (Done)

### 0.1 — `StudyTask` Model
- **File:** `apps/memorization/models.py:638`
- Replaces `WeeklyGoal` (now deleted)
- Fields: `student`, `assigned_by`, `task_type` (HIFZ/MURAJAA), `surah` (FK), `ayah_from`, `ayah_to`, `status` (PENDING/DONE/VALIDATED/REJECTED), `rejection_reason`, `notes`, `completed_at`, `validated_at`
- Methods: `mark_done()`, `validate(by, rejection_reason='')`
- Uses `references.Surah` directly (no Quran hierarchy dependency)
- Migration: `0007_studytask.py` ✓ applied

### 0.2 — Notification Types
- **File:** `apps/notifications/models.py`
- Added `TASK_ASSIGNED` and `TASK_VALIDATED` to `Notification.Type` enum
- Migration: `0004_alter_notification_type.py` ✓ applied

### 0.3 — Student Views
- **File:** `apps/accounts/views/student.py`
- `student_tasks` — list with status filter tabs (PENDING/DONE/VALIDATED/REJECTED), inline mark-done button
- `student_task_mark_done` — POST-only, sets status → DONE, sends notification to teacher
- **Note:** Students cannot self-assign tasks; `student_task_create` removed in favor of teacher-only assignment via `teacher_task_assign`

### 0.4 — Teacher Views
- **File:** `apps/accounts/views/teacher.py`
- `teacher_student_tasks` — list per-student with filter + validate/edit/delete actions
- `teacher_task_assign` — POST-only, creates task + notifies student
- `teacher_task_validate` — POST-only, validates or rejects (with reason) + notifies student + **auto-updates MemorizationRecord** on HIFZ validation
- `teacher_task_edit` — edit surah/ayah range
- `teacher_task_delete` — POST-only delete

### 0.5 — Auto-Update on Validation (New)
- **File:** `apps/accounts/views/teacher.py` (inside `teacher_task_validate`)
- When teacher validates a HIFZ task:
  1. Query `Rub.objects.filter(ayahs__surah_id=..., ayahs__number_in_surah__gte=..., __lte=...)`
  2. For each distinct rub, `MemorizationRecord.record_for(student, rub)`
  3. Call `record.mark_memorized(by=teacher)` — sets status→MEMORIZED, schedules first SRS review

### 0.6 — WeeklyGoal Removal
- Deleted model class from `apps/memorization/models.py`
- Deleted all 6 view functions from student.py and teacher.py
- Deleted 6 URL patterns from `apps/accounts/urls.py`
- Removed imports from `__init__.py`
- Removed sidebar links (both student "الأهداف الأسبوعية" and teacher sidebar isActive)
- Removed "الأهداف" button from `templates/dashboard/teacher/students.html`
- Deleted 3 templates: `student/weekly_goals.html`, `teacher/student_goals.html`, `teacher/goal_form.html`
- Migration: `0008_delete_weeklygoal.py` ✓ applied

### 0.7 — Templates
| Template | Purpose |
|---|---|
| `dashboard/student/tasks.html` | Student task list with status tabs |
| `dashboard/teacher/student_tasks.html` | Teacher view of student tasks |
| `dashboard/teacher/task_form.html` | Assign/edit task form |
| `dashboard/teacher/task_validate.html` | Validate/reject form |
| `dashboard/memorization/student_progress.html` | Student memorized rubs list |
| `dashboard/memorization/estimator.html` | Completion estimator |

### 0.8 — Sidebar
- **"المهام"** link for students (points to `student_tasks`)
- **"المهام"** link for teachers (points to `teacher_student_tasks` via student list → `teacher_students`)
- Active-state highlighting for all task routes

---

## Phase 1: Quran Reference Database (Next)

### 1.1 — Missing Models
- **Thumn:** `apps/references/models.py` — Add between Rub and Ayah
  - FK to `Hizb`, `number`, `name_ar`, `name_en`
  - `ayah_from` and `ayah_to` (ayah FK or integer range)
- **JuzDetail** (optional): metadata per juz (manzil, hizb quarter start)

### 1.2 — Data Seeding
- Update seed script (`apps/references/management/commands/`) to populate Thumn
- Verify 6236 ayahs, 240 rubs, 60 hizb, 30 juz, 114 surahs, ~960 thumn

### 1.3 — API Endpoints (read-only)
- `GET /api/references/surahs/` — list all surahs
- `GET /api/references/surahs/:id/` — surah detail with ayah ranges per rub
- `GET /api/references/quarters/` — juz/hizb/rub/thumn tree

### 1.4 — Indexes & Constraints
- Unique constraint on `(hizb, number)` for Thumn
- Index on `(surah_id, number_in_surah)` — already exists
- Index on `rub` FK on Ayah — already exists

---

## Phase 2: Quran Selector Component

### 2.1 — Alpine.js Hierarchical Selector
- **File:** `static/js/quran-selector.js`
- 4-level drill-down: Juz → Hizb → Rub → Thumn → Ayah range
- Each level filters the next (e.g., selecting Juz 1 shows only its 2 Hizbs)
- On final selection: emits `{ juz_id, hizb_id, rub_id, thumn_id, ayah_from, ayah_to }`
- Pre-filled state from URL params or Django template context

### 2.2 — Django Template Tag
- `{% quran_selector name="field_name" selected=object %}` — renders selector
- Accepts initial values for edit forms
- Falls back to surah/ayah selector if Quran DB not yet seeded

### 2.3 — Integration
- Replace surah `<select>` in `dashboard/teacher/task_form.html` and `task_validate.html` with Quran Selector
- Backend: parse selector output into surah+ayah range via helper

---

## Phase 3: Review Request System

### 3.1 — Flow
- Student submits review request → Teacher sees in queue → Teacher evaluates → SRS updated
- Replace current `ReviewRequest` model if needed

### 3.2 — Changes
- **Model:** Link `ReviewRequest` to `StudyTask` (optional) — a review request can be a task marked DONE
- **View:** Teacher review queue sorted by urgency (due date, student requests)
- **Notification:** Push notification to teacher when student requests review

---

## Phase 4: Spaced Repetition Engine (SRS)

### 4.1 — Algorithm
- SM-2 variant with configurable intervals
- Default first interval: 1 day
- Multipliers: `{excellent: 2.5, good: 1.3, weak: 0.5, fail: 0.1}`
- Cap at 180 days max interval

### 4.2 — Existing Implementation
- **File:** `apps/memorization/review_engine.py` — already has `first_interval_days()`, `calculate_next_interval()`, `next_review_date()`, `status_after_evaluation()`
- **File:** `apps/memorization/models.py` — `MemorizationRecord.mark_memorized()`, `evaluate()` methods

### 4.3 — SRS Schedule View
- **Student view:** Daily review queue — shows due MemorizationRecords sorted by urgency
- **Teacher view:** Student review status — heat map of rubs by mastery level
- **Celery beat task:** Daily digest of due reviews (optional)

---

## Phase 5: Teacher Dashboard

### 5.1 — Home Page
- Task queue: pending validations count, most urgent
- Review queue: students waiting for evaluation
- Quick actions: assign task, start session
- Chart: class progress (mastered vs in-progress rubs)

### 5.2 — Student Progress Page
- **Current:** `teacher_student_progress` — list-based view
- **Upgrade:** Rub-level heat map showing each of 240 rubs as colored cell
  - Color: NOT_MEMORIZED (gray), IN_PROGRESS (yellow), MEMORIZED (green), NEEDS_REVIEW (orange), MASTERED (blue)
  - Click to see review history

---

## Phase 6: Student Dashboard

### 6.1 — Home Page
- Today's review queue count + urgency indicator
- Task completion progress this week
- Upcoming sessions
- Achievement badges

### 6.2 — Memorization Map
- Visual rub grid (same as teacher but read-only)
- Tap a rub to see review history
- Quick access: "مراجعة اليوم" button opens today's due reviews

---

## Phase 7: Analytics & Reports

### 7.1 — Per-Student Reports
- Memorization rate (rubs/month)
- Review consistency (missed vs on-time reviews)
- Common mistake categories (from teacher evaluations)
- Estimated completion date (at current pace)

### 7.2 — Class Reports
- Average memorization rate per circle
- Teacher evaluation distribution (pie chart of excellent/good/weak/fail)
- Attendance correlation with progress

### 7.3 — Export
- PDF individual progress report
- Excel class summary
- CSV raw data export for research

---

## Phase 8: API

### 8.1 — Endpoints
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/tasks/` | Student tasks list |
| POST | `/api/v1/tasks/` | Create task |
| PATCH | `/api/v1/tasks/:id/` | Mark done / update |
| GET | `/api/v1/reviews/` | Due reviews for today |
| POST | `/api/v1/reviews/:id/evaluate/` | Teacher evaluation |
| GET | `/api/v1/progress/` | Memorization progress summary |
| GET | `/api/v1/quarters/` | Quran hierarchy tree |

### 8.2 — Serializers
- `StudyTaskSerializer`, `MemorizationRecordSerializer`, `ReviewHistorySerializer`
- Paginated list views with filter params (status, date range, task_type)

---

## Phase 9: Mobile Responsiveness

### 9.1 — Tailwind Breakpoints
- All templates already use responsive classes
- Verify: `sm:` (640px), `md:` (768px), `lg:` (1024px)
- Test on mobile viewports down to 320px

### 9.2 — Touch Interactions
- Swipe on task list to mark done (Alpine.js + touch events)
- Pull-to-refresh on review queue
- Bottom navigation bar on mobile (replaces sidebar)

---

## Phase 10: Optimization & Caching

### 10.1 — Database
- Add composite indexes for common query patterns:
  - `(student, status)` on StudyTask
  - `(student, next_review_date)` on MemorizationRecord — already exists
- Paginate all list views (default 20 per page)

### 10.2 — Queries
- Use `select_related('surah', 'assigned_by')` on task queries
- Use `prefetch_related` for review history
- N+1 prevention: batch-fetch rub records per student

### 10.3 — Caching
- Cache surah list (rarely changes)
- Cache Quran hierarchy tree
- Cache student progress summary (5 min TTL)

---

## Phase 11: Testing

### 11.1 — Unit Tests
- `TestStudyTaskModel` — creation, mark_done, validate, rejection
- `TestStudyTaskViews` — student create/mark-done, teacher assign/validate/edit/delete
- `TestAutoUpdateOnValidate` — verifies MemorizationRecord creation on HIFZ validation
- `TestPermissionChecks` — unauthorized access returns 403/302

### 11.2 — Integration Tests
- Full flow: assign → mark done → validate → SRS record created
- Notification delivery on each status transition
- URL reversal and template rendering

### 11.3 — Coverage Target
- Minimum 80% for memorization app
- Minimum 80% for accounts task views

---

## Phase 12: Deployment

### 12.1 — Data Migration
- Run `manage.py migrate` for all new apps
- Seed Quran reference data

### 12.2 — Environment
- Verify `REDIS_URL` for Celery (SRS digest notifications)
- Configure Celery beat schedule
- Set `DEBUG=False`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`

### 12.3 — Rollback Plan
- If task system has issues: task views are additive, old WeeklyGoal is gone but StudyTask migration can be reversed
- SRS changes are on `MemorizationRecord` — no existing data loss

---

## File Tree (Memorization App)

```
apps/memorization/
├── admin.py              ← MemorizationRecordAdmin, ReviewHistoryAdmin, StudyTaskAdmin
├── models.py             ← 9 models (no WeeklyGoal)
├── review_engine.py      ← SRS algorithm (kept for model-level use)
├── views.py              ← student_progress, completion_estimator
├── urls.py               ← student_progress, estimator (clean — no broken URL references)
├── migrations/           ← 0007–0009 applied
└── tests.py              ← 187 tests pass (model tests kept, view tests for removed SRS views removed)

apps/accounts/views/
├── student.py            ← student_tasks, student_task_mark_done, student_dashboard (no SRS queue)
├── teacher.py            ← teacher_student_tasks, teacher_task_assign, teacher_task_validate (with auto-update), teacher_task_edit, teacher_task_delete, teacher_dashboard (no SRS eval queue)
├── __init__.py           ← clean imports (no student_task_create)
└── urls.py               ← task routes (no student_task_create)

templates/dashboard/
├── student/
│   ├── home.html         ← progress stats (no "مراجعات اليوم" section)
│   └── tasks.html        ← task list with status tabs (incl. rejected)
├── teacher/
│   ├── home.html         ← active circles/halaqat stats (no eval queue)
│   ├── student_tasks.html ← per-student task list (incl. rejected)
│   ├── task_form.html    ← assign/edit form
│   └── task_validate.html ← validate/reject form
├── memorization/
│   ├── student_progress.html ← memorized rubs list (renamed from student_reviews)
│   └── estimator.html    ← completion estimator (kept)
└── partials/
    └── sidebar.html      ← "المهام" + "محفوظاتي" + "حاسبة الختمة" links
```

---

## Audit Journal

### 2026-07-09 22:35:42 CET — API pagination and JWT fixture hardening

- **Problem discovered:** Comprehensive route/template validation and the full Django test suite passed functionally, but test output exposed production-quality warnings:
  - DRF paginated `RecitationGrade` lists used an unordered queryset.
  - DRF paginated absence/justification lists used an unordered `Attendance` queryset.
  - Jitsi JWT tests used a short HS256 secret fixture, producing an insecure key length warning.
- **Analysis:** Unordered paginated querysets can produce duplicate or missing rows across pages as data changes or as the database planner changes result order. The JWT warning came from the test fixture constant, not from production Jitsi settings; however, leaving the warning in the suite hides future real cryptographic configuration warnings.
- **Decision made:** Add deterministic newest-first ordering to the affected API querysets and use a realistic 32+ byte Jitsi test secret.
- **Files modified:**
  - `apps/api/views.py`
  - `apps/classrooms/test_jitsi.py`
  - `plan.md`
- **Reason for the decision:** Ordering is backwards-compatible for API consumers and aligns paginated operational lists with expected newest-first behavior. Updating the test secret removes noise without changing token behavior.
- **Impact on users:** API pagination for grades and absence justifications becomes stable and predictable. No user-facing workflow or business rule changes.
- **Migration or compatibility considerations:** No database migration required. API ordering is deterministic but still returns the same resources.
- **Remaining TODO items:** Rerun targeted API/classroom tests and `manage.py check`; continue auditing route semantics, navigation coherence, permissions, and CRUD completeness.

### 2026-07-09 22:41:35 CET — Student and supervisor CRUD update paths

- **Problem discovered:** The admin CRUD audit found incomplete update workflows:
  - Students had list, create, read/detail, status toggle, import/export-adjacent reporting, and enrollment management, but no explicit edit route for profile fields.
  - Supervisors had list and create only; no edit action was visible or routable.
- **Analysis:** Teacher records already had a dedicated edit workflow. Students and supervisors expose profile/contact fields in list/detail pages, so admins need a clear update path without relying on Django admin or direct database edits. Full hard delete remains intentionally absent because these users have historical attendance, enrollment, messages, and audit relationships; soft status control is safer.
- **Decision made:** Add conservative edit views, URL names, templates, navigation actions, and regression tests for student and supervisor profile updates. Preserve role values server-side and allow only main admins to change a student's batch assignment.
- **Files modified:**
  - `apps/accounts/views/admin.py`
  - `apps/accounts/urls.py`
  - `apps/accounts/views/__init__.py`
  - `apps/accounts/tests.py`
  - `templates/dashboard/students/edit.html`
  - `templates/dashboard/students/detail.html`
  - `templates/dashboard/students/list.html`
  - `templates/dashboard/supervisors/edit.html`
  - `templates/dashboard/supervisors/list.html`
  - `plan.md`
- **Reason for the decision:** Completes the missing Update leg for two admin-managed user entities while preserving existing approval, enrollment, and soft-disable business rules.
- **Impact on users:** Main admins and eligible sub-admins can now edit student data from student list/detail pages. Main admins can edit supervisor contact/profile fields from the supervisor list.
- **Migration or compatibility considerations:** No database migration required. New URL names are additive: `accounts:admin_student_edit` and `accounts:admin_supervisor_edit`.
- **Remaining TODO items:** Continue broader route/navigation/permission audit; consider adding a dedicated supervisor detail page if supervisor operations grow beyond profile editing.

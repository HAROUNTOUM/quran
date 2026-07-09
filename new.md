# Gap Fixes & Changes — 4 July 2026

## Changes Made

### Gap 1: Auto-update MemorizationRecord on HIFZ validation
- **File:** `apps/accounts/views/teacher.py` (`teacher_task_validate`)
- After teacher validates a HIFZ task, queries `Rub.objects.filter(ayahs__surah_id=..., ayahs__number_in_surah__gte=..., __lte=__).distinct()`
- For each distinct Rub, calls `MemorizationRecord.record_for(student, rub, circle=task.circle)` + `record.mark_memorized(by=request.user)`
- Uses helper `_create_memorization_records_for_task(task)` for reuse
- **Note:** Cannot use `.select_related('rub__hizb__juz').distinct('rub__number')` — SQLite test DB doesn't support `DISTINCT ON`. Fallback: `.values('rub__number').distinct()` then fetch by number.

### Gap 2: Student task list — missing "مرفوض" (rejected) filter tab
- **File:** `apps/accounts/views/student.py` (`student_tasks`)
- Added `"rejected"` key to status filter counts dict
- **File:** `templates/dashboard/student/tasks.html`
- Added "مرفوض" filter tab
- Added rejected section in status count display

### Gap 3: Teacher task list — missing "مرفوض" filter tab
- **File:** `apps/accounts/views/teacher.py` (`teacher_student_tasks`)
- Added `"rejected"` key to status filter counts dict  
- **File:** `templates/dashboard/teacher/student_tasks.html`
- Added "مرفوض" filter tab

### Change 4: Remove student task creation (teacher-only assignment)
- **Removed:** `student_task_create` view from `apps/accounts/views/student.py`
- **Removed:** URL pattern from `apps/accounts/urls.py`
- **Removed:** Import from `apps/accounts/views/__init__.py`
- **Deleted:** `templates/dashboard/student/task_form.html`
- **Updated:** `templates/dashboard/partials/sidebar.html` — removed `student_task_create` from isActive

### Change 5: Remove "مراجعات اليوم" (SRS daily review queue)
- **Removed:** "مراجعات اليوم" section + next_review card + weak_sections from `templates/dashboard/student/home.html`
  - Replaced with simpler 3-card stats: الأرباع المحفوظة / نسبة الحضور / المهام بانتظار التحقق
- **Removed:** `due_reviews`, `due_reviews_count`, `weak_sections`, `next_review` from `student_dashboard` context
- **Added:** `pending_tasks_count` to `student_dashboard` context (already computed)
- **Cleaned up:** SRS-related import comment from `student.py`

### Change 6: Remove teacher SRS evaluation queue
- **Removed:** `eval_queue`, `eval_pending_total`, `eval_weak_total`, `evaluated_today` context from `teacher_dashboard` view
- **Removed:** `ReviewHistory` import from `apps/accounts/views/teacher.py`
- **Updated:** `templates/dashboard/teacher/home.html` — replaced SRS evaluation queue stats with active circles/halaqat stats + removed evaluation queue section

### Change 7: Clean up dead/broken memorization URLs and views
- **Removed broken URLs** from `apps/memorization/urls.py`:
  - `dashboard/reviews/` → renamed to `dashboard/progress/` (`student_progress`)
  - `dashboard/reviews/history/` (view never existed → 500)
  - `dashboard/reviews/memorize/` (view never existed → 500)
  - `dashboard/evaluate/` (view never existed → 500)
  - `dashboard/evaluate/<uuid:student_id>/` (view never existed → 500)
- **Kept:** `dashboard/estimator/` (`estimator`)

### Change 8: Rename student_reviews → student_progress
- **Renamed view:** `student_reviews` → `student_progress` in `apps/memorization/views.py`
- **Removed:** `get_weak_sections` call, `weak` from context (replaced with simpler progress-only page)
- **Removed:** `review_engine` import
- **Renamed URL name:** `student_reviews` → `student_progress`
- **Updated sidebar link:** `memorization:student_reviews` → `memorization:student_progress`

### Change 9: Clean up templates
- **Created:** `templates/dashboard/memorization/student_progress.html` — simplified progress page (memorized rubs count + list + link to estimator)
- **Deleted:** `templates/dashboard/memorization/student_reviews.html`
- **Deleted:** `templates/dashboard/memorization/review_history.html`
- **Deleted:** `templates/dashboard/memorization/teacher_evaluate_list.html`
- **Deleted:** `templates/dashboard/memorization/teacher_evaluate_student.html`

### Change 10: Update tests
- **Removed:** `ReviewWorkflowViewTest` class from `apps/memorization/tests.py` (tests for removed views: memorize, student_reviews, teacher evaluate)
- **Kept:** All model tests (SRSEngineTest, MemorizationRecordTest)

## Test Results
- **All 187 tests pass** (including memorization + accounts tests)
- `python manage.py check` — no issues (0 silenced)

## Key Design Decisions
1. **SRS engine retained** in `review_engine.py` and `MemorizationRecord.evaluate()` — model-level code is harmless and can be re-surfaced later via session reports or optional review workflows
2. **MemorizationRecord model kept** — tracks which rubs are memorized (used by HIFZ validation auto-update, student dashboard, estimator)
3. **Reviews happen in session reports** (ProgressLog/RecitationGrade) — teacher evaluates student during circle sessions, not via SRS queue
4. **Student cannot self-assign tasks** — only teacher assigns via `teacher_task_assign`

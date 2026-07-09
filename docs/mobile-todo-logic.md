# Mobile App Todo/Task Logic — Planning Document

## 1. Current System Overview

The platform tracks **weekly goals** per student via the `WeeklyGoal` model:

```
apps/memorization/models.py:309-342
```

### Model Structure

| Field | Type | Notes |
|-------|------|-------|
| `student` | FK → User | One student, many goals |
| `week_start` | Date | Monday of the target week |
| `goal_type` | CharField | `hifz` / `murajaa` / `pages` / `attendance` |
| `target_value` | Float | Student-defined target |
| `achieved_value` | Float | Auto-updated from system data |
| `notes` | Text | Optional |
| `created_at` | DateTime | Auto |
| `updated_at` | DateTime | Auto |

**Unique constraint:** one goal per `(student, week_start, goal_type)`

### Current Goal Types

| Type | Label | Unit | Example Target |
|------|-------|------|----------------|
| `hifz` | حفظ جديد | Number of ayahs | 10 new ayahs |
| `murajaa` | مراجعة | Number of ayahs | 30 review ayahs |
| `pages` | عدد الصفحات | Number of pages | 5 pages |
| `attendance` | الالتزام بالحضور | Number of sessions | 3 sessions |

### Computed Property

```python
@property
def progress_percent(self):
    """Returns 0–100, caps at 100."""
```

### Current State

- **Web views exist** for student-only CRUD (`dashboard/student/goals/`)
- **No API endpoint** — mobile cannot access goals
- **No auto-progress** — `achieved_value` is manually updated
- **No teacher visibility** — teachers cannot view student goals
- **No admin registration** — `WeeklyGoal` not registered in admin

---

## 2. Mobile API Endpoints

### Base URL: `/api/v1/`

All endpoints require JWT authentication (`Authorization: Bearer <token>`).
Standard response format: `{ "success": bool, "message": str, "data": ..., "errors": ... }`

### 2.1 Goals for Current Week

**`GET /api/v1/goals/current/`**

Returns the student's goals for the current week + overall progress summary.

**Response:**
```json
{
  "success": true,
  "data": {
    "week_start": "2026-06-29",
    "week_end": "2026-07-05",
    "goals": [
      {
        "id": 1,
        "goal_type": "hifz",
        "goal_type_label": "حفظ جديد",
        "target_value": 10.0,
        "achieved_value": 7.0,
        "progress_percent": 70,
        "notes": "سورة البقرة",
        "updated_at": "2026-07-03T10:30:00Z"
      }
    ],
    "overall_progress_percent": 62
  }
}
```

**Logic:**
```
today = localdate()
week_start = today - timedelta(days=today.weekday())  # Monday
goals = WeeklyGoal.objects.filter(student=user, week_start=week_start)
overall = avg(goals.progress_percent) if goals else 0
```

### 2.2 Past Weeks

**`GET /api/v1/goals/past/?weeks=4`**

Returns weekly summaries for previous weeks. `weeks` defaults to 4 (max 12).

**Response:**
```json
{
  "success": true,
  "data": {
    "weeks": [
      {
        "week_start": "2026-06-22",
        "overall_progress_percent": 85,
        "goals_count": 3,
        "goals_achieved": 2
      }
    ]
  }
}
```

### 2.3 Create/Update Goal

**`POST /api/v1/goals/`**

Creates a new goal for the current week, or updates an existing one of the same type.

**Request:**
```json
{
  "goal_type": "hifz",
  "target_value": 15.0,
  "notes": "سورة آل عمران"
}
```

**Logic:**
```
week_start = compute_current_week_start()
WeeklyGoal.objects.update_or_create(
    student=request.user,
    week_start=week_start,
    goal_type=validated_data["goal_type"],
    defaults={
        "target_value": validated_data["target_value"],
        "notes": validated_data.get("notes", ""),
    }
)
```

**Validation:**
- `goal_type` must be one of `hifz`, `murajaa`, `pages`, `attendance`
- `target_value` must be > 0
- Returns `422` on validation failure with field-level errors

**Response (201 Created):**
```json
{
  "success": true,
  "message": "تم إضافة الهدف الأسبوعي بنجاح",
  "data": { "id": 2, ... }
}
```

### 2.4 Update Progress

**`PATCH /api/v1/goals/{id}/progress/`**

Partially updates the achieved value (manual progress tracking).

**Request:**
```json
{
  "achieved_value": 12.0
}
```

**Constraints:**
- Goal must belong to the authenticated student
- Goal must be for the current week (past weeks are read-only)
- `achieved_value` must be ≥ 0, and clamped to `target_value` max

### 2.5 Delete Goal

**`DELETE /api/v1/goals/{id}/`**

Deletes a goal (only for current week, only owned by student).

**Response (204 No Content):** On success.
**Response (422):** If goal is from a past week.

### 2.6 Teacher View Student Goals (Optional)

**`GET /api/v1/teacher/students/{student_id}/goals/`**

Requires teacher role + `IsTeacherOfStudent` permission.

Returns the same format as 2.1 but for a specific student.

---

## 3. Data Flow & Auto-Progress Logic

### 3.1 Auto-Update from System Data

Currently `achieved_value` is manual. For mobile, implement auto-calculation:

#### Attendance Goals
```python
def _calc_achieved_attendance(student, week_start, week_end):
    return Attendance.objects.filter(
        student=student,
        session__session_date__gte=week_start,
        session__session_date__lte=week_end,
        status=Attendance.Status.PRESENT,
    ).count()
```

#### Hifz (New Memorization) Goals
```python
def _calc_achieved_hifz(student, week_start, week_end):
    from django.db.models import Sum
    result = MemorizationProgress.objects.filter(
        student=student,
        progress_type="hifz",
        date__gte=week_start,
        date__lte=week_end,
    ).aggregate(total=Sum("amount"))
    return result["total"] or 0
```

#### Murajaa (Review) Goals
```python
def _calc_achieved_murajaa(student, week_start, week_end):
    result = MemorizationProgress.objects.filter(
        student=student,
        progress_type="murajaa",
        date__gte=week_start,
        date__lte=week_end,
    ).aggregate(total=Sum("amount"))
    return result["total"] or 0
```

#### Pages Goals
```python
def _calc_achieved_pages(student, week_start, week_end):
    result = MemorizationProgress.objects.filter(
        student=student,
        date__gte=week_start,
        date__lte=week_end,
    ).aggregate(total=Sum("pages_read"))
    return result["total"] or 0
```

### 3.2 Background Sync (Cron / Celery)

A daily task (`apps/tasks/`) syncs `achieved_value` for all active goals:

```
for goal in WeeklyGoal.objects.filter(week_start=current_week_start):
    calc_fn = CALC_MAP[goal.goal_type]
    computed = calc_fn(goal.student, goal.week_start, goal.week_start + 6 days)
    if computed != goal.achieved_value:
        goal.achieved_value = computed
        goal.save(update_fields=["achieved_value", "updated_at"])
```

If Celery is available:
```
@shared_task
def sync_weekly_goal_progress():
    ...  # runs daily at midnight
```

If no Celery, a management command:
```
python manage.py sync_goal_progress
```

### 3.3 Mobile Data Flow

```
[Mobile App] → POST /api/v1/goals/       → [Django API] → [PostgreSQL]
[Mobile App] → GET  /api/v1/goals/current/ → [Django API] → [PostgreSQL]
                      └── triggers auto-calc of achieved_value
[Mobile App] → PATCH /api/v1/goals/{id}/progress/ → manual override

[Cron/Celery] → sync_goal_progress()     → auto-updates achieved_value
```

### 3.4 Offline Strategy

| Scenario | Mobile Behavior |
|----------|----------------|
| No network | Show last-cached goals from local storage |
| Create goal offline | Queue locally, sync when online (POST after reconnect) |
| Update progress offline | Queue locally, sync when online |
| Read goals offline | Cache `GET /goals/current/` response with `Cache-Control: private, max-age=3600` |
| Conflict resolution | Last-write-wins (server timestamp > local timestamp → server wins) |

---

## 4. Mobile Screen Layout

### Screen 1: Weekly Goals (Home Tab)

```
┌──────────────────────────────┐
│  الأهداف الأسبوعية           │
│  29 يونيو – 5 يوليو          │
│                              │
│  ●●●●●●○○○○  62%            │ ← overall progress bar
│                              │
│  ┌─ حفظ جديد ────────────┐  │
│  │ الهدف: 10 آيات         │  │
│  │ ■■■■■■■□□□  70%       │  │ ← per-goal progress
│  │ أنجزت 7 من 10          │  │
│  │ [+ تحديث التقدم]       │  │
│  └────────────────────────┘  │
│                              │
│  ┌─ مراجعة ──────────────┐  │
│  │ الهدف: 30 آية          │  │
│  │ ■■■■■■■■■■  100%      │  │
│  │ أنجزت 30 من 30         │  │
│  └────────────────────────┘  │
│                              │
│  [+ إضافة هدف جديد]         │
│                              │
│  ── الأسابيع السابقة ──     │
│  22 يونيو    ●●●●●●●○○○ 85% │
│  15 يونيو    ●●●●●○○○○○ 50% │
└──────────────────────────────┘
```

### Screen 2: Create/Edit Goal

```
┌──────────────────────────────┐
│  إضافة هدف جديد              │
│                              │
│  نوع الهدف                    │
│  [ ▼ حفظ جديد    ]          │
│                              │
│  القيمة المستهدفة            │
│  [  10  ]                    │
│                              │
│  ملاحظات (اختياري)          │
│  [ ................................ ]│
│                              │
│  [     حفظ     ]            │
└──────────────────────────────┘
```

### Screen 3: Past Week Detail

```
┌──────────────────────────────┐
│  أسبوع 22 يونيو              │
│                              │
│  ●●●●●●●○○○  85%            │
│                              │
│  حفظ جديد    15/20  75% ✓    │
│  مراجعة      30/30  100% ✓   │
│  الحضور       3/3   100% ✓   │
│  صفحات        0/5     0% ✗   │
│                              │
│  [قراءة فقط — أسبوع سابق]   │
└──────────────────────────────┘
```

---

## 5. API Contract Summary

| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| GET | `/api/v1/goals/current/` | Student | Current week goals + overall progress |
| GET | `/api/v1/goals/past/` | Student | Past weeks summary |
| POST | `/api/v1/goals/` | Student | Create/update goal for current week |
| PATCH | `/api/v1/goals/{id}/progress/` | Student | Update achieved progress |
| DELETE | `/api/v1/goals/{id}/` | Student | Delete current-week goal |
| GET | `/api/v1/teacher/students/{id}/goals/` | Teacher | Teacher view of student goals |
| POST | `/api/v1/goals/sync/` | Staff | Trigger progress sync (admin only) |

### Error Codes

| Code | HTTP | Meaning |
|------|------|---------|
| `invalid_goal_type` | 422 | Unknown goal type |
| `invalid_target` | 422 | Target must be > 0 |
| `past_week_readonly` | 422 | Cannot modify past week goals |
| `not_found` | 404 | Goal not found |
| `forbidden` | 403 | Not your goal / not your student |
| `rate_limited` | 429 | Too many requests |

---

## 6. Push Notifications

When auto-sync detects goal achievement (progress >= 100% for first time):

```python
def _notify_goal_achieved(goal):
    Notification.objects.create(
        recipient=goal.student,
        type=Notification.Type.GOAL_ACHIEVED,  # needs new type
        title="تم تحقيق الهدف 🎉",
        message=f"أحسنت! حققت هدف {goal.get_goal_type_display()} لهذا الأسبوع.",
        link="/dashboard/student/goals/",
    )
```

**Mobile-side:** When the app receives this push, show a congratulatory toast/banner and refresh the goals screen.

---

## 7. Implementation Plan

### Phase A: API Layer (Backend)

| # | Task | Files |
|---|------|-------|
| A1 | Create `WeeklyGoalSerializer` | `apps/api/serializers.py` |
| A2 | Create `WeeklyGoalViewSet` | `apps/api/views.py` |
| A3 | Register `goals/` router in `apps/api/urls.py` | `apps/api/urls.py` |
| A4 | Add `GOAL_ACHIEVED` type to `Notification.Type` | `apps/notifications/models.py` |
| A5 | Add goal notification to `sync_goal_progress` | `apps/tasks/goal_sync.py` |
| A6 | Add `sync_goal_progress` management command | `apps/memorization/management/commands/` |
| A7 | Add goal data to `StudentHomeView` | `apps/api/views.py:2106` |

### Phase B: Auto-Progress Service

| # | Task | Files |
|---|------|-------|
| B1 | Create `apps/memorization/services.py` goal calc functions | New file |
| B2 | Write tests for auto-calc logic | `apps/memorization/tests/` |
| B3 | Register `sync_goal_progress` in cron/Celery | `config/` |

### Phase C: Mobile Client

| # | Task | Notes |
|---|------|-------|
| C1 | Goals API client module | Auth headers, base URL, error handling |
| C2 | Weekly Goals main screen | Progress bars, goal cards |
| C3 | Create/Edit goal form | Picker for type, number input |
| C4 | Past weeks screen | Collapsible list |
| C5 | Auto-sync on app foreground | Refresh goals on resume |
| C6 | Offline caching | AsyncStorage/SQLite |
| C7 | Push notification handler | Navigate to goals screen |

---

## 8. Acceptance Criteria

- [ ] Student can view current week goals with progress bars
- [ ] Student can create new goals (max 4 per week, one per type)
- [ ] Student can update achieved progress
- [ ] Past weeks are read-only (view only, no edit)
- [ ] Attendance-based goals auto-calculate from Attendance model
- [ ] Memorization-based goals auto-calculate from MemorizationProgress
- [ ] Teacher can view their students' goals
- [ ] Push notification sent when goal is 100% achieved
- [ ] All data accessible offline (last synced state)
- [ ] API responds in <200ms for goal queries
- [ ] Rate limit: 30 requests/min per user on goals endpoints

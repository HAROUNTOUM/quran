# Full Application Architecture Audit — Quran LMS (الطبيب الحافظ)

**Date:** 2026-07-11 · **Author role:** Full-Stack Architect / UI-UX / Product
**Method:** static discovery of the whole codebase before any change (per the "audit first, no blind edits" rule).
**Scope reality check:** the requesting prompt is a generic SaaS template (mentions controllers/repositories, hooks, workspace/org switchers, CRM/HR/Finance, bundles). This product is a **Django 5 server-rendered monolith** for an Arabic (RTL) Quran-memorization school with four roles (main-admin, sub-admin/supervisor, teacher, student). Phases have been **adapted to the real stack**; inapplicable ones are marked **N/A** with rationale rather than invented.

> **Status of this document:** analysis and plan only. **No application code was modified** to produce it. Nothing here is executed until you approve a phase.

---

## Phase 1 — Project map

### Stack
- **Backend:** Django 5, split settings (`config/settings/{base,local,production}.py`), Celery (`config/celery.py`), Channels/ASGI + WebSockets (`config/routing.py`, `apps/chat/consumers.py`).
- **Frontend:** server-rendered Django templates (186 `.html`), Tailwind CSS, Alpine.js, HTMX. Not an SPA. **RTL/Arabic-only.**
- **Second surface:** a full **DRF REST API** at `/api/v1/` (`apps/api/`, 22 viewsets + ~18 function/APIView endpoints, JWT auth, drf-spectacular schema/docs).
- **Data:** SQLite in dev (`db.sqlite3`), Postgres in prod (Render). Reference data seeded (114 surahs, 30 juz, 60 hizb, 240 rub, **480 thumn**, 6236 ayah).

### Apps (20) and where their logic actually lives
| App | Models | Own `urls.py`? | Wired at root? | Notes |
|-----|--------|----------------|----------------|-------|
| **accounts** | Batch, User, StudentCard, TeacherAbsence, TeacherSubstitution, SessionSubstitution, PasswordResetCode | ✅ (142 routes) | ✅ `""` | **God-app.** Holds views for exams, batches, announcements, requests, attendance, notifications + all 4 role dashboards. 9,827 LOC. |
| api | — (serializers over other apps' models) | ✅ (24) | ✅ `/api/v1/` | Parallel REST surface mirroring ~22 models. |
| memorization | ReviewRequest, PrivateSession, MemorizationProgress, ProgressLog, StudentAchievement, RecitationGrade, MemorizationRecord, ReviewHistory, StudyTask | ✅ (2) | ✅ `""` | Has the good **`engine.py`** service layer. |
| circles | Circle, CircleEnrollment, SessionStudentNote, Session, SessionRescheduleRequest, SessionTurn, SessionLessonToggle | ❌ | ❌ | Core domain models; **all views live in `accounts`**. 20 migrations. |
| exams | Exam, ExamMark, ExamNotification, ExamApprovalHistory | ❌ | ❌ | `services.py` exists; **views live in `accounts`** under `accounts:admin_exam_*`. |
| attendance | Attendance, SessionAttendanceIntent | ❌ | ❌ | Logic duplicated across `accounts` views **and** the API. |
| announcements | Announcement | ❌ | ❌ | Views in `accounts` (`admin/teacher/student_announcements`). |
| requests | SupportRequest, Comment | ❌ | ❌ | Views in `accounts` (`*_requests`). |
| notifications | Notification | ❌ | ❌ | `services.py` + Alpine store + API viewset. Views in `accounts`. |
| chat | Conversation, Message | ✅ (4) | ✅ | Channels consumers + `services.py`. Real-time DM/channels. |
| references | Surah, Juz, Hizb, Rub, Thumn, Ayah, EvaluationCriterion | ❌ | ❌ | Reference data + `utils.py` (thumn math). Correctly a library app. |
| certificates | CertificateSeq, CertificateTemplate, Certificate | ✅ (10) | ✅ `/dashboard/` | Has `services.py`. |
| webinars | Webinar | ✅ (6) | ✅ | Also surfaced via `accounts:teacher_webinars`. |
| classrooms | TeacherRoom | ✅ (3) | ✅ | |
| emailcenter | EmailCampaign, EmailLog | ✅ (5) | ✅ | Has `services.py`. |
| usersettings | SettingsChangeHistory, UserSettings, SystemSettings | ✅ (1) | ✅ | Has `services.py`. |
| reports | SavedReport | ✅ (1) | ✅ | Thin; most reporting is in `accounts` + `api`. |
| core | UUIDModel, TimeStampedModel, SoftDeleteModel, UserTrackedModel, StudentOwnedModel | ❌ | ❌ | Abstract base models. Correct. |

### Root URL wiring
`config/urls.py` includes only: accounts, classrooms, memorization, api, certificates, webinars, reports, usersettings, chat, emailcenter. **exams / attendance / announcements / requests / notifications are never included** — they are reached only through the `accounts` namespace. This is the single biggest structural signal in the codebase.

---

## Phase 2 — Navigation / route audit

142 routes live under the `accounts:` namespace, grouped by prefix: **56 `admin_*`, 36 `teacher_*`, 29 `student_*`, 2 `supervisor_*`**, plus auth/profile/notifications. Representative findings (full route list is derivable from `apps/accounts/urls.py`):

| Concern | Evidence | Recommendation |
|---------|----------|----------------|
| **Namespace misattribution** | Exam, batch, announcement, request, attendance routes are all `accounts:...` (e.g. `accounts:admin_exam_list`, `accounts:teacher_announcements`). | Re-home under domain namespaces (`exams:`, `announcements:`, `requests:`) as views migrate (Phase 15). |
| **No conflicting/overlapping routes found** | Each path is distinct; role prefixes (`teacher/`, `student/`, `dashboard/`) keep them separate. | ✅ No merges needed on the URL layer. |
| **Reachability** | Every sidebar link resolves to a real name (verified). No orphan template with a dead `{% url %}` found in nav partials. | ✅ |
| **Overloaded single namespace** | 142 names in one `app_name="accounts"` file. | Split file by role now (cheap), re-home by domain later. |
| **Webinars double-surfaced** | Both `webinars:admin_list` and `accounts:teacher_webinars`. | Consolidate teacher webinar entry to the `webinars` app. |

**Verdict:** no route *conflicts* or *dead routes*, but the routing is **mis-organised** — domain functionality is namespaced as `accounts`, which is misleading and forces the god-app to exist.

---

## Phase 3 — UI audit

- **Design language is already consistent:** one Tailwind token set (navy/cream/brick/primary palette in Arabic RTL), shared `base.html` + `dashboard/base.html`, shared partials (`header.html`, `sidebar.html`), and a `templates/components/` + `templates/dashboard/components/` library. This is **not** a "template-looking" UI; it has an opinionated identity.
- **Not duplication (corrected):** the `student/` vs `students/`, `teacher/` vs `teachers/`, `supervisor/` vs `supervisors/` directory pairs are **role-self pages vs admin-CRUD pages**, a deliberate convention — *not* duplicated screens. `templates/exams/` (top-level) holds only PDF templates; `templates/admin/` holds Django-admin import/export overrides. These are legitimate.
- **Real UI issue — nav redundancy:** after the recent header change, **Announcements, Notifications, and Requests now appear in *both* the sidebar and the header**. Two doorways to the same page dilutes the information scent and doubles maintenance.
- **Minor:** two parallel component folders (`templates/components/` and `templates/dashboard/components/`) — verify there is no drift between them.

**Recommendation:** keep the design system; pick a **single home** for each notification-class surface (header for transient/global: notifications, chat, announcements; sidebar for navigational sections). Consolidate the two component folders.

---

## Phase 4 — Component / template audit

- **Reuse is decent:** partials exist for tabs (`_attendance_tabs`, `_circle_tabs`, `_learning_tabs`, `_requests_tabs`), `_memorization_plan`, quran selector (`components/quran_selector.html`), etc.
- **Backend "components" (the real duplication):** business logic, not templates, is duplicated — see Phase 5.
- **Action:** audit `templates/components/` vs `templates/dashboard/components/` for identical partials and merge into one library; extract any repeated table/modal markup in the role dashboards into shared partials.

---

## Phase 5 — Backend audit (the core issue)

### 5.1 God-app `accounts/views/`
| File | Lines | Holds |
|------|-------|-------|
| `admin.py` | **2,936** (128 KB) | admin dashboards, batches, circles, exams, reports, announcements, requests, absences, inscriptions |
| `teacher.py` | 1,171 | teacher dashboard, sessions, marking, exams, tasks, webinars |
| `student.py` | 1,135 | student dashboard, circles, sessions, tasks, reviews, stats |
| `auth.py` | 321 | login/signup/OTP/password reset |
| `supervisor.py` | 178 | supervisor board |
| `common.py` | 135 | profile, notifications |

`admin.py` alone is **7× the 400-line "typical" and 3.6× the 800-line "max"** in the coding-style rules. It mixes at least eight domains.

### 5.2 Dual backend / duplicated logic
There are **two implementations of most write operations**: server views in `accounts` and DRF viewsets in `api`. A **partial** service layer exists (`memorization/engine.py`, and `services.py` in certificates, chat, classrooms, emailcenter, exams, notifications, usersettings) but adoption is **inconsistent**:
- ✅ Good: `session_report_data` / `create_progress_log` are called by *both* server views and the API serializer → single source of truth.
- ❌ Bad: attendance marking is implemented independently in `accounts/views/{teacher,student,admin}.py` **and** `apps/api/views.py` — the exact class of duplication that produced the recurring "DRF doesn't translate Django `ValidationError` → 500" bugs fixed four times this session.

### 5.3 Model debt
- **Dual memorization models:** legacy `MemorizationProgress` vs canonical rub/thumn-keyed `MemorizationRecord` (already tracked as item 12 in `docs/audit-report-2026-07-07.md`). Read paths are now behind shared helpers, which shrinks the eventual swap.
- **Schema churn:** circles 20 migrations, memorization 17 — worth a squash before the next release.

**Recommendation:** make the **service/engine layer mandatory** for every write; both the server view and the API viewset become thin adapters over it. This is the fix that removes the whole "500 in prod, 400 in tests" bug class.

---

## Phase 6 — Frontend ⇄ backend integration

- **Hybrid confirmed:** 10 templates call `/api/v1/*` directly (notifications, announcements list, absence justifications, circles list, student attendance, session progress marking, student sessions, quran selector, student session detail). The rest post to server views.
- **Dead-button status:** the previous audit (`audit-report-2026-07-07.md`) rendered 110 no-arg pages × 4 roles and checked every `{% url %}`; it found and fixed the only two failures (a missing reschedule template 500 and dead password-reset templates). No new dead buttons surfaced in this pass.
- **Open question for the product owner:** *what is the API for?* If a mobile/SPA client is planned → keep it, but consolidate logic into services (5.2). If not → it is a large, separately-tested surface doubling maintenance; scope it down to only the endpoints the templates actually consume.

---

## Phase 7 — Sidebar (adapted)

The sidebar is **already grouped by feature, per role** (sections: الرئيسية / الحلقات / الحفظ والحضور / التسميع والأسئلة / الدعم والبلاغات / الإعلانات / الإشعارات / إدارة… ). The prompt's premise ("overloaded, ungrouped") does not hold. The real fixes:
1. **Remove the sidebar↔header duplication** (Announcements/Notifications/Requests). Recommend: those three live in the **header**; the sidebar keeps only *navigational sections* (dashboards, circles, students, exams, reports, settings).
2. Collapse rarely-used admin items (absence substitutions, email center, inscriptions) into an **"Administration"** group so the top of the sidebar stays high-frequency.

---

## Phase 8 — Header (adapted)

Already present in `templates/dashboard/partials/header.html`: notifications (now Alpine-store-driven live badge), chat/messages, announcements, requests, profile, email center (admin). **Applicable additions:** a **global search** and a **quick-create (+)** would genuinely help.
**N/A for this product:** workspace switcher, organization selector (single-tenant school), language selector (Arabic-only), theme toggle beyond what exists — do not add speculative multi-tenant chrome (YAGNI).

---

## Phases 9–11 — Chat / Notifications / Announcements

**These modules already exist** — the task is *assess & finish*, not *build*:
- **Chat** (`apps/chat`): Conversation/Message models, Channels consumers, `services.py`, inbox + header icon with unread badge. Verify: typing indicators, online presence, file sharing, mobile layout — enumerate gaps against Phase 9's checklist rather than rebuilding.
- **Notifications** (`apps/notifications`): model + `services.py` + API viewset + Alpine store + mark-all-read. Missing from the Phase 10 wishlist: filtering, archive, per-type preferences. Add on top; do not replace.
- **Announcements** (`apps/announcements`): model + role views. Missing: pinning, priority levels, expiry, read-tracking. Add fields + admin UI.

---

## Phase 12 — UX

Common actions are already within 2–3 clicks (role dashboard → section → item). Highest-leverage UX wins: (1) global search in the header; (2) remove the double doorways from Phase 3 so users aren't unsure which to use; (3) a quick-create (+) for the teacher's most frequent action (mark a session / assign a task).

---

## Phase 13 — Performance

- **Bundle budget:** N/A in the SPA sense — server-rendered, minimal JS (Alpine/HTMX from static). Keep watching Tailwind CSS size.
- **Real risks:** N+1 queries in the big list views (batches, circles, student progress) — audit `select_related`/`prefetch_related` in `accounts/views/admin.py`. The dashboard-stats endpoints aggregate over thumn coverage; verify they are not recomputed per-request without caching.
- **Duplicate fetching:** the notification badge + list both hit the API; ensure the Alpine store fetches once and shares.

---

## Phase 14 — Security

- **Fixed this session:** batch-scoping fail-open, cross-batch member hijack, exam edit/detail/create cross-tenant writes, `supervisor_groups` `?batch=` IDOR. Scoping is now centralized in `apps/accounts/scoping.py` (single source of truth) — **good pattern, keep it**.
- **Follow-ups to verify (not yet audited):**
  1. **API↔server scoping parity** — server views use `scoping.py`; API viewsets scope by role separately. Confirm a sub-admin can't reach cross-batch data through `/api/v1/` that the server views now block.
  2. `set_supervisors` silently drops unknown ids / picks an arbitrary primary (M2 from prior review).
  3. File-upload validation (certificates, student cards, chat attachments) — type/size checks.
  4. Secrets: confirm none hardcoded; `BREVO_API_KEY` etc. from env (memory notes Render SMTP is blocked — mail path needs the API key).

---

## Phase 15 — Refactoring plan

### 1. Current architecture
```
                     ┌─────────────────────────────────────────┐
   Browser (RTL)     │  Django server-rendered templates (186)  │
   Tailwind/Alpine/  │  base.html → dashboard/base.html         │
   HTMX ────────────▶│  header + sidebar partials               │
        │            └───────────────┬─────────────────────────┘
        │  10 templates fetch /api    │ most posts
        ▼                             ▼
  ┌──────────────┐        ┌──────────────────────────────────────┐
  │  DRF API      │        │  apps/accounts/views  (GOD-APP)      │
  │  /api/v1  22  │        │  admin.py 2936 · teacher 1171 ·       │
  │  viewsets     │        │  student 1135 · supervisor · common  │
  │  (parallel    │◀──────▶│  → owns exams, batches, announce,    │
  │   logic)      │  dup   │    requests, attendance, notif logic │
  └──────┬────────┘        └───────────────┬──────────────────────┘
         │  partial reuse                   │
         ▼                                  ▼
  ┌──────────────────────────────────────────────────────────────┐
  │  Domain apps (models only for many): circles, exams,          │
  │  attendance, announcements, requests, notifications,          │
  │  memorization(engine.py ✅), references(utils ✅)             │
  └──────────────────────────────────────────────────────────────┘
```

### 2. Recommended architecture
```
  Templates ──┐                 ┌── DRF API (thin adapters)
              ▼                 ▼
        ┌───────────────────────────────────┐
        │  Per-domain services / engine      │  ← single source of truth
        │  exams.services · attendance.svc · │    for every WRITE
        │  memorization.engine · circles.svc │
        └───────────────┬───────────────────┘
                        ▼
        ┌───────────────────────────────────┐
        │  Domain apps own their views+urls: │
        │  exams/ attendance/ announcements/ │
        │  requests/ notifications/ circles/ │
        └───────────────────────────────────┘
   accounts = auth + users + batches only.  scoping.py = shared guard.
```

### 3. New navigation tree (deduped)
```
HEADER (global/transient):  🔍 Search · ➕ Quick-create · 💬 Chat · 🔔 Notifications
                            · 📣 Announcements · 👤 Profile
SIDEBAR (navigational sections, per role):
  Admin:  Dashboard · Batches · Circles · Students · Teachers · Supervisors
          · Exams & Certificates · Reports · Administration(absences, email,
          inscriptions, settings)
  Teacher: Dashboard · My Circles & Schedule · Students · Marking/Tasks
          · Exams · Webinars
  Student: Dashboard · Circles & Schedule · Memorization & Attendance
          · Reviews & Questions · Results & Achievements
  Supervisor: Dashboard · Batch follow-up board
```
(Announcements/Notifications/Requests removed from sidebar — header only.)

### 4. New route map (target namespaces)
`accounts:` → auth, users, batches, profile only.
New/rehomed: `exams:*`, `attendance:*`, `announcements:*`, `requests:*`, `notifications:*`, `circles:*`, `supervisor:*`. Include each app's `urls.py` in `config/urls.py`.

### 5. Component hierarchy
One `templates/components/` library (merge the two folders): `quran_selector`, tab strips, data-table, modal, stat-card, empty-state, pagination. Role dashboards compose these.

### 6. Backend architecture
Every write goes through a domain service that raises **DRF-translatable** errors; server view and API viewset both call it. Extend the `engine.py` pattern to attendance, exams, requests, announcements first (highest duplication).

### 7. Database impact
- Minimal for the restructure (moving views doesn't touch schema).
- Retire `MemorizationProgress` → `MemorizationRecord` (needs a backfill migration; already de-risked).
- Squash circles/memorization migrations before next release.

### 8. Files to delete
Root clutter → move to `docs/` or remove: `new.md`, `new1.md`, `plan.md`, `system-ui-optimization-prompt.md`, `ui_audit/` (fold into `docs/`), empty-ish `tasks/`. Consolidate `README.md`/`LOCAL_README.md`/`CHANGES.md`.

### 9. Files to split / merge
- **Split** `accounts/views/admin.py` (2,936 LOC) by domain into the target apps' `views.py`.
- **Merge** the two component template folders; merge duplicated attendance write-logic into `attendance/services.py`.

### 10. Files to rename
- For clarity, admin-CRUD template dirs `students/ teachers/ supervisors/` → `manage_students/` etc. (optional; the convention is defensible if documented).
- Route names as they re-home (`accounts:admin_exam_list` → `exams:list`).

### 11. API changes
Decide the API's purpose (Phase 6). Then: consolidate viewset logic into services, and either (a) keep full API + document it as the mobile contract, or (b) trim to the ~10 endpoints the templates consume. No breaking changes until that decision.

### 12. Migration strategy — **strangler pattern**
Move **one domain at a time** (suggested order: exams → announcements → requests → attendance → notifications → circles), each as its own PR: create the app's `views.py`+`urls.py`, move logic to `services.py`, point templates/URLs at the new names, delete the old block from `admin.py`, keep tests green. `accounts` shrinks each step; nothing big-bangs.

### 13. Risk assessment
| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| URL-name churn breaks `{% url %}` in 186 templates | High | High | Keep old names as aliases for one release; grep every rename; run the 110-page × 4-role smoke render each step. |
| Behaviour drift when de-duplicating logic into services | Medium | High | Move behind existing test suite (330 tests); add characterization tests before extracting. |
| API/server scoping divergence during move | Medium | High (security) | Route both through `scoping.py`; add cross-surface scoping tests (Phase 14 follow-up 1). |
| Migration squash on a live Render DB | Low | High | Squash only in a maintenance window with a fresh backup; never rewrite applied prod migrations. |

### 14. Step-by-step plan
1. **Ship the current security fixes** (done this session: exam/supervisor scoping; commits `814f206`).
2. **Docs/root cleanup** (delete/move clutter) — zero-risk, do first.
3. **Split `admin.py` by domain in place** (same app, new files) — no URL change, pure readability win.
4. **Merge component template folders**; remove sidebar↔header nav duplication.
5. **Strangler move, one domain per PR** (Phase 12 order), routing logic through services and keeping URL aliases.
6. **API decision + logic consolidation** into services; add API↔server scoping-parity tests.
7. **Model debt:** retire `MemorizationProgress`; squash migrations pre-release.
8. **Feature top-ups** on existing chat/notifications/announcements (pinning, priority, presence, filtering) once structure is clean.

### 15. Summary
The application is **functionally healthy and visually consistent** — no route conflicts, no significant dead buttons, an already-grouped sidebar, a real design system, and security holes closed this session. The problems are **structural, not cosmetic**:
1. a **9,800-LOC `accounts` god-app** owning five other domains' logic;
2. a **DRF API duplicating server-view logic** with an inconsistently-adopted service layer (the root cause of the recurring prod-500 bug class);
3. **navigation redundancy** between the new header and the sidebar;
4. known **model/migration debt** and **repo clutter**.

Fixing these via the **strangler plan** (services-first, one domain per PR, URL aliases, tests green each step) yields: sharply better **maintainability** (files under the 800-line rule, one place per behaviour), fewer **prod bugs** (single validated write path), and a clearer **UX** (one home per action) — with **low risk** because nothing is rewritten wholesale and the 330-test suite guards every step.

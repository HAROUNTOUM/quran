# Fix Plan — Webinars + Private Sessions

> Self-contained work order for a fresh Claude Code session. Repo: Django 6 Quran
> memorization platform (Arabic RTL). Run via `./.venv/bin/python manage.py …`,
> dev settings `config.settings.local` (SQLite), tests `manage.py test --parallel=1`.
> No chat feature; structured tickets only. Fat-model/thin-view. Tailwind CDN
> (literal class names only — no dynamic `bg-{{x}}-50`), Alpine, htmx, emerald
> `primary` + amber `accent`, Tajawal.

## Locked decisions (from product owner)
1. **Webinar creation stays admin-only.** Do NOT let teachers create webinars.
   Instead surface a teacher "ندواتي كمتحدّث" page for webinars where they are
   host or co-speaker, with a **دخول غرفة المتحدثين** button.
2. **Enable the webinars module by default** (`feature_webinars_enabled` → True).
3. **Private sessions: do all three** — reminders running in prod, admin oversight
   view, and never-blank meeting link.

---

## Diagnosis (already confirmed — don't re-investigate)

**Webinars**
- `apps/usersettings/registry.py` → `feature_webinars_enabled` default is **False**,
  so the whole module is hidden on the live deploy. `get_system_setting` returns
  `store.data.get(key, spec.default)`, i.e. the default applies per-key when the
  key was never saved — so flipping the default to True enables it immediately in
  prod with **no data migration** (unless an admin explicitly stored False).
- `templates/dashboard/partials/sidebar.html:88` — the **teacher** webinar link is
  NOT feature-gated and points to `webinars:list` (audience view). When the module
  is off, `apps/webinars/views.py` `_require_module` redirects non-admins to the
  dashboard → dead link.
- Management views (`webinar_admin_list/create/manage`) are `@role_required("admin")`
  and `Webinar.host` is `limit_choices_to={"role":"admin"}`. Teachers can only be
  admin-assigned **co_speakers** (`Webinar.co_speakers`, `can_join_speaker_room`),
  and have no surface to find/enter their speaker room.

**Private sessions** (`apps/memorization/models.py` → `PrivateSession`)
- `send_session_reminders` management command exists but **nothing runs it in prod**:
  `render.yaml` deploys only a `web` service (no Celery worker/beat, no cron).
- No admin oversight view of teacher↔student private sessions.
- `PrivateSession` has no `effective_meeting_url()` fallback, so an approval without
  a link leaves the student's page blank (normal `Session` falls back to the
  teacher's permanent classroom room via `TeacherRoom`).
- `render.yaml` still targets `branch: improvement-plan-v2`; live service deploys `main`.

---

## Part A — Webinars

### A1. Enable by default
- `apps/usersettings/registry.py`: set `feature_webinars_enabled` `default=True`.
- No migration required (registry-backed). Verify in a shell that
  `feature_enabled("webinars")` returns True on a fresh DB.

### A2. Gate + repoint the teacher sidebar link
- `templates/dashboard/partials/sidebar.html` (~line 88, teacher block): wrap the
  webinar link in `{% if features.webinars %}…{% endif %}` and point it at the new
  teacher speaker page **`accounts:teacher_webinars`** (A3), label "الندوات المباشرة".
  Update its `isActive('webinar')` to also match `isActive('teacher_webinars')`.

### A3. Teacher speaker surface — "ندواتي كمتحدّث"
- **View** `teacher_webinars` in `apps/accounts/views/teacher.py` (`@role_required(TEACHER)`):
  list `Webinar.objects.filter(Q(host=user) | Q(co_speakers=user)).distinct()`
  ordered by scheduled time. (Import `Webinar` from `apps.webinars.models`.)
- **URL** `dashboard/teacher/webinars/` name `teacher_webinars` in `apps/accounts/urls.py`;
  export the view in `apps/accounts/views/__init__.py`.
- **Template** `templates/dashboard/teacher/webinars.html` (extends `dashboard/base.html`):
  cards/rows with title, status chip, scheduled time, and a **دخول غرفة المتحدثين**
  button → `{% url 'webinars:speaker_room' w.pk %}` shown only when
  `w.status` in (SCHEDULED, LIVE). Empty state when none.
- Keep the existing student webinar tab (التواصل → الندوات) and audience
  `webinars:list` untouched.

### A4. Verify admin path
- Admin sidebar webinar link (`sidebar.html` ~line 203) is already `{% if features.webinars %}`
  → `webinars:admin_list`. With A1 it now shows. No change unless it regressed.

---

## Part B — Private Sessions

### B1. Never-blank meeting link
- `apps/memorization/models.py` `PrivateSession`: add
  `effective_meeting_url()` mirroring `apps/circles/models.py` `Session.effective_meeting_url()`
  — return `self.meeting_url` if set, else the teacher's `TeacherRoom` join URL
  (`reverse("classrooms:join", kwargs={"slug": room.slug})`), else "".
- Update `templates/dashboard/student/private_sessions.html` and
  `templates/dashboard/teacher/private_sessions.html` to use `s.effective_meeting_url`.

### B2. Admin oversight view
- **View** `admin_private_sessions` in `apps/accounts/views/admin.py`
  (`@role_required(ADMIN, SUPERVISOR)`): read-only list of all `PrivateSession`
  (`select_related("teacher","student","circle")`), optional `?status=` filter,
  paginated. Template `templates/dashboard/admin/private_sessions.html`
  (extends `dashboard/base.html`) — teacher, student, date/time, status, result.
- **URL** `dashboard/admin/private-sessions/` name `admin_private_sessions`; export it.
- **Sidebar**: add a gated-by-nothing admin entry under the admin "التواصل"/reports
  area (admin block in `sidebar.html`).

### B3. Reminders in production
- Add a **cron service** to `render.yaml` (free-plan cron; shares DB/Redis env):
  ```yaml
  - type: cron
    name: hafez-reminders
    runtime: docker
    dockerfilePath: ./Dockerfile
    schedule: "0 6 * * *"        # daily 06:00 UTC
    dockerCommand: python manage.py send_session_reminders
    envVars:                      # reuse the same DB/Redis/DJANGO_SETTINGS as web
      - fromGroup: …              # mirror the web service's env vars
  ```
  (If a cron service is unavailable on the plan, fall back to a Celery-beat periodic
  task — `config/celery.py` + a `beat_schedule` entry — plus a worker+beat service.
  Cron service is preferred: simplest, no long-running worker.)
- Confirm `send_session_reminders` runs headless (it already guards with
  `reminder_sent_at`, idempotent).

### B4. render.yaml branch fix
- `branch: improvement-plan-v2` → `branch: main`.

### B5. (Optional) Dedupe approval notification
- `apps/notifications/signals.py` `notify_review_request_status`: when
  `instance.type == RECITATION` and status becomes APPROVED, skip the generic
  "تم قبول طلبك" (the specific "تم تحديد جلسة تسميع خاصة" is sent by
  `PrivateSession._notify_scheduled`). Low priority.

---

## Verification (run after each part; all must pass)
- `./.venv/bin/python manage.py check --settings=config.settings.local`
- Template parse smoke (get_template) for every touched template.
- `./.venv/bin/python manage.py test --parallel=1 --settings=config.settings.local`
  — full suite must stay green (currently **218**). Add tests:
  - teacher_webinars shows only host/co-speaker webinars, excludes others.
  - `PrivateSession.effective_meeting_url()` falls back to the classroom room.
  - `admin_private_sessions` access control (admin/supervisor only; teacher/student 403).
- Manual: toggle the module in Settings → الوحدات; teacher sees "ندواتي كمتحدّث"
  with a working speaker-room button; admin sees the private-sessions monitor;
  `manage.py send_session_reminders` sends for tomorrow's sessions once.

## Out of scope (do not do)
- Teacher-created webinars (creation stays admin-only).
- Any change to the no-chat rule, the Jitsi audience/broadcast model, or the
  student تسميع→approval→PrivateSession flow itself (already working, 218 tests).

# UI and Feature Consolidation Architecture

Date: 2026-07-04

Scope: Django server-rendered dashboard UI, route structure, task workflows, and reusable component consolidation for the Hafez Quran memorization platform.

This is not a visual redesign brief. It is a product-structure brief: reduce page count, navigation depth, repeated controls, and workflow context switching.

## Evidence Snapshot

- The project has 129 HTML templates; dashboard templates dominate the surface.
- Dashboard template clusters: teacher 22, student 20, reports 9, exams 7, webinars 6, classrooms 5, certificates 7 outside `dashboard/`.
- `apps/accounts/urls.py` exposes most user workflows as separate pages: admin routes at lines 13-57 and 91-124, teacher routes at lines 60-89 and 127-130, student routes at lines 96-109 and 132-152.
- The sidebar exposes page fragments as primary navigation. Teacher nav splits live teaching, classroom, students, tasks, exams, certificates, requests, announcements, notifications, review requests, reschedules, absence justifications, and absences. Student nav splits circles, sessions, classroom, progress, estimator, memorization, stats, tasks, leaderboard, attendance, justifications, achievements, certificates, review requests, exams, support requests, announcements, notifications, and webinars.
- The domain model already points to task-first workspaces:
  - `Circle` creates the primary teaching context.
  - `Session` consumes circle, attendance, turns, live room, progress logs, notes, reschedules, and review evaluations.
  - `MemorizationRecord`, `ReviewHistory`, `StudyTask`, and `ProgressLog` all attach student learning work to student/circle/session.
  - `SupportRequest`, `ReviewRequest`, `SessionRescheduleRequest`, `Attendance.justification`, `Notification`, and `Announcement` are all communication/inbox items.

## Target Navigation Model

The product should have three depths:

1. Home
2. Workspace
3. Context panel, drawer, modal, tab, or inline operation

Primary nav should become role-specific and short.

Student:

- Today
- My Learning
- My Circle
- Inbox
- Results

Teacher:

- Today
- Circle Workspace
- Students
- Inbox
- Assessments

Admin/Supervisor:

- Operations
- People
- Circles
- Assessments
- Inbox
- Reports

## Feature Relationship Graph

### Circle Workspace

Creates:

- Circle
- Enrollment
- Session
- Classroom room
- Webinar association when relevant

Edits:

- Circle metadata
- Schedule
- Teacher assignment
- Student enrollment status
- Active/inactive circle state

Consumes:

- Users
- Quran reference data
- Attendance
- Memorization records
- Study tasks
- Exams
- Certificates
- Reports

Reports and analytics:

- Attendance rate
- Active students
- Weak sections
- Completed rub/hizb counts
- Exam outcomes
- Teacher coverage

Notifications:

- Enrollment approval
- Session starting
- Task assigned
- Review due
- Certificate issued
- Exam published

Permissions:

- Admin/supervisor: manage all
- Teacher: manage assigned circles and sessions
- Student: view/enroll/drop allowed circles

Always appears with:

- Students
- Sessions
- Attendance
- Progress
- Tasks
- Classroom

### Session Workspace

Creates:

- Attendance records
- Attendance intents
- Turns
- Progress logs
- Review evaluations
- Student notes
- Reschedule requests

Edits:

- Session status
- Meeting link
- Turn order
- Attendance state
- Lesson toggles
- Progress/evaluation rows

Consumes:

- Circle
- Enrollment
- Memorization due queue
- Study tasks
- Classroom/Jitsi

Reports and analytics:

- Present/absent counts
- Evaluated vs remaining students
- Weak/late/overdue memorization
- Progress logs by session

Notifications:

- Session starting
- Reschedule request/update
- Task validation
- Review request outcome

Permissions:

- Teacher owns session operations
- Student confirms attendance, claims/release turn, requests reschedule
- Admin/supervisor can override

Always appears with:

- Roster
- Attendance
- Turn queue
- Evaluation form
- Classroom link

### Student Learning Workspace

Creates:

- Self-mark memorized
- Study task completion
- Review request
- Request/reschedule/justification as needed

Edits:

- Task status
- Review request draft
- Daily plan interactions

Consumes:

- MemorizationRecord
- ReviewHistory
- StudyTask
- ProgressLog
- QuranSelector
- ExamMark
- Certificate

Reports and analytics:

- Daily due reviews
- Progress by rub/hizb/juz
- Weak sections
- Completion estimate
- History

Notifications:

- Task assigned/validated
- Review due
- Exam published
- Certificate issued

Permissions:

- Student own data
- Teacher/admin contextual read/update

Always appears with:

- Today plan
- Quran map
- Tasks
- Progress history
- Estimator

### Inbox Workspace

Creates:

- Support request
- Announcement
- Review request
- Reschedule request
- Absence justification
- Notification

Edits:

- Status transitions
- Comments
- Mark read/unread
- Approve/reject

Consumes:

- User
- Circle
- Session
- Attendance
- SupportRequest
- ReviewRequest
- Notification
- Announcement

Reports and analytics:

- Open requests
- Overdue requests
- Response time
- Read/unread state

Notifications:

- All request lifecycle events

Permissions:

- Student/teacher: own and relevant circle items
- Admin/supervisor: all operational items

Always appears with:

- Filters
- Status chips
- Detail inspector
- Reply/action form

## Optimizations

### 1. Student Learning Workspace

Current Structure:

- `/dashboard/student/`
- `/dashboard/student/memorization/`
- `/dashboard/progress/`
- `/dashboard/estimator/`
- `/dashboard/student/stats/`
- `/dashboard/student/tasks/`
- `/dashboard/student/achievements/`
- `/dashboard/student/leaderboard/`
- `/dashboard/student/circles/<pk>/leaderboard/`
- `/dashboard/student/review-requests/`
- `/dashboard/student/review-requests/create/`

Problem:

- Learning is split by data type instead of task: today plan, progress map, stats, tasks, estimator, review requests, achievements, and leaderboard each compete for navigation.
- `StudentAchievement` duplicates progress/certificate meaning and is already called out for removal in the roadmap.

User Friction:

- Student must jump between progress, tasks, memorization, stats, review requests, and estimator to answer "what do I do today?".
- Repeated page headers and filters create scrolling before useful actions.
- Leaderboard and achievement pages encourage secondary browsing inside the core learning workflow.

Related Features:

- `MemorizationRecord.due()`
- `ReviewHistory`
- `StudyTask`
- `ProgressLog`
- `ReviewRequest`
- `Certificate`
- `ExamMark`
- Quran selector/search

Why They Belong Together:

- All are either an input to, output of, or report on student memorization work.
- The student does not need separate destinations for planning, doing, and reviewing learning.

Proposed Workspace:

- New canonical route: `/dashboard/student/learn/`
- Tabs:
  - Today: due reviews, assigned tasks, next session, review request CTA.
  - Quran Map: rub/hizb/juz status with search and filters.
  - Tasks: assigned work, mark done inline.
  - History: review history, progress logs, teacher notes.
  - Estimate: completion estimator as a side panel or tab, not a standalone nav item.
  - Recognition: certificates and exam results summary; no separate achievements page.
- Right inspector:
  - Selected rub/passage details.
  - Latest evaluations.
  - Related tasks.
  - Request review action.

Pages Removed:

- Remove from primary nav: memorization, progress, estimator, stats, tasks, achievements, both leaderboards, review-request create.
- Keep old URLs as redirects or deep links into the correct tab.

Navigation Removed:

- Student progress nav group shrinks from about 6 primary links to 1.
- Review request creation becomes inline from selected passage.

Clicks Saved:

- Typical daily learning flow: 4-8 clicks saved.
- Requesting review for a selected passage: 2-4 clicks saved.
- Checking task plus related history: 3-5 clicks saved.

Scrolling Reduced:

- Replace long stats pages with compact panels.
- Use sticky section tabs and virtualized/limited history rows.

Context Switching Reduced:

- Student stays in one workspace from "what is due?" to "mark done/request review/check history".

Reusable Components:

- `WorkspaceShell`
- `WorkspaceTabs`
- `QuranMapPanel`
- `DueReviewList`
- `StudyTaskList`
- `Timeline`
- `StatusChip`
- `ActionMenu`
- `SideInspector`

Implementation Priority:

- P0. This removes the most student-facing fragmentation and matches the existing roadmap phase 6.

Estimated UX Improvement:

- Very high: 35-50% less navigation for daily student work.

### 2. Student Circle and Session Workspace

Current Structure:

- `/dashboard/student/circles/`
- `/dashboard/student/circles/<pk>/`
- `/dashboard/student/circles/<pk>/enroll/`
- `/dashboard/student/circles/<pk>/unenroll/`
- `/dashboard/student/sessions/`
- `/dashboard/student/sessions/<pk>/`
- `/dashboard/student/sessions/<pk>/claim-turn/`
- `/dashboard/student/sessions/<pk>/release-turn/`
- `/dashboard/student/sessions/<pk>/reschedule/`
- `/dashboard/classroom/`
- `/dashboard/student/attendance/`
- `/dashboard/student/justifications/`

Problem:

- Circle membership, schedule, session details, live room, attendance, turn queue, and absence justification are one workflow but are separated.

User Friction:

- Student leaves the circle context to view sessions, then leaves again for classroom, then again for attendance/justification.
- Session actions are hidden behind detail pages instead of being visible beside the upcoming/current session.

Related Features:

- Circle enrollment
- Session
- SessionTurn
- SessionAttendanceIntent
- Attendance
- SessionRescheduleRequest
- Classroom room

Why They Belong Together:

- The student enters this area to participate in a circle, attend a session, claim/release a turn, and resolve attendance issues.

Proposed Workspace:

- Canonical route: `/dashboard/student/circles/<circle_id>/`
- Tabs:
  - Overview: teacher, schedule, current position, next session.
  - Sessions: upcoming/past sessions with expandable rows.
  - Live: classroom embed/join panel for active/upcoming session.
  - Attendance: attendance record, justifications inline.
  - Members: lightweight roster if permitted.
  - Requests: reschedule and circle-related requests.
- Global `/dashboard/student/circles/` remains as a chooser/list, not a working surface.

Pages Removed:

- Sessions list/detail becomes tab/expandable rows.
- Classroom becomes embedded in circle/session workspace.
- Attendance and justifications merge into Attendance tab.
- Reschedule becomes a drawer from session row.

Navigation Removed:

- Three sidebar links collapse into one "My Circle".
- Session detail/claim/release can stay as POST endpoints, not destination pages.

Clicks Saved:

- Join live session: 2-3 clicks saved.
- Claim turn from session context: 1-2 clicks saved.
- Submit justification: 3-5 clicks saved.

Scrolling Reduced:

- Attendance history paginated within tab.
- Session rows expand instead of separate full pages.

Context Switching Reduced:

- Student remains inside current circle while attending, requesting schedule change, and checking attendance.

Reusable Components:

- `SessionRow`
- `AttendanceTimeline`
- `InlineJustificationForm`
- `LiveRoomPanel`
- `TurnQueue`

Implementation Priority:

- P1, after Student Learning Workspace.

Estimated UX Improvement:

- High: 25-40% less navigation for attendance/session workflows.

### 3. Student Inbox Workspace

Current Structure:

- `/dashboard/student/requests/`
- `/dashboard/student/requests/create/`
- `/dashboard/student/requests/<pk>/`
- `/dashboard/student/review-requests/`
- `/dashboard/student/review-requests/create/`
- `/dashboard/student/announcements/`
- `/dashboard/student/notifications/`
- `/dashboard/student/justifications/`
- `/dashboard/student/sessions/<pk>/reschedule/`

Problem:

- Communication is split by implementation model rather than user intent.

User Friction:

- Student has to check multiple pages to know what needs attention.
- Notifications are disconnected from the action target they announce.

Related Features:

- SupportRequest
- ReviewRequest
- SessionRescheduleRequest
- Attendance.justification
- Announcement
- Notification

Why They Belong Together:

- These are all inbound/outbound messages or requests with read/action/status states.

Proposed Workspace:

- Canonical route: `/dashboard/student/inbox/`
- Tabs or segmented filters:
  - All
  - Requests
  - Reviews
  - Attendance
  - Announcements
  - Notifications
- List-detail split:
  - Left: filterable thread/request list.
  - Right: detail panel with comments/actions.
- Create request opens drawer with request type.
- Notifications deep-link into the relevant thread/panel.

Pages Removed:

- Student announcements, notifications, support requests, review requests, justifications, and reschedule create as separate nav pages.

Navigation Removed:

- Communication nav group shrinks from 5+ links to 1.

Clicks Saved:

- Respond to or inspect a notification: 2-5 clicks saved.
- Create a support/review/reschedule request: 1-3 clicks saved.

Scrolling Reduced:

- List-detail split avoids long pages of cards.
- Filters stay sticky.

Context Switching Reduced:

- All communication lifecycle items stay in one workspace.

Reusable Components:

- `InboxShell`
- `ThreadList`
- `MessageTimeline`
- `RequestStatusChip`
- `RequestActionPanel`
- `UnreadBadge`

Implementation Priority:

- P1, because it simplifies both student and teacher/admin surfaces.

Estimated UX Improvement:

- High: 30-45% less communication checking effort.

### 4. Teacher Circle Workspace

Current Structure:

- `/dashboard/teacher/`
- `/dashboard/teacher/sessions/manage/`
- `/dashboard/teacher/circles/<pk>/`
- `/dashboard/teacher/circles/<circle_pk>/sessions/create/`
- `/dashboard/teacher/sessions/<pk>/`
- `/dashboard/teacher/sessions/<pk>/attendance/`
- `/dashboard/teacher/sessions/<pk>/progress/`
- `/dashboard/teacher/sessions/<pk>/edit/`
- `/dashboard/teacher/sessions/<pk>/delete/`
- `/dashboard/teacher/sessions/<pk>/remove-turn/<student_id>/`
- `/dashboard/teacher/sessions/<pk>/reorder-turns/`
- `/dashboard/teacher/sessions/<pk>/toggle-turns/`
- `/dashboard/teacher/sessions/<pk>/advance-status/`
- `/dashboard/teacher/lessons/<pk>/toggle/`
- `/dashboard/classroom/`
- `/dashboard/teacher/students/`
- `/dashboard/teacher/students/<pk>/progress/`
- `/dashboard/teacher/students/<student_id>/tasks/`
- `/dashboard/teacher/students/<student_id>/tasks/assign/`
- `/dashboard/teacher/tasks/<pk>/validate/`
- `/dashboard/teacher/tasks/<pk>/edit/`
- `/dashboard/teacher/tasks/<pk>/delete/`

Problem:

- The teacher's live workflow is split into session management, attendance, progress, turn queue, classroom, student roster, student progress, and tasks.

User Friction:

- Teacher starts from circle/session, jumps to attendance, jumps to progress, jumps to student progress/tasks, then returns to session.
- The live class mental model is one screen: roster, turns, attendance, evaluation, lesson scope, and meeting room.

Related Features:

- Circle
- CircleEnrollment
- Session
- SessionTurn
- Attendance
- ProgressLog
- ReviewHistory
- MemorizationRecord
- StudyTask
- SessionStudentNote
- SessionLessonToggle
- Classroom

Why They Belong Together:

- During class, every teacher action is attached to a circle, session, or student in that session.

Proposed Workspace:

- Canonical route: `/dashboard/teacher/circles/<circle_id>/`
- Tabs:
  - Today: next/current session, evaluation queue, alerts.
  - Roster: students, current position, weak flags, quick task assign.
  - Sessions: calendar/list, create/edit session in drawer.
  - Live Session: attendance, turn queue, classroom, lesson toggles, evaluation form.
  - Progress: student progress matrix and history.
  - Tasks: assigned work and validation queue.
  - Settings: circle metadata and schedule.
- Session routes become deep links into `?session=<id>&tab=live` or `?tab=sessions&session=<id>`.
- Student progress/tasks open in right inspector from roster row.

Pages Removed:

- Session manage, session detail, attendance, progress, edit/delete pages as primary screens.
- Teacher student task assign/edit/validate/delete pages as primary screens.
- Classroom standalone page as primary screen for teachers.

Navigation Removed:

- Teacher sidebar can collapse "Manage sessions", "Classroom", "Students", and "Tasks" into "Circle Workspace".

Clicks Saved:

- Live class flow: 6-12 clicks saved per session.
- Assign or validate a task from a student row: 3-5 clicks saved.
- Take attendance then evaluate: 3-4 clicks saved.

Scrolling Reduced:

- Roster table with sticky columns and side inspector replaces long per-student pages.
- Live session surface uses split panels.

Context Switching Reduced:

- Teacher can complete an entire class from one workspace.

Reusable Components:

- `CircleWorkspaceShell`
- `RosterTable`
- `StudentInspector`
- `LiveSessionPanel`
- `AttendanceGrid`
- `TurnQueue`
- `EvaluationForm`
- `TaskDrawer`
- `SessionCalendar`

Implementation Priority:

- P0. This is the highest-productivity teacher workflow and likely the most repeated operational path.

Estimated UX Improvement:

- Very high: 40-60% less navigation for live teaching.

### 5. Teacher Inbox and Requests Workspace

Current Structure:

- `/dashboard/teacher/requests/`
- `/dashboard/teacher/requests/create/`
- `/dashboard/teacher/announcements/`
- `/dashboard/teacher/notifications/`
- `/dashboard/teacher/review-requests/`
- `/dashboard/teacher/reschedule-requests/`
- `/dashboard/teacher/absence-justifications/`
- `/dashboard/teacher/absences/`
- `/dashboard/teacher/absences/create/`

Problem:

- Teacher decisions are scattered across many pages: respond to requests, schedule review, approve reschedule, approve absence justification, create absence, read announcements.

User Friction:

- Teacher must poll multiple pages to know what requires action.
- Requests that point to sessions or students do not open next to that context.

Related Features:

- SupportRequest
- ReviewRequest
- SessionRescheduleRequest
- Attendance.justification
- TeacherAbsence
- Announcement
- Notification

Why They Belong Together:

- They are action items and messages, not standalone product modules.

Proposed Workspace:

- Canonical route: `/dashboard/teacher/inbox/`
- Views:
  - Needs action
  - My requests
  - Student requests
  - Attendance issues
  - Announcements
  - Notifications
- Detail panel includes linked student/session/circle context.
- Approve/reject forms stay inline.

Pages Removed:

- Teacher requests, announcements, notifications, review requests, reschedule requests, absence justifications, absences, absence create as primary nav items.

Navigation Removed:

- Communication group shrinks from 8+ links to 1.

Clicks Saved:

- Daily triage: 8-15 clicks saved.
- Approve request with session context: 2-4 clicks saved.

Scrolling Reduced:

- Compact queue/list with filters replaces long isolated pages.

Context Switching Reduced:

- Action items open beside the relevant student/session context.

Reusable Components:

- Same inbox components from student/admin with role-specific filters.

Implementation Priority:

- P1.

Estimated UX Improvement:

- High: 35-50% less request triage effort.

### 6. Admin Operations Workspace

Current Structure:

- `/dashboard/admin/`
- `/dashboard/inscriptions/`
- `/dashboard/students/`
- `/dashboard/students/create/`
- `/dashboard/students/<pk>/`
- `/dashboard/teachers/`
- `/dashboard/teachers/create/`
- `/dashboard/teachers/<pk>/`
- `/dashboard/teachers/<pk>/edit/`
- `/dashboard/supervisors/`
- `/dashboard/supervisors/create/`
- `/dashboard/circles/`
- `/dashboard/circles/create/`
- `/dashboard/circles/<pk>/`
- `/dashboard/absences/`
- `/dashboard/absences/active/`
- `/dashboard/absences/<pk>/manage/`

Problem:

- People, enrollment, circle assignment, and teacher coverage are separated even though admin operations require comparing them.

User Friction:

- Admin jumps between users, inscriptions, circles, and absences to approve an account or fix coverage.
- Create/edit/detail pages interrupt list context.

Related Features:

- User
- Circle
- CircleEnrollment
- TeacherAbsence
- TeacherSubstitution
- SessionSubstitution
- Pending users

Why They Belong Together:

- Admin is managing operational capacity: who can teach, who is enrolled, which circle is covered, and which accounts need approval.

Proposed Workspace:

- Canonical route: `/dashboard/operations/`
- Sections:
  - Pending approvals: inline approve/reject drawer.
  - People: unified users table with role filter and inline create drawer.
  - Circles: circles table with occupancy, teacher, schedule, status.
  - Coverage: teacher absences, active substitutions, affected sessions.
  - Imports/exports: actions menu, not separate visual modules.
- Detail pages become inspectors:
  - User inspector: profile, roles, permissions, activity, enrollments, certificates.
  - Circle inspector: roster, sessions, teacher, schedule, reports.

Pages Removed:

- Create/edit/detail pages for students, teachers, supervisors, circles become drawers/inspectors.
- Absence active/manage pages become Coverage tab with detail drawer.

Navigation Removed:

- Admin management group shrinks from 8 primary links to 3: Operations, People, Circles.

Clicks Saved:

- Approve user and place into circle: 4-7 clicks saved.
- Manage absence/substitution: 3-6 clicks saved.
- Inspect teacher/student/circle relationship: 5-8 clicks saved.

Scrolling Reduced:

- Dense tables with sticky filters replace card/detail pages.

Context Switching Reduced:

- Admin keeps list context while editing details.

Reusable Components:

- `DataWorkspace`
- `FilterBar`
- `BulkActionBar`
- `UserInspector`
- `CircleInspector`
- `InlineCreateDrawer`
- `ExportMenu`

Implementation Priority:

- P2, after teacher/student high-frequency workflows.

Estimated UX Improvement:

- Medium-high: 25-40% less admin operational navigation.

### 7. Assessment and Recognition Workspace

Current Structure:

- Admin exams: list, create, detail, edit, delete, publish, approve all, reject marks, export.
- Teacher exams: list, grade, submit, export.
- Student exams: results.
- Certificates: admin list, generate, preview, revoke, notify, upload PDF; student own; teacher list/create.
- Reports exam results page.
- Student achievements page.

Problem:

- Exams, marks, certificates, achievements, and exam reports are different surfaces for the same recognition/evaluation lifecycle.

User Friction:

- Admin creates exam in one area, reviews reports elsewhere, generates certificates elsewhere.
- Teacher grades in a separate page from circle/student context.
- Student checks exam results, achievements, and certificates separately.

Related Features:

- Exam
- ExamMark
- ExamApprovalHistory
- ExamNotification
- Certificate
- CertificateTemplate
- StudentAchievement
- RecitationGrade

Why They Belong Together:

- They represent assessment, approval, publishing, and recognition.

Proposed Workspace:

- Canonical admin route: `/dashboard/assessments/`
- Tabs:
  - Exams
  - Grading approval
  - Results
  - Certificates
  - Templates
- Teacher grading opens from Circle Workspace or Assessments tab.
- Student "Results" contains exam results and certificates; achievements are removed or folded into progress summary.

Pages Removed:

- Exam create/edit/detail as standalone pages become drawers/panels.
- Certificate generate/revoke/upload/notify become actions in certificate row/detail panel.
- Student achievements page removed.
- Separate report exam results becomes Results tab.

Navigation Removed:

- Assessment/certificate/report links collapse into one role-appropriate destination.

Clicks Saved:

- Create/publish/approve exam: 4-8 clicks saved.
- Generate certificate from result: 4-6 clicks saved.
- Student checks outcomes: 2-4 clicks saved.

Scrolling Reduced:

- Results table with grouped rows replaces multiple result pages.

Context Switching Reduced:

- Assessment lifecycle stays inside one workspace.

Reusable Components:

- `AssessmentWorkspace`
- `ExamTable`
- `GradeEntryGrid`
- `ApprovalTimeline`
- `CertificateActions`
- `ResultSummary`

Implementation Priority:

- P2.

Estimated UX Improvement:

- Medium-high: 25-40% less assessment administration friction.

### 8. Reports Workspace Simplification

Current Structure:

- `/dashboard/reports/`
- `/dashboard/reports/data/`
- `/dashboard/reports/export/pdf/`
- `/dashboard/reports/export/excel/`
- `/dashboard/reports/csv/`
- `/dashboard/reports/exam-results/`
- Many report partials for hifz, murajaa, grades, attendance, teachers, circles.

Problem:

- Reports are chart/module-heavy and detached from operational workspaces that create the data.

User Friction:

- Admin has to leave operations/circle/student context to answer basic questions.
- Export actions are separate routes rather than actions on current report state.

Related Features:

- Attendance
- ProgressLog
- MemorizationRecord
- ExamMark
- Circle
- User
- Reports cache/utils

Why They Belong Together:

- Reports summarize workspace data and should be available both globally and contextually.

Proposed Workspace:

- Keep one `/dashboard/reports/` workspace.
- Convert reports to practical views:
  - Association report
  - Circle report
  - Teacher report
  - Student report
  - Assessment report
- Export menu uses current filters and report type.
- Embed contextual report widgets inside Circle, Student, Teacher, and Assessment workspaces.

Pages Removed:

- Separate data/export visual flows become API/action endpoints.
- Exam results report folds into Assessment Workspace.

Navigation Removed:

- Reports stays one nav item for admin/supervisor only.

Clicks Saved:

- Export filtered report: 2-3 clicks saved.
- Inspect report from circle/student: 3-6 clicks saved.

Scrolling Reduced:

- Replace stacked chart partials with tabbed report views and compact tables.

Context Switching Reduced:

- Reports are accessible where the data is used.

Reusable Components:

- `ReportWorkspace`
- `ReportFilterBar`
- `MetricStrip`
- `ReportTable`
- `ExportMenu`

Implementation Priority:

- P3.

Estimated UX Improvement:

- Medium: 20-30% less reporting friction.

### 9. Live Room and Webinar Consolidation

Current Structure:

- `/dashboard/classroom/`
- `/dashboard/classrooms/`
- `/dashboard/classrooms/join/<slug>/`
- `/dashboard/webinars/`
- `/dashboard/webinars/<pk>/watch/`
- `/dashboard/webinars/<pk>/speaker-room/`
- `/dashboard/webinars/manage/`
- `/dashboard/webinars/manage/create/`
- `/dashboard/webinars/manage/<pk>/`

Problem:

- Live rooms and webinars are related real-time participation flows but exposed as separate modules in all role sidebars.

User Friction:

- User must decide whether to use classroom, webinar, speaker room, watch page, or admin manage page before knowing the live state.

Related Features:

- Classroom rooms
- Jitsi embed
- Webinar
- Stream embed
- Speaker room
- Session meeting data

Why They Belong Together:

- They are all live participation or broadcast surfaces. The user intent is "join/watch/manage live event".

Proposed Workspace:

- Student/teacher: live room appears contextually inside Circle/Session Workspace.
- Admin: `/dashboard/live/` manages classrooms and webinars.
- Webinars list remains only for browsing live/replay events, not operational management.

Pages Removed:

- Classroom standalone removed from primary nav for students/teachers.
- Webinar manage create/detail become admin live workspace drawers.

Navigation Removed:

- One less global nav item for student/teacher.

Clicks Saved:

- Join class: 2 clicks saved.
- Manage webinar lifecycle: 2-4 clicks saved.

Scrolling Reduced:

- Live panels are embedded and state-driven.

Context Switching Reduced:

- Session and live room remain in the same context.

Reusable Components:

- `LiveEventCard`
- `JitsiPanel`
- `StreamPanel`
- `LiveStatusBadge`
- `SpeakerRoomActions`

Implementation Priority:

- P3.

Estimated UX Improvement:

- Medium: 15-25% less live-event confusion.

### 10. Reusable Component Consolidation

Current Structure:

- Repeated create/list/detail templates exist across students, teachers, supervisors, circles, announcements, notifications, requests, exams, certificates, webinars.
- Existing partials are useful but narrow: stat card, pagination, empty state, rows, confirm modal.

Problem:

- The UI system repeats page headers, table shells, filter bars, cards, status badges, forms, action menus, and detail layouts.

User Friction:

- Same concepts look and behave differently.
- Users relearn controls in every module.
- Developers add pages because reusable workspace primitives are missing.

Related Features:

- All list/detail/create/edit flows.

Why They Belong Together:

- They are not domain features; they are interaction patterns.

Proposed Workspace:

- Add shared components under `templates/dashboard/components/` or expand `templates/dashboard/partials/`:
  - `workspace_shell.html`
  - `workspace_tabs.html`
  - `page_toolbar.html`
  - `filter_bar.html`
  - `data_table.html`
  - `status_chip.html`
  - `action_menu.html`
  - `side_inspector.html`
  - `drawer_form.html`
  - `timeline.html`
  - `metric_strip.html`
  - `empty_state.html`
  - `confirm_modal.html`

Pages Removed:

- Component extraction enables removal of many create/edit/detail pages in later passes.

Navigation Removed:

- Indirect: drawers and inspectors replace destinations.

Clicks Saved:

- 1-3 clicks per create/edit/detail operation.

Scrolling Reduced:

- Dense shared layout and sticky action bars reduce repeated vertical page chrome.

Context Switching Reduced:

- Inline/drawer operations keep users inside workspace.

Reusable Components:

- This optimization creates the reusable component foundation for all others.

Implementation Priority:

- P0 as a technical enabler, but only build components while migrating the first real workspace.

Estimated UX Improvement:

- Medium directly, very high as an enabler.

## Route Transition Strategy

Do not break existing URLs immediately.

1. Build canonical workspace routes.
2. Update sidebar to point to workspace routes.
3. Keep old GET routes as redirects with tab/query mapping.
4. Keep POST/action endpoints as-is when useful.
5. Migrate templates gradually into workspace partials.
6. Remove old templates after redirect coverage and tests.

Suggested redirects:

- `/dashboard/student/memorization/` -> `/dashboard/student/learn/?tab=today`
- `/dashboard/progress/` -> `/dashboard/student/learn/?tab=quran-map`
- `/dashboard/estimator/` -> `/dashboard/student/learn/?tab=estimate`
- `/dashboard/student/tasks/` -> `/dashboard/student/learn/?tab=tasks`
- `/dashboard/student/stats/` -> `/dashboard/student/learn/?tab=history`
- `/dashboard/student/achievements/` -> `/dashboard/student/results/?tab=certificates`
- `/dashboard/student/review-requests/` -> `/dashboard/student/inbox/?type=review`
- `/dashboard/student/attendance/` -> `/dashboard/student/circles/<active>/?tab=attendance`
- `/dashboard/student/justifications/` -> `/dashboard/student/inbox/?type=attendance`
- `/dashboard/teacher/sessions/manage/` -> `/dashboard/teacher/circles/<active>/?tab=sessions`
- `/dashboard/teacher/sessions/<id>/attendance/` -> `/dashboard/teacher/circles/<circle>/?tab=live&session=<id>`
- `/dashboard/teacher/sessions/<id>/progress/` -> `/dashboard/teacher/circles/<circle>/?tab=live&session=<id>`
- `/dashboard/teacher/students/<id>/tasks/` -> `/dashboard/teacher/circles/<active>/?tab=roster&student=<id>&panel=tasks`
- `/dashboard/teacher/review-requests/` -> `/dashboard/teacher/inbox/?type=review`
- `/dashboard/teacher/reschedule-requests/` -> `/dashboard/teacher/inbox/?type=reschedule`
- `/dashboard/teacher/absence-justifications/` -> `/dashboard/teacher/inbox/?type=attendance`

## Implementation Priority Stack

P0:

- Shared workspace primitives created during first migration.
- Teacher Circle Workspace.
- Student Learning Workspace.

P1:

- Student Circle/Session Workspace.
- Student Inbox.
- Teacher Inbox.

P2:

- Admin Operations Workspace.
- Assessment and Recognition Workspace.

P3:

- Reports simplification.
- Live room/webinar consolidation.

## Stop Condition Check

After this consolidation:

- No student learning page exists outside My Learning except contextual results/circle participation.
- No teacher live-class action requires leaving Circle Workspace.
- No request/notification/announcement/justification lifecycle is split across separate nav items.
- No create/edit/detail page is a primary destination when a drawer or inspector can preserve list/workspace context.
- Reports exist globally only for cross-organization analysis and contextually inside relevant workspaces.
- Sidebar links describe tasks and workspaces, not database models.

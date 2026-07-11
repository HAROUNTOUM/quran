# URL Inventory

## Dashboard: Admin (`/dashboard/`)

| URL | View | Permission |
|-----|------|------------|
| `/dashboard/` | `admin_dashboard` | Admin |
| `/dashboard/users/table/` | `pending_users_table` | Admin |
| `/dashboard/users/<uuid:pk>/approve/` | `approve_user` | Admin |
| `/dashboard/students/` | `admin_students` | Admin |
| `/dashboard/students/create/` | `admin_student_create` | Admin |
| `/dashboard/students/export/pdf/` | `admin_students_export_pdf` | Admin |
| `/dashboard/students/export/excel/` | `admin_students_export_excel` | Admin |
| `/dashboard/teachers/` | `admin_teachers` | Admin |
| `/dashboard/teachers/create/` | `admin_teacher_create` | Admin |
| `/dashboard/teachers/export/pdf/` | `admin_teachers_export_pdf` | Admin |
| `/dashboard/teachers/export/excel/` | `admin_teachers_export_excel` | Admin |
| `/dashboard/supervisors/` | `admin_supervisors` | Admin |
| `/dashboard/supervisors/create/` | `admin_supervisor_create` | Admin |
| `/dashboard/circles/` | `admin_circles` | Admin |
| `/dashboard/circles/create/` | `admin_circle_create` | Admin |
| `/dashboard/circles/<int:pk>/` | `admin_circle_detail` | Admin |
| `/dashboard/circles/export/pdf/` | `admin_circles_export_pdf` | Admin |
| `/dashboard/circles/export/excel/` | `admin_circles_export_excel` | Admin |
| `/dashboard/inscriptions/export/pdf/` | `admin_inscriptions_export_pdf` | Admin |
| `/dashboard/inscriptions/export/excel/` | `admin_inscriptions_export_excel` | Admin |
| `/dashboard/requests/` | `admin_requests` | Admin |
| `/dashboard/requests/<int:pk>/` | `admin_request_detail` | Admin |
| `/dashboard/announcements/` | `admin_announcements` | Admin |
| `/dashboard/announcements/create/` | `admin_announcement_create` | Admin |
| `/dashboard/reports/` | `admin_reports` | Admin |
| `/dashboard/reports/data/` | `admin_report_data` | Admin |
| `/dashboard/reports/export/pdf/` | `admin_report_export_pdf` | Admin |
| `/dashboard/reports/export/excel/` | `admin_report_export_excel` | Admin |
| `/dashboard/absences/` | `admin_teacher_absences` | Admin |
| `/dashboard/absences/active/` | `admin_active_substitutions` | Admin |
| `/dashboard/absences/<int:pk>/manage/` | `admin_absence_manage` | Admin |
| `/dashboard/admin/notifications/` | `admin_notifications` | Admin |
| `/dashboard/admin/notifications/create/` | `admin_notification_create` | Admin |
| `/dashboard/exams/` | `admin_exam_list` | Admin |
| `/dashboard/exams/create/` | `admin_exam_create` | Admin |
| `/dashboard/exams/<int:pk>/` | `admin_exam_detail` | Admin |
| `/dashboard/exams/<int:pk>/edit/` | `admin_exam_edit` | Admin |
| `/dashboard/exams/<int:pk>/delete/` | `admin_exam_delete` | Admin |
| `/dashboard/exams/<int:pk>/publish/` | `admin_exam_publish` | Admin |
| `/dashboard/exams/<int:pk>/approve-all/` | `admin_exam_approve_all` | Admin |
| `/dashboard/exams/<int:pk>/reject-marks/` | `admin_exam_reject_marks` | Admin |
| `/dashboard/exams/<int:pk>/export/pdf/` | `admin_exam_export_pdf` | Admin |
| `/dashboard/exams/<int:pk>/export/csv/` | `admin_exam_export_csv` | Admin |
| `/dashboard/reports/exam-results/` | `report_exam_results` | Admin |
| `/dashboard/notifications/` | `notification_list` | Any auth'd |
| `/dashboard/notifications/<int:pk>/read/` | `notification_mark_read` | Any auth'd |
| `/dashboard/notifications/mark-all-read/` | `notification_mark_all_read` | Any auth'd |

## Dashboard: Teacher (`/dashboard/teacher/`)

| URL | View | Permission |
|-----|------|------------|
| `/dashboard/teacher/` | `teacher_dashboard` | Teacher |
| `/dashboard/teacher/circles/<int:pk>/` | `teacher_circle_detail` | Teacher |
| `/dashboard/teacher/students/` | `teacher_students` | Teacher |
| `/dashboard/teacher/students/<uuid:pk>/progress/` | `teacher_student_progress` | Teacher |
| `/dashboard/teacher/sessions/<int:pk>/attendance/` | `teacher_session_attendance` | Teacher |
| `/dashboard/teacher/circles/<int:circle_pk>/sessions/create/` | `teacher_session_create` | Teacher |
| `/dashboard/teacher/absences/` | `teacher_absence_list` | Teacher |
| `/dashboard/teacher/absences/create/` | `teacher_absence_create` | Teacher |
| `/dashboard/teacher/announcements/` | `teacher_announcements` | Teacher |
| `/dashboard/teacher/requests/` | `teacher_requests` | Teacher |
| `/dashboard/teacher/requests/create/` | `teacher_request_create` | Teacher |
| `/dashboard/teacher/notifications/` | `teacher_notifications` | Teacher |
| `/dashboard/teacher/sessions/manage/` | `teacher_session_manage` | Teacher |
| `/dashboard/teacher/sessions/<int:pk>/progress/` | `teacher_session_progress` | Teacher |
| `/dashboard/teacher/sessions/<int:pk>/edit/` | `teacher_session_edit` | Teacher |
| `/dashboard/teacher/sessions/<int:pk>/delete/` | `teacher_session_delete` | Teacher |
| `/dashboard/teacher/sessions/<int:pk>/` | `teacher_session_detail` | Teacher |
| `/dashboard/teacher/sessions/<int:pk>/remove-turn/<uuid:student_id>/` | `teacher_session_remove_turn` | Teacher |
| `/dashboard/teacher/sessions/<int:pk>/reorder-turns/` | `teacher_session_reorder_turns` | Teacher |
| `/dashboard/teacher/lessons/<int:pk>/toggle/` | `teacher_toggle_lesson` | Teacher |
| `/dashboard/teacher/review-requests/` | `teacher_review_requests` | Teacher |
| `/dashboard/teacher/reschedule-requests/` | `teacher_reschedule_requests` | Teacher |
| `/dashboard/teacher/absence-justifications/` | `teacher_absence_justifications` | Teacher |
| `/dashboard/teacher/exams/` | `teacher_exams` | Teacher |
| `/dashboard/teacher/exams/<int:pk>/grade/` | `teacher_exam_grade` | Teacher |
| `/dashboard/teacher/exams/<int:pk>/submit/` | `teacher_exam_submit` | Teacher |
| `/dashboard/teacher/exams/<int:pk>/export/pdf/` | `teacher_exam_export_pdf` | Teacher |

## Dashboard: Student (`/dashboard/student/`)

| URL | View | Permission |
|-----|------|------------|
| `/dashboard/student/` | `student_dashboard` | Student |
| `/dashboard/student/circles/` | `student_circles` | Student |
| `/dashboard/student/circles/<int:pk>/` | `student_circle_detail` | Student |
| `/dashboard/student/circles/<int:pk>/enroll/` | `student_enroll_circle` | Student |
| `/dashboard/student/circles/<int:pk>/unenroll/` | `student_unenroll` | Student |
| `/dashboard/student/memorization/` | `student_memorization` | Student |
| `/dashboard/student/attendance/` | `student_attendance` | Student |
| `/dashboard/student/sessions/` | `student_sessions` | Student |
| `/dashboard/student/sessions/<int:pk>/` | `student_session_detail` | Student |
| `/dashboard/student/sessions/<int:pk>/claim-turn/` | `student_claim_turn` | Student |
| `/dashboard/student/sessions/<int:pk>/release-turn/` | `student_release_turn` | Student |
| `/dashboard/student/review-requests/` | `student_review_requests` | Student |
| `/dashboard/student/review-requests/create/` | `student_review_request_create` | Student |
| `/dashboard/student/requests/` | `student_requests` | Student |
| `/dashboard/student/requests/create/` | `student_request_create` | Student |
| `/dashboard/student/requests/<int:pk>/` | `student_request_detail` | Student |
| `/dashboard/student/announcements/` | `student_announcements` | Student |
| `/dashboard/student/notifications/` | `student_notifications` | Student |
| `/dashboard/student/exams/` | `student_exam_results` | Student |
| `/dashboard/student/achievements/` | `student_achievements` | Student |
| `/dashboard/student/justifications/` | `student_justifications` | Student |

## Dashboard: Certificates (`/dashboard/certificates/`)

| URL | View | Permission |
|-----|------|------------|
| `/dashboard/certificates/` | `certificate_list` | Supervisor/Admin |
| `/dashboard/certificates/generate/` | `certificate_generate` | Supervisor/Admin |
| `/dashboard/certificates/<int:pk>/download/` | `certificate_download` | Supervisor/Admin/Teacher/Student |
| `/dashboard/certificates/<int:pk>/preview/` | `certificate_preview` | Supervisor/Admin |
| `/dashboard/certificates/<int:pk>/revoke/` | `certificate_revoke` | Supervisor/Admin |
| `/dashboard/certificates/<int:pk>/notify/` | `certificate_notify` | Supervisor/Admin |
| `/dashboard/certificates/<int:pk>/upload-pdf/` | `certificate_upload_pdf` | Supervisor/Admin |
| `/dashboard/certificates/own/` | `student_certificates` | Student |
| `/dashboard/certificates/teacher/` | `teacher_certificate_list` | Teacher |
| `/dashboard/certificates/teacher/create/` | `teacher_certificate_create` | Teacher |

## API v1 (`/api/v1/`)

| URL | View | Permission |
|-----|------|------------|
| `/api/v1/schema/` | `SpectacularAPIView` | Any |
| `/api/v1/docs/` | `SpectacularSwaggerView` | Any |
| `/api/v1/auth/login/` | `CustomTokenObtainView` | Any |
| `/api/v1/auth/refresh/` | `TokenRefreshView` | Any |
| `/api/v1/auth/logout/` | `LogoutView` | Auth'd |
| `/api/v1/auth/me/` | `MeView` | Auth'd |
| `/api/v1/auth/change-password/` | `ChangePasswordView` | Auth'd |
| `/api/v1/attendance/weekly-chart/` | `AttendanceChartView` | Auth'd |
| `/api/v1/attendance/general-trend/` | `AttendanceTrendView` | Auth'd |
| `/api/v1/grades/teacher-chart/` | `RecitationGradeViewSet` | Auth'd |
| `/api/v1/reports/dashboard-stats/` | `DashboardStatsView` | Auth'd |
| `/api/v1/reports/student-stats/` | `StudentStatsView` | Auth'd |
| `/api/v1/reports/teacher-stats/` | `TeacherStatsView` | Auth'd |
| `/api/v1/reports/urgent-alerts/` | `UrgentAlertsView` | Auth'd |
| `/api/v1/sessions/<int:session_id>/logs/` | `ProgressLogViewSet` | Auth'd |
| `/api/v1/dashboard/student-home/` | `StudentHomeView` | Student |
| `/api/v1/users/` | `UserViewSet` | Admin, crud |
| `/api/v1/users/stats/` | `UserViewSet` | Admin, stats |
| `/api/v1/users/<pk>/` | `UserViewSet` | Admin, detail |
| `/api/v1/registration/` | `RegistrationViewSet` | Any, list/admin |
| `/api/v1/registration/<pk>/` | `RegistrationViewSet` | Any, detail |
| `/api/v1/registration/<pk>/approve/` | `RegistrationViewSet` | Admin |
| `/api/v1/registration/<pk>/reject/` | `RegistrationViewSet` | Admin |
| `/api/v1/registration/bulk/` | `RegistrationViewSet` | Admin |
| `/api/v1/registration/stats/` | `RegistrationViewSet` | Admin |
| `/api/v1/circles/` | `CircleViewSet` | Auth'd, list |
| `/api/v1/circles/<pk>/` | `CircleViewSet` | Auth'd, detail |
| `/api/v1/circles/<pk>/enroll/` | `CircleViewSet` | Student |
| `/api/v1/circles/<pk>/remove_student/` | `CircleViewSet` | Teacher+ |
| `/api/v1/circles/<pk>/stats/` | `CircleViewSet` | Teacher+ |
| `/api/v1/circles/<pk>/students/` | `CircleViewSet` | Teacher+ |
| `/api/v1/sessions/` | `SessionViewSet` | Auth'd, scoped |
| `/api/v1/sessions/<pk>/` | `SessionViewSet` | Auth'd, detail |
| `/api/v1/sessions/<pk>/attendance/` | `SessionViewSet` | Teacher+ |
| `/api/v1/sessions/<pk>/attendance-intent/` | `SessionViewSet` | Student |
| `/api/v1/sessions/<pk>/join-link/` | `SessionViewSet` | Auth'd |
| `/api/v1/sessions/<pk>/reschedule/` | `SessionViewSet` | Teacher |
| `/api/v1/sessions/<pk>/submit_attendance/` | `SessionViewSet` | Teacher |
| `/api/v1/attendance/<pk>/` | `AttendanceViewSet` | Auth'd, scoped |
| `/api/v1/grades/` | `RecitationGradeViewSet` | Auth'd, scoped |
| `/api/v1/grades/<pk>/` | `RecitationGradeViewSet` | Auth'd, detail |
| `/api/v1/grades/teacher_chart/` | `RecitationGradeViewSet` | Auth'd |
| `/api/v1/justifications/` | `AbsenceJustificationViewSet` | Auth'd, scoped |
| `/api/v1/justifications/<pk>/approve/` | `AbsenceJustificationViewSet` | Teacher+ |
| `/api/v1/justifications/<pk>/reject/` | `AbsenceJustificationViewSet` | Teacher+ |
| `/api/v1/requests/` | `RequestViewSet` | Auth'd, scoped |
| `/api/v1/requests/<pk>/` | `RequestViewSet` | Auth'd, scoped |
| `/api/v1/requests/<pk>/comments/` | `RequestViewSet` | Auth'd, scoped |
| `/api/v1/announcements/` | `AnnouncementViewSet` | Auth'd |
| `/api/v1/announcements/<pk>/` | `AnnouncementViewSet` | Auth'd |
| `/api/v1/notifications/` | `NotificationViewSet` | Auth'd, own |
| `/api/v1/notifications/count/` | `NotificationViewSet` | Auth'd, own |
| `/api/v1/notifications/mark_all_read/` | `NotificationViewSet` | Auth'd, own |
| `/api/v1/notifications/<pk>/read/` | `NotificationViewSet` | Auth'd, own |
| `/api/v1/exams/` | `ExamViewSet` | Auth'd, scoped |
| `/api/v1/exams/<pk>/` | `ExamViewSet` | Auth'd, detail |
| `/api/v1/exams/<pk>/grade/` | `ExamViewSet` | Teacher |
| `/api/v1/exams/<pk>/marks/` | `ExamViewSet` | Teacher+ |
| `/api/v1/exams/<pk>/approve/` | `ExamViewSet` | Supervisor+ |
| `/api/v1/exams/<pk>/publish/` | `ExamViewSet` | Supervisor+ |
| `/api/v1/exams/<pk>/reject_marks/` | `ExamViewSet` | Supervisor+ |
| `/api/v1/exams/<pk>/submit_approval/` | `ExamViewSet` | Teacher |
| `/api/v1/review-requests/` | `ReviewRequestViewSet` | Auth'd, scoped |
| `/api/v1/review-requests/<pk>/` | `ReviewRequestViewSet` | Auth'd, scoped |
| `/api/v1/review-requests/<pk>/approve/` | `ReviewRequestViewSet` | Supervisor+ |
| `/api/v1/review-requests/<pk>/reject/` | `ReviewRequestViewSet` | Supervisor+ |
| `/api/v1/notes/` | `SessionStudentNoteViewSet` | Teacher+ |
| `/api/v1/notes/<pk>/` | `SessionStudentNoteViewSet` | Teacher+ |
| `/api/v1/memorization-progress/` | `MemorizationProgressViewSet` | Auth'd, scoped |
| `/api/v1/memorization-progress/<pk>/` | `MemorizationProgressViewSet` | Auth'd, scoped |
| `/api/v1/surahs/` | `SurahViewSet` | Auth'd |
| `/api/v1/surahs/<pk>/` | `SurahViewSet` | Auth'd |
| `/api/v1/evaluation-criteria/` | `EvaluationCriterionViewSet` | Auth'd |
| `/api/v1/evaluation-criteria/<pk>/` | `EvaluationCriterionViewSet` | Auth'd |
| `/api/v1/progress-logs/` | `ProgressLogViewSet` | Auth'd, scoped |
| `/api/v1/progress-logs/<pk>/` | `ProgressLogViewSet` | Auth'd, scoped |
| `/api/v1/lesson-toggles/` | `SessionLessonToggleViewSet` | Auth'd, scoped |
| `/api/v1/lesson-toggles/<pk>/` | `SessionLessonToggleViewSet` | Auth'd, scoped |
| `/api/v1/reschedule-requests/` | `SessionRescheduleViewSet` | Auth'd, scoped |
| `/api/v1/reschedule-requests/<pk>/` | `SessionRescheduleViewSet` | Auth'd, scoped |
| `/api/v1/reschedule-requests/<pk>/approve/` | `SessionRescheduleViewSet` | Supervisor+ |
| `/api/v1/reschedule-requests/<pk>/reject/` | `SessionRescheduleViewSet` | Supervisor+ |
| `/api/v1/turns/` | `SessionTurnViewSet` | Auth'd, scoped |
| `/api/v1/turns/claim/` | `SessionTurnViewSet` | Student |
| `/api/v1/turns/release/` | `SessionTurnViewSet` | Student |
| `/api/v1/turns/remove/` | `SessionTurnViewSet` | Teacher |
| `/api/v1/turns/reorder/` | `SessionTurnViewSet` | Teacher |
| `/api/v1/certificates/` | `CertificateViewSet` | Auth'd, scoped |
| `/api/v1/certificates/<pk>/` | `CertificateViewSet` | Auth'd, scoped |

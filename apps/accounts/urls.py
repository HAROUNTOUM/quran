from django.contrib.auth import views as auth_views
from django.urls import path
from . import views

app_name = "accounts"

urlpatterns = [
    path("", views.landing_page, name="landing"),
    path("login/", views.login_view, name="login"),
    path("signup/", views.signup_view, name="signup"),
    path("logout/", views.logout_view, name="logout"),
    path("verify-email/<str:token>/", views.verify_email_view, name="verify_email"),
    path("resend-verification/", views.resend_verification_view, name="resend_verification"),

    # Password reset (code-based)
    path("password-reset/", views.password_reset_request_view, name="password_reset"),
    path("password-reset/verify/", views.password_reset_verify_view, name="password_reset_verify"),
    path("password-reset/set/", views.password_reset_set_view, name="password_reset_set"),
    path("password-reset/complete/", auth_views.PasswordResetCompleteView.as_view(
        template_name="registration/password_reset_complete.html",
    ), name="password_reset_complete"),

    path("dashboard/", views.dashboard_redirect, name="dashboard"),
    path("dashboard/admin/", views.admin_dashboard, name="admin_dashboard"),
    path("dashboard/profile/", views.profile_view, name="profile"),
    path("dashboard/profile/edit/", views.profile_edit_view, name="profile_edit"),
    path("dashboard/inscriptions/", views.admin_inscriptions, name="admin_inscriptions"),
    path("dashboard/students/", views.admin_students, name="admin_students"),
    path("dashboard/students/create/", views.admin_student_create, name="admin_student_create"),
    path("dashboard/students/<uuid:pk>/", views.admin_student_detail, name="admin_student_detail"),
    path("dashboard/students/<uuid:pk>/edit/", views.admin_student_edit, name="admin_student_edit"),
    path("dashboard/students/<uuid:pk>/toggle-status/", views.admin_student_toggle_status, name="admin_student_toggle_status"),
    path("dashboard/students/export/pdf/", views.admin_students_export_pdf, name="admin_students_export_pdf"),
    path("dashboard/students/export/excel/", views.admin_students_export_excel, name="admin_students_export_excel"),

    path("dashboard/teachers/", views.admin_teachers, name="admin_teachers"),
    path("dashboard/teachers/create/", views.admin_teacher_create, name="admin_teacher_create"),
    path("dashboard/teachers/<uuid:pk>/edit/", views.admin_teacher_edit, name="admin_teacher_edit"),
    path("dashboard/teachers/<uuid:pk>/", views.admin_teacher_detail, name="admin_teacher_detail"),
    path("dashboard/teachers/<uuid:pk>/toggle-status/", views.admin_teacher_toggle_status, name="admin_teacher_toggle_status"),
    path("dashboard/teachers/export/pdf/", views.admin_teachers_export_pdf, name="admin_teachers_export_pdf"),
    path("dashboard/teachers/export/excel/", views.admin_teachers_export_excel, name="admin_teachers_export_excel"),

    path("dashboard/supervisors/", views.admin_supervisors, name="admin_supervisors"),
    path("dashboard/supervisors/create/", views.admin_supervisor_create, name="admin_supervisor_create"),
    path("dashboard/supervisors/<uuid:pk>/edit/", views.admin_supervisor_edit, name="admin_supervisor_edit"),

    path("dashboard/circles/", views.admin_circles, name="admin_circles"),
    path("dashboard/circles/create/", views.admin_circle_create, name="admin_circle_create"),
    path("dashboard/circles/<int:pk>/", views.admin_circle_detail, name="admin_circle_detail"),
    path("dashboard/circles/export/pdf/", views.admin_circles_export_pdf, name="admin_circles_export_pdf"),
    path("dashboard/circles/export/excel/", views.admin_circles_export_excel, name="admin_circles_export_excel"),
    path("dashboard/inscriptions/export/pdf/", views.admin_inscriptions_export_pdf, name="admin_inscriptions_export_pdf"),
    path("dashboard/inscriptions/export/excel/", views.admin_inscriptions_export_excel, name="admin_inscriptions_export_excel"),

    path("dashboard/requests/", views.admin_requests, name="admin_requests"),
    path("dashboard/requests/<int:pk>/", views.admin_request_detail, name="admin_request_detail"),
    path("dashboard/announcements/", views.admin_announcements, name="admin_announcements"),
    path("dashboard/announcements/create/", views.admin_announcement_create, name="admin_announcement_create"),
    path("dashboard/supervisor/groups/", views.supervisor_groups, name="supervisor_groups"),
    path("dashboard/supervisor/groups/<int:pk>/", views.supervisor_group_board, name="supervisor_group_board"),
    path("dashboard/reports/", views.admin_reports, name="admin_reports"),
    path("dashboard/reports/data/", views.admin_report_data, name="admin_report_data"),
    path("dashboard/reports/export/pdf/", views.admin_report_export_pdf, name="admin_report_export_pdf"),
    path("dashboard/reports/export/excel/", views.admin_report_export_excel, name="admin_report_export_excel"),

    path("dashboard/users/<uuid:pk>/approve/", views.approve_user, name="approve_user"),
    path("dashboard/users/table/", views.pending_users_table, name="users_table"),
    path("dashboard/notifications/", views.notification_list, name="notification_list"),
    path("dashboard/notifications/<int:pk>/read/", views.notification_mark_read, name="notification_mark_read"),
    path("dashboard/admin/notifications/", views.admin_notifications, name="admin_notifications"),
    path("dashboard/admin/private-sessions/", views.admin_private_sessions, name="admin_private_sessions"),
    path("dashboard/admin/notifications/create/", views.admin_notification_create, name="admin_notification_create"),

    # Teacher pages
    path("dashboard/teacher/", views.teacher_dashboard, name="teacher_dashboard"),
    path("dashboard/teacher/circles/<int:pk>/", views.teacher_circle_detail, name="teacher_circle_detail"),
    path("dashboard/teacher/students/", views.teacher_students, name="teacher_students"),
    path("dashboard/teacher/students/<uuid:pk>/progress/", views.teacher_student_progress, name="teacher_student_progress"),
    path("dashboard/teacher/students/<uuid:student_id>/tasks/", views.teacher_student_tasks, name="teacher_student_tasks"),
    path("dashboard/teacher/students/<uuid:student_id>/tasks/assign/", views.teacher_task_assign, name="teacher_task_assign"),
    path("dashboard/teacher/tasks/<int:pk>/validate/", views.teacher_task_validate, name="teacher_task_validate"),
    path("dashboard/teacher/tasks/<int:pk>/edit/", views.teacher_task_edit, name="teacher_task_edit"),
    path("dashboard/teacher/tasks/<int:pk>/delete/", views.teacher_task_delete, name="teacher_task_delete"),
    path("dashboard/teacher/sessions/<int:pk>/log-progress/", views.teacher_session_log_progress, name="teacher_session_log_progress"),
    path("dashboard/teacher/progress-logs/<int:pk>/edit/", views.teacher_progress_log_edit, name="teacher_progress_log_edit"),
    path("dashboard/teacher/progress-logs/<int:pk>/delete/", views.teacher_progress_log_delete, name="teacher_progress_log_delete"),
    path("dashboard/teacher/students/<uuid:student_id>/records/add/", views.teacher_record_add, name="teacher_record_add"),
    path("dashboard/teacher/students/<uuid:student_id>/records/<int:record_pk>/evaluate/", views.teacher_record_evaluate, name="teacher_record_evaluate"),
    path("dashboard/teacher/sessions/<int:pk>/attendance/", views.teacher_session_attendance, name="teacher_session_attendance"),
    path("dashboard/teacher/circles/<int:circle_pk>/sessions/create/", views.teacher_session_create, name="teacher_session_create"),
    path("dashboard/teacher/absences/", views.teacher_absence_list, name="teacher_absence_list"),
    path("dashboard/teacher/absences/create/", views.teacher_absence_create, name="teacher_absence_create"),
    path("dashboard/teacher/announcements/", views.teacher_announcements, name="teacher_announcements"),
    path("dashboard/teacher/requests/", views.teacher_requests, name="teacher_requests"),
    path("dashboard/teacher/requests/create/", views.teacher_request_create, name="teacher_request_create"),
    path("dashboard/teacher/notifications/", views.teacher_notifications, name="teacher_notifications"),
    path("dashboard/teacher/sessions/manage/", views.teacher_session_manage, name="teacher_session_manage"),
    path("dashboard/teacher/sessions/<int:pk>/progress/", views.teacher_session_progress, name="teacher_session_progress"),
    path("dashboard/teacher/sessions/<int:pk>/edit/", views.teacher_session_edit, name="teacher_session_edit"),
    path("dashboard/teacher/sessions/<int:pk>/delete/", views.teacher_session_delete, name="teacher_session_delete"),
    path("dashboard/teacher/sessions/<int:pk>/", views.teacher_session_detail, name="teacher_session_detail"),
    path("dashboard/teacher/sessions/<int:pk>/remove-turn/<uuid:student_id>/", views.teacher_session_remove_turn, name="teacher_session_remove_turn"),
    path("dashboard/teacher/sessions/<int:pk>/reorder-turns/", views.teacher_session_reorder_turns, name="teacher_session_reorder_turns"),
    path("dashboard/teacher/sessions/<int:pk>/toggle-turns/", views.teacher_session_toggle_turns, name="teacher_session_toggle_turns"),
    path("dashboard/teacher/sessions/<int:pk>/advance-status/", views.teacher_session_advance_status, name="teacher_session_advance_status"),
    path("dashboard/teacher/review-requests/", views.teacher_review_requests, name="teacher_review_requests"),
    path("dashboard/teacher/private-sessions/", views.teacher_private_sessions, name="teacher_private_sessions"),
    path("dashboard/teacher/webinars/", views.teacher_webinars, name="teacher_webinars"),
    path("dashboard/teacher/reschedule-requests/", views.teacher_reschedule_requests, name="teacher_reschedule_requests"),
    path("dashboard/teacher/absence-justifications/", views.teacher_absence_justifications, name="teacher_absence_justifications"),
    # Admin: Absences
    path("dashboard/absences/", views.admin_teacher_absences, name="admin_teacher_absences"),
    path("dashboard/absences/active/", views.admin_active_substitutions, name="admin_active_substitutions"),
    path("dashboard/absences/<int:pk>/manage/", views.admin_absence_manage, name="admin_absence_manage"),

    # Student pages
    path("dashboard/student/", views.student_dashboard, name="student_dashboard"),
    path("dashboard/student/circles/", views.student_circles, name="student_circles"),
    path("dashboard/student/circles/<int:pk>/", views.student_circle_detail, name="student_circle_detail"),
    path("dashboard/student/circles/<int:pk>/enroll/", views.student_enroll_circle, name="student_enroll_circle"),
    path("dashboard/student/memorization/", views.student_memorization, name="student_memorization"),
    path("dashboard/student/attendance/", views.student_attendance, name="student_attendance"),
    path("dashboard/student/sessions/", views.student_sessions, name="student_sessions"),
    path("dashboard/student/sessions/<int:pk>/", views.student_session_detail, name="student_session_detail"),
    path("dashboard/student/sessions/<int:pk>/confirm-attendance/", views.student_confirm_attendance, name="student_confirm_attendance"),
    path("dashboard/student/sessions/<int:pk>/claim-turn/", views.student_claim_turn, name="student_claim_turn"),
    path("dashboard/student/sessions/<int:pk>/release-turn/", views.student_release_turn, name="student_release_turn"),
    path("dashboard/student/tasks/", views.student_tasks, name="student_tasks"),
    path("dashboard/student/tasks/<int:pk>/done/", views.student_task_mark_done, name="student_task_mark_done"),
    path("dashboard/student/review-requests/", views.student_review_requests, name="student_review_requests"),
    path("dashboard/student/review-requests/create/", views.student_review_request_create, name="student_review_request_create"),
    path("dashboard/student/private-sessions/", views.student_private_sessions, name="student_private_sessions"),

    # Exam results
    path("dashboard/reports/exam-results/", views.report_exam_results, name="report_exam_results"),

    # Admin exams
    path("dashboard/exams/", views.admin_exam_list, name="admin_exam_list"),
    path("dashboard/exams/create/", views.admin_exam_create, name="admin_exam_create"),
    path("dashboard/exams/<int:pk>/", views.admin_exam_detail, name="admin_exam_detail"),
    path("dashboard/exams/<int:pk>/edit/", views.admin_exam_edit, name="admin_exam_edit"),
    path("dashboard/exams/<int:pk>/delete/", views.admin_exam_delete, name="admin_exam_delete"),
    path("dashboard/exams/<int:pk>/publish/", views.admin_exam_publish, name="admin_exam_publish"),
    path("dashboard/exams/<int:pk>/approve-all/", views.admin_exam_approve_all, name="admin_exam_approve_all"),
    path("dashboard/exams/<int:pk>/reject-marks/", views.admin_exam_reject_marks, name="admin_exam_reject_marks"),
    path("dashboard/exams/<int:pk>/export/pdf/", views.admin_exam_export_pdf, name="admin_exam_export_pdf"),
    path("dashboard/exams/<int:pk>/export/csv/", views.admin_exam_export_csv, name="admin_exam_export_csv"),

    # Teacher exams
    path("dashboard/teacher/exams/", views.teacher_exams, name="teacher_exams"),
    path("dashboard/teacher/exams/<int:pk>/grade/", views.teacher_exam_grade, name="teacher_exam_grade"),
    path("dashboard/teacher/exams/<int:pk>/submit/", views.teacher_exam_submit, name="teacher_exam_submit"),
    path("dashboard/teacher/exams/<int:pk>/export/pdf/", views.teacher_exam_export_pdf, name="teacher_exam_export_pdf"),

    path("dashboard/student/requests/", views.student_requests, name="student_requests"),
    path("dashboard/student/announcements/", views.student_announcements, name="student_announcements"),
    path("dashboard/student/notifications/", views.student_notifications, name="student_notifications"),

    # Student exams
    path("dashboard/student/exams/", views.student_exam_results, name="student_exam_results"),

    # Student unified stats
    path("dashboard/student/stats/", views.student_stats, name="student_stats"),

    # Student achievements, request detail, unenroll, justifications
    path("dashboard/student/achievements/", views.student_achievements, name="student_achievements"),
    path("dashboard/student/requests/<int:pk>/", views.student_request_detail, name="student_request_detail"),
    path("dashboard/student/circles/<int:pk>/unenroll/", views.student_unenroll, name="student_unenroll"),
    path("dashboard/student/justifications/", views.student_justifications, name="student_justifications"),
    path("dashboard/student/sessions/<int:pk>/reschedule/", views.student_request_reschedule, name="student_request_reschedule"),
    path("dashboard/student/reschedule-requests/", views.student_reschedule_requests, name="student_reschedule_requests"),
    path("dashboard/student/circles/<int:pk>/leaderboard/", views.student_circle_leaderboard, name="student_circle_leaderboard"),

    # Platform-wide leaderboard
    path("dashboard/student/leaderboard/", views.student_leaderboard, name="student_leaderboard"),

    # Mark all notifications read
    path("dashboard/notifications/mark-all-read/", views.notification_mark_all_read, name="notification_mark_all_read"),

    # Batch management
    path("dashboard/batches/", views.admin_batch_list, name="admin_batch_list"),
    path("dashboard/batches/create/", views.admin_batch_create, name="admin_batch_create"),
    path("dashboard/batches/<int:pk>/", views.admin_batch_detail, name="admin_batch_detail"),
    path("dashboard/batches/<int:pk>/circles/", views.admin_batch_circles, name="admin_batch_circles"),
    path("dashboard/batches/<int:pk>/edit/", views.admin_batch_edit, name="admin_batch_edit"),
    path("dashboard/batches/<int:pk>/toggle-status/", views.admin_batch_toggle_status, name="admin_batch_toggle_status"),
]

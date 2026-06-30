from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

router = DefaultRouter()
router.register(r"users", views.UserViewSet, basename="user")
router.register(r"registration", views.RegistrationViewSet, basename="registration")
router.register(r"circles", views.CircleViewSet, basename="circle")
router.register(r"sessions", views.SessionViewSet, basename="session")
router.register(r"attendance", views.AttendanceViewSet, basename="attendance")
router.register(r"grades", views.RecitationGradeViewSet, basename="grade")
router.register(r"justifications", views.AbsenceJustificationViewSet, basename="justification")
router.register(r"requests", views.RequestViewSet, basename="request")
router.register(r"announcements", views.AnnouncementViewSet, basename="announcement")
router.register(r"notifications", views.NotificationViewSet, basename="notification")
router.register(r"exams", views.ExamViewSet, basename="exam")
router.register(r"review-requests", views.ReviewRequestViewSet, basename="review_request")
router.register(r"notes", views.SessionStudentNoteViewSet, basename="note")
router.register(r"memorization-progress", views.MemorizationProgressViewSet, basename="memorization")
router.register(r"surahs", views.SurahViewSet, basename="surah")
router.register(r"evaluation-criteria", views.EvaluationCriterionViewSet, basename="evaluation_criterion")
router.register(r"progress-logs", views.ProgressLogViewSet, basename="progress_log")
router.register(r"lesson-toggles", views.SessionLessonToggleViewSet, basename="lesson_toggle")
router.register(r"reschedule-requests", views.SessionRescheduleViewSet, basename="reschedule_request")

urlpatterns = [
    # Auth
    path("auth/login/", views.CustomTokenObtainView.as_view(), name="auth_login"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="auth_refresh"),
    path("auth/logout/", views.LogoutView.as_view(), name="auth_logout"),
    path("auth/me/", views.MeView.as_view(), name="auth_me"),
    path("auth/change-password/", views.ChangePasswordView.as_view(), name="auth_change_password"),

    # Attendance charts
    path("attendance/weekly-chart/", views.AttendanceChartView.as_view(), name="attendance_weekly_chart"),
    path("attendance/general-trend/", views.AttendanceTrendView.as_view(), name="attendance_general_trend"),

    # Grade chart
    path("grades/teacher-chart/", views.RecitationGradeViewSet.as_view({"get": "teacher_chart"}), name="grade_teacher_chart"),

    # Reports
    path("reports/dashboard-stats/", views.DashboardStatsView.as_view(), name="report_dashboard_stats"),
    path("reports/student-stats/", views.StudentStatsView.as_view(), name="report_student_stats"),
    path("reports/teacher-stats/", views.TeacherStatsView.as_view(), name="report_teacher_stats"),
    path("reports/urgent-alerts/", views.UrgentAlertsView.as_view(), name="report_urgent_alerts"),

    # Session progress logs (nested under session)
    path("sessions/<int:session_id>/logs/", views.ProgressLogViewSet.as_view({"post": "create"}), name="session_progress_logs"),

    # DRF router
    path("", include(router.urls)),
]

from django.contrib import admin

from apps.attendance.models import Attendance, SessionAttendanceIntent


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = [
        "student", "session", "status", "justification_status",
        "justification", "teacher_comment", "reviewed_by", "reviewed_at",
    ]
    list_filter = ["status", "justification_status", "reviewed_by"]
    search_fields = [
        "student__full_name_ar", "student__email",
        "session__circle__name", "justification",
    ]
    raw_id_fields = ["student", "session", "reviewed_by"]
    readonly_fields = ["created_at", "updated_at", "reviewed_at"]
    date_hierarchy = "session__session_date"


@admin.register(SessionAttendanceIntent)
class SessionAttendanceIntentAdmin(admin.ModelAdmin):
    list_display = ["student", "session", "intent", "reason", "created_at"]
    list_filter = ["intent"]
    search_fields = ["student__full_name_ar", "reason"]

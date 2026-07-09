from django.contrib import admin

from apps.webinars.models import Webinar


@admin.register(Webinar)
class WebinarAdmin(admin.ModelAdmin):
    list_display = ("title", "status", "scheduled_at", "created_by", "is_active")
    date_hierarchy = "scheduled_at"
    list_filter = ("status", "is_active")
    search_fields = ("title", "description")
    filter_horizontal = ("co_speakers",)
    readonly_fields = ("speaker_room_name", "started_at", "ended_at", "created_at", "updated_at")

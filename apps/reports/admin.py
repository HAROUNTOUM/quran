from django.contrib import admin

from .models import SavedReport


@admin.register(SavedReport)
class SavedReportAdmin(admin.ModelAdmin):
    list_display = ("title", "report_type", "created_by", "format", "is_scheduled", "last_generated", "created_at")
    list_filter = ("report_type", "format", "is_scheduled")
    search_fields = ("title",)
    date_hierarchy = "created_at"

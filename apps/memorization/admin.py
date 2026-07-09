from django.contrib import admin

from .models import MemorizationRecord, ReviewHistory, StudyTask


class ReviewHistoryInline(admin.TabularInline):
    model = ReviewHistory
    extra = 0
    can_delete = False
    readonly_fields = (
        "reviewer", "evaluation", "mistakes_count", "previous_interval",
        "new_interval", "previous_status", "new_status", "created_at",
    )

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(MemorizationRecord)
class MemorizationRecordAdmin(admin.ModelAdmin):
    list_display = (
        "student", "rub", "status", "next_review_date",
        "review_interval_days", "review_count",
    )
    list_filter = ("status", "circle")
    search_fields = ("student__full_name_ar",)
    raw_id_fields = ("student", "rub", "circle")
    list_select_related = ("student", "rub")
    inlines = [ReviewHistoryInline]
    date_hierarchy = "next_review_date"


@admin.register(ReviewHistory)
class ReviewHistoryAdmin(admin.ModelAdmin):
    list_display = ("record", "reviewer", "evaluation", "mistakes_count", "created_at")
    list_filter = ("evaluation",)
    search_fields = ("record__student__full_name_ar",)
    raw_id_fields = ("record", "reviewer", "session")
    readonly_fields = ("created_at",)


@admin.register(StudyTask)
class StudyTaskAdmin(admin.ModelAdmin):
    list_display = ("student", "task_type", "surah", "ayah_from", "ayah_to", "status", "created_at")
    list_filter = ("status", "task_type")
    search_fields = ("student__full_name_ar", "surah__name_ar")
    raw_id_fields = ("student", "assigned_by", "surah")
    list_select_related = ("student", "surah")
    date_hierarchy = "created_at"

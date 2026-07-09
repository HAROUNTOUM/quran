from django.contrib import admin

from apps.classrooms.models import TeacherRoom


@admin.register(TeacherRoom)
class TeacherRoomAdmin(admin.ModelAdmin):
    list_display = ("teacher", "slug", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("teacher__full_name_ar", "teacher__email", "slug")
    raw_id_fields = ("teacher",)
    readonly_fields = ("slug", "room_name", "created_at", "updated_at")

from django.contrib import admin

from apps.usersettings.models import (
    SettingsChangeHistory, SystemSettings, UserSettings,
)


@admin.register(UserSettings)
class UserSettingsAdmin(admin.ModelAdmin):
    list_display = ("user", "updated_at")
    search_fields = ("user__full_name_ar", "user__email")
    raw_id_fields = ("user",)


@admin.register(SystemSettings)
class SystemSettingsAdmin(admin.ModelAdmin):
    list_display = ("__str__", "updated_at")

    def has_add_permission(self, request):
        # Singleton — only the pk=1 row created via load()
        from apps.usersettings.models import SystemSettings
        return not SystemSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SettingsChangeHistory)
class SettingsChangeHistoryAdmin(admin.ModelAdmin):
    list_display = ("key", "user", "changed_by", "is_critical", "created_at")
    list_filter = ("is_critical", "key")
    search_fields = ("key", "user__full_name_ar", "changed_by__full_name_ar")
    date_hierarchy = "created_at"

    # Audit log is append-only, written by code paths — never hand-edited.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

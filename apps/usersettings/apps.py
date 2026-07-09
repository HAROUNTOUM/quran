from django.apps import AppConfig


class UserSettingsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.usersettings"
    verbose_name = "الإعدادات"

    def ready(self):
        import apps.usersettings.signals  # noqa

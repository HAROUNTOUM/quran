from django.apps import AppConfig


class ClassroomsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.classrooms"
    verbose_name = "القاعات الافتراضية"

    def ready(self):
        import apps.classrooms.signals  # noqa

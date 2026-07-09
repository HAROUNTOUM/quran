from django.apps import AppConfig


class MemorizationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.memorization"
    verbose_name = "الحفظ والمراجعة"

    def ready(self):
        import apps.memorization.signals  # noqa

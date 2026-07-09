from django.apps import AppConfig


class CirclesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.circles"
    verbose_name = "الحلقات"

    def ready(self):
        import apps.circles.signals  # noqa

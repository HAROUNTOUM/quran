from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.usersettings.models import UserSettings


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_settings(sender, instance, created, **kwargs):
    """Section I: every user gets a settings row at creation."""
    if created:
        UserSettings.objects.get_or_create(user=instance)

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.classrooms.models import TeacherRoom


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def provision_teacher_room(sender, instance, created, **kwargs):
    """Section I: every teacher gets a permanent room. Fires on creation and
    also covers role changes to teacher on later saves (idempotent)."""
    if instance.role == "teacher":
        TeacherRoom.get_or_create_for(instance)

from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.conf import settings


@receiver(pre_save, sender=settings.AUTH_USER_MODEL)
def set_email_as_username(sender, instance, **kwargs):
    if instance.email and instance.email != instance.username:
        instance.username = instance.email


@receiver(pre_save, sender=settings.AUTH_USER_MODEL)
def ensure_admin_approved(sender, instance, **kwargs):
    if instance.pk is None and instance.role in (
        instance.__class__.Role.ADMIN,
        instance.__class__.Role.SUPERVISOR,
    ):
        instance.is_approved = instance.__class__.ApprovalStatus.APPROVED

from django.db.models.signals import pre_save
from django.dispatch import receiver

from apps.circles.models import SessionRescheduleRequest


@receiver(pre_save, sender=SessionRescheduleRequest)
def validate_reschedule_relationships(sender, instance, **kwargs):
    """Creation-only integrity backstop (Section I): catches programmatic
    creates that bypass forms. Logic lives on the model, not here."""
    if instance.pk is None:
        instance.validate_relationships()

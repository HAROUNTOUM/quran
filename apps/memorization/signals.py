from django.db.models.signals import pre_save
from django.dispatch import receiver

from apps.memorization.models import ReviewRequest


@receiver(pre_save, sender=ReviewRequest)
def validate_review_request_relationships(sender, instance, **kwargs):
    """Creation-only integrity backstop (Section I): a ReviewRequest can't
    reference a student–circle pair that isn't actually linked. Logic lives
    on the model, not here."""
    if instance.pk is None:
        instance.validate_relationships()

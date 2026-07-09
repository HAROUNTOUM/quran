from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta

from apps.circles.models import Session, CircleEnrollment
from apps.attendance.models import Attendance


@receiver(pre_save, sender=Session)
def set_start_time_on_schedule(sender, instance, **kwargs):
    transitioning_to_scheduled = False

    if instance.pk is None:
        transitioning_to_scheduled = instance.status == Session.Status.SCHEDULED
    else:
        try:
            old = sender.objects.get(pk=instance.pk)
            transitioning_to_scheduled = (
                old.status != Session.Status.SCHEDULED
                and instance.status == Session.Status.SCHEDULED
            )
        except sender.DoesNotExist:
            return

    if transitioning_to_scheduled:
        if not instance.start_time and instance.session_date and instance.session_time:
            tz = timezone.get_current_timezone()
            naive = timezone.datetime.combine(
                instance.session_date, instance.session_time
            )
            instance.start_time = timezone.make_aware(naive, tz)


@receiver(post_save, sender=Session)
def create_attendance_on_scheduled(sender, instance, created, **kwargs):
    transitioning_to_scheduled = False

    if created:
        transitioning_to_scheduled = instance.status == Session.Status.SCHEDULED
    else:
        try:
            old = sender.objects.get(pk=instance.pk)
            transitioning_to_scheduled = (
                old.status != Session.Status.SCHEDULED
                and instance.status == Session.Status.SCHEDULED
            )
        except sender.DoesNotExist:
            return

    if transitioning_to_scheduled:
        enrollments = CircleEnrollment.objects.filter(
            circle=instance.circle,
            status=CircleEnrollment.Status.ACTIVE,
        ).select_related("student")

        atts = []
        for enrollment in enrollments:
            atts.append(Attendance(
                session=instance,
                student=enrollment.student,
                status=Attendance.Status.NOT_RESPONDED,
            ))
        Attendance.objects.bulk_create(atts, ignore_conflicts=True)

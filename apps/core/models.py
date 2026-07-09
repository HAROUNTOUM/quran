import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class UUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخر تحديث")

    class Meta:
        abstract = True


class BaseManager(models.Manager):
    """Manager that hides soft-deleted rows. Attached as `.active` on SoftDeleteModel."""

    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class SoftDeleteModel(models.Model):
    is_deleted = models.BooleanField(default=False, verbose_name="محذوف")
    deleted_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ الحذف")

    # `objects` stays unfiltered so admin/aggregates never silently hide rows;
    # use `.active` for user-facing queries.
    objects = models.Manager()
    active = BaseManager()

    class Meta:
        abstract = True

    def soft_delete(self):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_deleted", "deleted_at"])

    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=["is_deleted", "deleted_at"])


class UserTrackedModel(models.Model):
    """Abstract base recording which user created/last modified a row."""

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, editable=False,
        related_name="%(app_label)s_%(class)s_created",
        verbose_name="أنشئ بواسطة",
    )
    modified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, editable=False,
        related_name="%(app_label)s_%(class)s_modified",
        verbose_name="آخر تعديل بواسطة",
    )

    class Meta:
        abstract = True

    def save_with_user(self, user, **kwargs):
        """Save while stamping the acting user — keeps views thin without middleware magic."""
        if self.pk is None and self.created_by_id is None:
            self.created_by = user
        self.modified_by = user
        self.save(**kwargs)


class StudentOwnedModel(models.Model):
    """Abstract base for any model that is primarily about one student's data (Rule 2)."""

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_records",
        limit_choices_to={"role": "student"},
        verbose_name="الطالب",
    )

    class Meta:
        abstract = True

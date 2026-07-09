from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.accounts.models import User


class SupportRequestQuerySet(models.QuerySet):
    def open(self):
        return self.filter(status__in=[
            SupportRequest.Status.SUBMITTED, SupportRequest.Status.UNDER_REVIEW,
        ])

    def overdue(self):
        cutoff = timezone.now() - timedelta(days=SupportRequest.overdue_after_days())
        return self.open().filter(created_at__lt=cutoff)

    def for_user(self, user):
        return self.filter(submitted_by=user)


class SupportRequest(models.Model):

    class Type(models.TextChoices):
        TECHNICAL = 'technical', 'دعم فني'
        ADMINISTRATIVE = 'administrative', 'إداري'
        ACADEMIC = 'academic', 'أكاديمي'
        OTHER = 'other', 'أخرى'

    class Priority(models.TextChoices):
        LOW = 'low', 'منخفضة'
        NORMAL = 'normal', 'متوسطة'
        HIGH = 'high', 'عالية'
        URGENT = 'urgent', 'عاجلة'

    class Status(models.TextChoices):
        SUBMITTED = 'submitted', 'مقدم'
        UNDER_REVIEW = 'under_review', 'قيد المراجعة'
        APPROVED = 'approved', 'مقبول'
        REJECTED = 'rejected', 'مرفوض'
        RESOLVED = 'resolved', 'تم الحل'

    # Non-admin actors move requests forward along this graph only.
    # Admins/supervisors may jump to any status (matches the existing
    # admin workflow, incl. reopening).
    ALLOWED_TRANSITIONS = {
        Status.SUBMITTED: {Status.UNDER_REVIEW, Status.APPROVED, Status.REJECTED, Status.RESOLVED},
        Status.UNDER_REVIEW: {Status.APPROVED, Status.REJECTED, Status.RESOLVED},
        Status.APPROVED: {Status.RESOLVED},
        Status.REJECTED: set(),
        Status.RESOLVED: set(),
    }

    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='support_requests'
    )
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True)
    type = models.CharField(max_length=50, choices=Type.choices, default=Type.OTHER)
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.NORMAL)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUBMITTED)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = SupportRequestQuerySet.as_manager()

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'طلب دعم'
        verbose_name_plural = 'طلبات الدعم'
        indexes = [
            # L13: "my requests" pages filter by (submitted_by, status).
            models.Index(fields=["submitted_by", "status"]),
        ]

    def __str__(self):
        return self.title

    @property
    def sender(self):
        return self.submitted_by

    # ------------------------------------------------------------------
    # Section A — the Request model owns submission, validation,
    # status-transition and overdue-detection logic.
    # ------------------------------------------------------------------

    @staticmethod
    def overdue_after_days() -> int:
        """Days an open request may wait before counting as overdue.

        Reads the admin-managed system setting; falls back to 3 if the
        settings store isn't available (e.g. before migration).
        """
        try:
            from apps.usersettings.services import get_system_setting
            return int(get_system_setting("request_overdue_days"))
        except Exception:
            return 3

    @classmethod
    def submit(cls, user, title, body, type=Type.OTHER, priority=Priority.NORMAL):
        """Validated submission path — the only supported way to create one."""
        title = (title or "").strip()
        body = (body or "").strip()
        if not title or not body:
            raise ValidationError("يرجى ملء جميع الحقول المطلوبة")
        if type not in cls.Type.values:
            type = cls.Type.OTHER
        if priority not in cls.Priority.values:
            priority = cls.Priority.NORMAL
        return cls.objects.create(
            submitted_by=user, title=title, body=body,
            type=type, priority=priority,
        )

    def transition_to(self, new_status, by, comment=""):
        """Single validated path for every status change.

        Admin/supervisor may jump freely (existing behavior); other actors
        must follow ALLOWED_TRANSITIONS. Optionally records a comment as
        part of the same response action.
        """
        if new_status not in self.Status.values:
            raise ValidationError("حالة غير صالحة")
        if new_status == self.status:
            raise ValidationError("الطلب في هذه الحالة بالفعل")
        if by.role not in (User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN):
            allowed = self.ALLOWED_TRANSITIONS.get(self.status, set())
            if new_status not in allowed:
                raise ValidationError(
                    f"لا يمكن نقل الطلب من '{self.get_status_display()}' إلى الحالة المطلوبة"
                )
        self.status = new_status
        self.save(update_fields=["status", "updated_at"])
        if comment:
            Comment.objects.create(request=self, author=by, body=comment)
        return self

    @property
    def is_open(self) -> bool:
        return self.status in (self.Status.SUBMITTED, self.Status.UNDER_REVIEW)

    @property
    def is_overdue(self) -> bool:
        if not self.is_open:
            return False
        return self.created_at < timezone.now() - timedelta(days=self.overdue_after_days())


class Comment(models.Model):
    request = models.ForeignKey(SupportRequest, on_delete=models.CASCADE, related_name='comments', verbose_name="الطلب")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='request_comments', verbose_name="الكاتب")
    body = models.TextField("التعليق")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = 'تعليق'
        verbose_name_plural = 'التعليقات'

    def __str__(self):
        return f"{self.author.full_name_ar}: {self.body[:50]}"

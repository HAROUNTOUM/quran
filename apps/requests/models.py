from django.db import models
from django.conf import settings


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

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'طلب دعم'
        verbose_name_plural = 'طلبات الدعم'

    def __str__(self):
        return self.title

    @property
    def sender(self):
        return self.submitted_by


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

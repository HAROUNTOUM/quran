from django.db import models
from django.conf import settings


class Notification(models.Model):

    class Type(models.TextChoices):
        APPROVAL = 'approval', 'اعتماد حساب'
        REJECTION = 'rejection', 'رفض حساب'
        NEW_USER = 'new_user', 'مستخدم جديد'
        NEW_REQUEST = 'new_request', 'طلب دعم جديد'
        REQUEST_UPDATE = 'request_update', 'تحديث طلب دعم'
        ANNOUNCEMENT = 'announcement', 'إعلان جديد'
        REVIEW_REQUEST = 'review_request', 'طلب مراجعة/تسميع'
        RESCHEDULE_REQUEST = 'reschedule_request', 'طلب تعديل موعد'
        ABSENCE_REVIEW = 'absence_review', 'مراجعة تبرير غياب'
        CERTIFICATE = 'certificate', 'شهادة'
        SESSION_STARTING = 'session_starting', 'بدء الحصة'
        SYSTEM = 'system', 'إشعار نظام'
        TASK_ASSIGNED = 'task_assigned', 'مهمة حفظ/مراجعة'
        TASK_VALIDATED = 'task_validated', 'اعتماد مهمة'

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='notifications'
    )
    type = models.CharField(max_length=30, choices=Type.choices, verbose_name='النوع')
    title = models.CharField(max_length=255, verbose_name='العنوان')
    message = models.TextField(verbose_name='الرسالة')
    link = models.CharField(max_length=500, blank=True, verbose_name='الرابط')
    is_read = models.BooleanField(default=False, verbose_name='مقروء')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            # L13: the unread-count context processor runs this filter on
            # every authenticated page load.
            models.Index(fields=["recipient", "is_read"]),
        ]
        verbose_name = 'إشعار'
        verbose_name_plural = 'الإشعارات'

    def mark_as_read(self):
        if not self.is_read:
            self.is_read = True
            self.save(update_fields=["is_read"])

    def __str__(self):
        return f'{self.get_type_display()}: {self.title}'

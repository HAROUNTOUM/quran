from django.db import models
from django.conf import settings


class Attendance(models.Model):

    class Status(models.TextChoices):
        PRESENT = 'present', 'حاضر'
        LATE = 'late', 'متأخر'
        ABSENT = 'absent', 'غائب'
        EXCUSED = 'excused', 'معذور'
        LEFT_EARLY = 'left_early', 'انصرف مبكراً'
        PENDING_JUSTIFICATION = 'pending_justification', 'بانتظار التبرير'

    session = models.ForeignKey(
        'circles.Session', on_delete=models.CASCADE,
        related_name='attendance_records'
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='attendance_records'
    )
    status = models.CharField(max_length=30, choices=Status.choices)
    justification = models.TextField("تبرير الطالب", blank=True)
    teacher_remark = models.TextField("ملاحظة المعلم", blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reviewed_absences",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('session', 'student')
        verbose_name = 'حضور'
        verbose_name_plural = 'سجلات الحضور'

    def __str__(self):
        return f"{self.student.full_name_ar} — {self.status} ({self.session.session_date})"


class SessionAttendanceIntent(models.Model):

    class Intent(models.TextChoices):
        ATTENDING = "attending", "سأحضر"
        ABSENT = "absent", "سأغيب"
        UNDECIDED = "undecided", "لم أقرر بعد"

    session = models.ForeignKey(
        "circles.Session", on_delete=models.CASCADE,
        related_name="attendance_intents",
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="attendance_intents",
    )
    intent = models.CharField(
        max_length=20, choices=Intent.choices, default=Intent.UNDECIDED,
        verbose_name="نية الحضور",
    )
    reason = models.TextField("سبب الغياب", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("session", "student")
        verbose_name = "نية حضور"
        verbose_name_plural = "نوايا الحضور"

    def __str__(self):
        return f"{self.student.full_name_ar} — {self.get_intent_display()} ({self.session.session_date})"

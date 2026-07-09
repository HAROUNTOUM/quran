from django.db import models
from django.conf import settings
from django.db.models import Count, Q, Sum
from django.utils import timezone


class AttendanceQuerySet(models.QuerySet):
    def for_student(self, student):
        return self.filter(student=student)

    def for_period(self, start, end):
        return self.filter(session__session_date__gte=start, session__session_date__lte=end)

    def present_count(self):
        return self.filter(status__in=("present", "confirmed")).count()

    def absent_count(self):
        return self.filter(status__in=("absent", "absent_unjustified", "absent_justified")).count()

    def late_count(self):
        return self.filter(status="late").count()

    def attendance_rate(self):
        total = self.count()
        if total == 0:
            return 0.0
        present = self.present_count()
        return round(present / total * 100, 1)

    def status_breakdown(self):
        return self.values("status").annotate(count=Count("id")).order_by("status")

    def weekly_trend(self, weeks=8):
        from django.db.models.functions import TruncWeek
        return self.annotate(week=TruncWeek("session__session_date")).values("week").annotate(
            total=Count("id"),
            present=Count("id", filter=Q(status__in=("present", "confirmed"))),
            absent=Count("id", filter=Q(status__in=("absent", "absent_unjustified", "absent_justified"))),
        ).order_by("-week")[:weeks]


class Attendance(models.Model):

    class Status(models.TextChoices):
        NOT_RESPONDED = 'not_responded', 'لم يرد'
        CONFIRMED = 'confirmed', 'مؤكد'
        PRESENT = 'present', 'حاضر'
        ABSENT_UNJUSTIFIED = 'absent_unjustified', 'غائب بدون عذر'
        ABSENT_JUSTIFIED = 'absent_justified', 'غائب بعذر'
        LATE = 'late', 'متأخر'
        ABSENT = 'absent', 'غائب'
        EXCUSED = 'excused', 'معذور'
        LEFT_EARLY = 'left_early', 'انصرف مبكراً'

    class JustificationStatus(models.TextChoices):
        NONE = 'none', 'لا يوجد'
        PENDING = 'pending', 'قيد المراجعة'
        ACCEPTED = 'accepted', 'مقبول'
        REFUSED = 'refused', 'مرفوض'

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
    justification_status = models.CharField(
        max_length=20, choices=JustificationStatus.choices,
        default=JustificationStatus.NONE, verbose_name="حالة التبرير",
    )
    justification_submitted_at = models.DateTimeField(
        null=True, blank=True, verbose_name="تاريخ تقديم التبرير",
    )
    submitted_before_session = models.BooleanField(default=False, verbose_name="قدّم قبل الحصة")
    teacher_comment = models.TextField("تعليق المعلم", blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reviewed_absences",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = AttendanceQuerySet.as_manager()

    class Meta:
        unique_together = ('session', 'student')
        verbose_name = 'حضور'
        verbose_name_plural = 'سجلات الحضور'
        indexes = [
            # HAF-24: attendance_stats() aggregates per student by status.
            models.Index(fields=["student", "status"]),
        ]

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

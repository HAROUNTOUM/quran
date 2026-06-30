from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.conf import settings

from .models import Notification
from apps.accounts.models import User
from apps.requests.models import SupportRequest, Comment
from apps.announcements.models import Announcement
from apps.memorization.models import ReviewRequest
from apps.circles.models import SessionRescheduleRequest
from apps.attendance.models import Attendance


@receiver(post_save, sender=User)
def notify_user_created(sender, instance, created, **kwargs):
    if not created:
        return
    if instance.role in (User.Role.ADMIN,):
        return

    admins = User.objects.filter(role=User.Role.ADMIN)
    for admin in admins:
        Notification.objects.create(
            recipient=admin,
            type=Notification.Type.NEW_USER,
            title="مستخدم جديد في انتظار الاعتماد",
            message=f"قام {instance.full_name_ar} ({instance.get_role_display()}) بالتسجيل في المنصة. يرجى مراجعة طلبات الاعتماد.",
            link="/dashboard/inscriptions/",
        )

    if instance.is_approved == User.ApprovalStatus.APPROVED:
        Notification.objects.create(
            recipient=instance,
            type=Notification.Type.APPROVAL,
            title="تم اعتماد حسابك",
            message=f"أهلاً {instance.full_name_ar}، تم اعتماد حسابك في منصة الطبيب الحافظ. يمكنك الآن الدخول والبدء في استخدام المنصة.",
            link="/dashboard/",
        )


@receiver(pre_save, sender=User)
def notify_user_approved_or_rejected(sender, instance, **kwargs):
    if instance.pk is None:
        return
    try:
        old = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return

    if old.is_approved == instance.is_approved:
        return

    if instance.is_approved == User.ApprovalStatus.APPROVED:
        Notification.objects.create(
            recipient=instance,
            type=Notification.Type.APPROVAL,
            title="تم اعتماد حسابك",
            message=f"أهلاً {instance.full_name_ar}، تم اعتماد حسابك في منصة الطبيب الحافظ. يمكنك الآن الدخول والبدء في استخدام المنصة.",
            link="/dashboard/",
        )

    elif instance.is_approved == User.ApprovalStatus.REJECTED:
        reason = instance.rejection_reason or "لم يتم تحديد سبب"
        Notification.objects.create(
            recipient=instance,
            type=Notification.Type.REJECTION,
            title="عذراً، لم يتم اعتماد حسابك",
            message=f"عذراً {instance.full_name_ar}، لم يتم اعتماد حسابك في المنصة. سبب الرفض: {reason}",
            link="/login/",
        )


@receiver(post_save, sender=SupportRequest)
def notify_new_support_request(sender, instance, created, **kwargs):
    if not created:
        return
    admins = User.objects.filter(role=User.Role.ADMIN)
    for admin in admins:
        Notification.objects.create(
            recipient=admin,
            type=Notification.Type.NEW_REQUEST,
            title="طلب دعم جديد",
            message=f"تم تقديم طلب دعم جديد بواسطة {instance.submitted_by.full_name_ar}: {instance.title}",
            link="/dashboard/requests/",
        )


@receiver(post_save, sender=Comment)
def notify_comment_added(sender, instance, created, **kwargs):
    if not created:
        return
    req = instance.request
    if instance.author != req.submitted_by:
        Notification.objects.create(
            recipient=req.submitted_by,
            type=Notification.Type.REQUEST_UPDATE,
            title=f"تعليق جديد على طلبك",
            message=f"قام {instance.author.full_name_ar} بإضافة تعليق على طلبك: {req.title}",
            link=f"/dashboard/requests/{req.pk}/",
        )
    else:
        admins = User.objects.filter(role=User.Role.ADMIN)
        for admin in admins:
            Notification.objects.create(
                recipient=admin,
                type=Notification.Type.REQUEST_UPDATE,
                title=f"تعليق جديد على طلب دعم",
                message=f"قام {instance.author.full_name_ar} بإضافة تعليق على طلب {req.title}",
                link=f"/dashboard/requests/{req.pk}/",
            )


@receiver(post_save, sender=Announcement)
def notify_new_announcement(sender, instance, created, **kwargs):
    if not created:
        return
    users = User.objects.filter(is_approved=User.ApprovalStatus.APPROVED, is_active=True)
    for user in users:
        Notification.objects.create(
            recipient=user,
            type=Notification.Type.ANNOUNCEMENT,
            title=instance.title,
            message=instance.body[:200],
            link="/dashboard/announcements/",
        )


@receiver(pre_save, sender=ReviewRequest)
def notify_review_request_status(sender, instance, **kwargs):
    if instance.pk is None:
        return
    try:
        old = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return
    if old.status == instance.status:
        return

    if instance.status == ReviewRequest.Status.APPROVED:
        Notification.objects.create(
            recipient=instance.student,
            type=Notification.Type.REVIEW_REQUEST,
            title="تم قبول طلبك",
            message=f"تم قبول طلب {instance.get_type_display()} الخاص بك في حلقة {instance.circle.name}",
            link="/dashboard/student/memorization/",
        )
    elif instance.status == ReviewRequest.Status.REJECTED:
        reason = instance.rejection_reason or "لم يتم تحديد سبب"
        Notification.objects.create(
            recipient=instance.student,
            type=Notification.Type.REVIEW_REQUEST,
            title="تم رفض طلبك",
            message=f"تم رفض طلب {instance.get_type_display()} الخاص بك. السبب: {reason}",
            link="/dashboard/student/memorization/",
        )


@receiver(pre_save, sender=SessionRescheduleRequest)
def notify_reschedule_request_status(sender, instance, **kwargs):
    if instance.pk is None:
        return
    try:
        old = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return
    if old.status == instance.status:
        return

    session_label = f"{instance.session.circle.name} — {instance.session.session_date}"
    if instance.status == SessionRescheduleRequest.Status.APPROVED:
        Notification.objects.create(
            recipient=instance.requested_by,
            type=Notification.Type.RESCHEDULE_REQUEST,
            title="تم قبول طلب تعديل الموعد",
            message=f"تم قبول طلب تعديل موعد حصة {session_label} إلى {instance.proposed_date}",
            link="/dashboard/teacher/sessions/manage/",
        )
    elif instance.status == SessionRescheduleRequest.Status.REJECTED:
        reason = instance.rejection_reason or "لم يتم تحديد سبب"
        Notification.objects.create(
            recipient=instance.requested_by,
            type=Notification.Type.RESCHEDULE_REQUEST,
            title="تم رفض طلب تعديل الموعد",
            message=f"تم رفض طلب تعديل موعد حصة {session_label}. السبب: {reason}",
            link="/dashboard/teacher/sessions/manage/",
        )


@receiver(pre_save, sender=Attendance)
def notify_absence_review(sender, instance, **kwargs):
    if instance.pk is None:
        return
    if not instance.justification:
        return
    try:
        old = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return
    if old.status == instance.status:
        return
    if old.status != Attendance.Status.PENDING_JUSTIFICATION:
        return

    session_label = f"{instance.session.circle.name} — {instance.session.session_date}"
    if instance.status == Attendance.Status.EXCUSED:
        Notification.objects.create(
            recipient=instance.student,
            type=Notification.Type.ABSENCE_REVIEW,
            title="تم قبول تبرير الغياب",
            message=f"تم قبول تبرير غيابك عن حصة {session_label}",
            link="/dashboard/student/",
        )
    elif instance.status == Attendance.Status.ABSENT:
        remark = f" ملاحظة المعلم: {instance.teacher_remark}" if instance.teacher_remark else ""
        Notification.objects.create(
            recipient=instance.student,
            type=Notification.Type.ABSENCE_REVIEW,
            title="تم رفض تبرير الغياب",
            message=f"تم رفض تبرير غيابك عن حصة {session_label}.{remark}",
            link="/dashboard/student/",
        )

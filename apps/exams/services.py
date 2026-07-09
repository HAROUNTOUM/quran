from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.notifications.models import Notification

from apps.circles.models import CircleEnrollment

from .models import Exam, ExamApprovalHistory, ExamMark, ExamNotification

User = get_user_model()


# ─── SEQUENCE 1: Exam Creation & Publishing ─────────────────────────


def validate_exam_input(data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    if not data.get("title", "").strip():
        return False, "عنوان الامتحان مطلوب"
    if data.get("max_marks", 100) <= 0:
        return False, "الدرجة القصوى يجب أن تكون أكبر من صفر"
    if data.get("pass_percentage", 50) < 0 or data.get("pass_percentage", 50) > 100:
        return False, "نسبة النجاح يجب أن تكون بين 0 و 100"
    circle_id = data.get("circle_id") or (data.get("circle") if isinstance(data.get("circle"), int) else None)
    if circle_id:
        from apps.circles.models import Circle
        if not Circle.objects.filter(pk=circle_id, status=Circle.Status.ACTIVE).exists():
            return False, "الحلقة المحددة غير موجودة أو غير نشطة"
    return True, None


def check_exam_code_unique(exam_code: str, exclude_pk: Optional[int] = None) -> bool:
    qs = Exam.objects.filter(exam_code=exam_code)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return not qs.exists()


def create_exam(data: Dict[str, Any], user: User) -> Exam:
    exam = Exam.objects.create(
        title=data["title"].strip(),
        description=data.get("description", ""),
        exam_type=data.get("exam_type", "monthly"),
        circle=data.get("circle"),
        circle_id=data.get("circle_id"),
        created_by=user,
        assigned_teacher=data.get("assigned_teacher"),
        assigned_teacher_id=data.get("assigned_teacher_id"),
        exam_date=data.get("exam_date", timezone.now().date()),
        max_marks=data.get("max_marks", 100),
        pass_percentage=data.get("pass_percentage", 50),
        status=Exam.Status.DRAFT,
        auto_publish=data.get("auto_publish", False),
    )
    _log_history(exam, ExamApprovalHistory.Action.CREATED, user)
    if data.get("auto_publish") or data.get("status") == Exam.Status.PUBLISHED:
        _publish_exam(exam, user)
    return exam


def _publish_exam(exam: Exam, user: User) -> None:
    exam.status = Exam.Status.PUBLISHED
    exam.save(update_fields=["status"])
    _log_history(exam, ExamApprovalHistory.Action.PUBLISHED, user)


# ─── SEQUENCE 2: Notification on Publish ───────────────────────────


def get_class_teachers(exam: Exam) -> List[User]:
    if exam.assigned_teacher:
        return [exam.assigned_teacher]
    if exam.circle and exam.circle.teacher:
        return [exam.circle.teacher]
    return []


def get_class_students(exam: Exam) -> List[User]:
    if exam.circle:
        return list(
            User.objects.filter(
                enrollments__circle=exam.circle,
                enrollments__status=CircleEnrollment.Status.ACTIVE,
                role=User.Role.STUDENT,
                is_approved=User.ApprovalStatus.APPROVED,
            ).distinct()
        )
    return list(
        User.objects.filter(
            role=User.Role.STUDENT, is_approved=User.ApprovalStatus.APPROVED
        )
    )


def create_notifications(
    exam: Exam,
    recipients: List[User],
    notif_type: str,
    title: str,
    message: str,
    link: str = "",
    sent_via: str = ExamNotification.SentVia.IN_APP,
) -> List[ExamNotification]:
    notifs = []
    for recipient in recipients:
        notif = ExamNotification.objects.create(
            exam=exam,
            recipient=recipient,
            type=notif_type,
            sent_via=sent_via,
            title=title,
            message=message,
            link=link,
        )
        notifs.append(notif)
        if sent_via in (ExamNotification.SentVia.BOTH, ExamNotification.SentVia.EMAIL):
            send_email_notification(recipient, title, message)
    return notifs


def send_email_notification(user: User, subject: str, message: str) -> None:
    if not user.email:
        return
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=None,  # uses DEFAULT_FROM_EMAIL
            recipient_list=[user.email],
            fail_silently=True,
        )
    except Exception:
        pass  # Email failure should not block the main flow


def notify_published(exam: Exam, user: User) -> None:
    teachers = get_class_teachers(exam)
    students = get_class_students(exam)
    recipients = teachers + students
    link = f"/dashboard/exams/{exam.pk}/"
    create_notifications(
        exam, recipients,
        ExamNotification.Type.EXAM_PUBLISHED,
        f"نشر امتحان: {exam.title}",
        f"تم نشر الامتحان {exam.title} بتاريخ {exam.exam_date}",
        link,
    )
    Notification.objects.bulk_create([
        Notification(
            recipient=r, type=Notification.Type.SYSTEM,
            title=f"امتحان جديد: {exam.title}",
            message=f"تم نشر الامتحان {exam.title}، يرجى مراجعة التفاصيل",
            link=link,
        ) for r in recipients
    ])


# ─── SEQUENCE 3: Mark Entry ────────────────────────────────────────


def verify_exam_status(exam: Exam, allowed_statuses: List[str]) -> Tuple[bool, Optional[str]]:
    if exam.status not in allowed_statuses:
        return False, f"الامتحان في حالة {exam.get_status_display()} ولا يمكن تنفيذ هذا الإجراء"
    return True, None


def verify_teacher_assignment(exam: Exam, user: User) -> Tuple[bool, Optional[str]]:
    if user.role in (User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN):
        return True, None
    if exam.assigned_teacher_id == user.pk:
        return True, None
    if exam.circle and exam.circle.teacher_id == user.pk:
        return True, None
    return False, "ليس لديك صلاحية لإدخال درجات لهذا الامتحان"


def validate_mark_value(marks_obtained: float, max_marks: float) -> Tuple[bool, Optional[str]]:
    if marks_obtained < 0:
        return False, "الدرجة لا يمكن أن تكون سالبة"
    if marks_obtained > max_marks:
        return False, f"الدرجة لا يمكن أن تتجاوز {max_marks}"
    return True, None


def calculate_percentage_grade(marks_obtained: float, max_marks: float) -> Dict[str, Any]:
    percentage = round((marks_obtained / max_marks) * 100, 2) if max_marks > 0 else 0
    if percentage >= 90:
        grade = "A"
    elif percentage >= 80:
        grade = "B"
    elif percentage >= 70:
        grade = "C"
    elif percentage >= 60:
        grade = "D"
    elif percentage >= 50:
        grade = "E"
    else:
        grade = "F"
    return {"percentage": percentage, "grade": grade}


def save_mark(
    exam: Exam,
    student: User,
    marks_obtained: float,
    entered_by: User,
    teacher_notes: str = "",
    private_notes: str = "",
) -> ExamMark:
    mark, created = ExamMark.objects.update_or_create(
        exam=exam,
        student=student,
        defaults={
            "marks_obtained": marks_obtained,
            "teacher_notes": teacher_notes,
            "private_notes": private_notes,
            "entered_by": entered_by,
            "status": ExamMark.Status.PENDING,
        },
    )
    return mark


def check_all_marks_entered(
    exam: Exam, enrolled_students: List[User]
) -> bool:
    entered_ids = set(exam.marks.values_list("student_id", flat=True))
    enrolled_ids = {s.pk for s in enrolled_students}
    return enrolled_ids.issubset(entered_ids)


def suggest_submission(exam: Exam, user: User) -> None:
    from apps.notifications.models import Notification as InAppNotification

    # Notify the teacher that all marks are entered and suggest submission
    teachers = get_class_teachers(exam)
    link = f"/dashboard/teacher/exams/{exam.pk}/grade/"
    for teacher in teachers:
        InAppNotification.objects.create(
            recipient=teacher,
            type=InAppNotification.Type.SYSTEM,
            title=f"اكتمال تصحيح: {exam.title}",
            message=f"تم إدخال درجات جميع الطلاب في الامتحان {exam.title}. يُرجى تقديم النتائج للاعتماد.",
            link=link,
        )

    # Also notify admins/supervisors if no assigned teacher
    if not teachers:
        admins = User.objects.filter(
            Q(role=User.Role.MAIN_ADMIN) | Q(role=User.Role.SUB_ADMIN),
            is_approved=User.ApprovalStatus.APPROVED,
            is_active=True,
        )
        for admin in admins:
            InAppNotification.objects.create(
                recipient=admin,
                type=InAppNotification.Type.SYSTEM,
                title=f"اكتمال تصحيح: {exam.title}",
                message=f"تم إدخال درجات جميع الطلاب في الامتحان {exam.title} وهو جاهز للاعتماد.",
                link=f"/dashboard/exams/{exam.pk}/",
            )


# ─── SEQUENCE 4: Submit for Approval ───────────────────────────────


def submit_for_approval(exam: Exam, user: User) -> Tuple[bool, Optional[str]]:
    ok, err = verify_exam_status(exam, [Exam.Status.GRADING, Exam.Status.PUBLISHED])
    if not ok:
        return False, err
    ok, err = verify_teacher_assignment(exam, user)
    if not ok:
        return False, err
    enrolled = get_class_students(exam)
    if not check_all_marks_entered(exam, enrolled):
        return False, "لم يتم إدخال درجات جميع الطلاب بعد"

    with transaction.atomic():
        exam.status = Exam.Status.PENDING_APPROVAL
        exam.save(update_fields=["status"])
        _log_history(exam, ExamApprovalHistory.Action.SUBMITTED, user)
        _notify_admins(exam, user)
    return True, None


def _notify_admins(exam: Exam, submitted_by: User) -> None:
    admins = User.objects.filter(
        Q(role=User.Role.MAIN_ADMIN) | Q(role=User.Role.SUB_ADMIN),
        is_approved=User.ApprovalStatus.APPROVED,
        is_active=True,
    )
    link = f"/dashboard/exams/{exam.pk}/"
    create_notifications(
        exam, list(admins),
        ExamNotification.Type.SUBMITTED_FOR_APPROVAL,
        f"تقديم للاعتماد: {exam.title}",
        f"قام {submitted_by.full_name_ar} بتقديم نتائج الامتحان {exam.title} للاعتماد",
        link,
    )


# ─── SEQUENCE 5: Mark Approval ─────────────────────────────────────


def _calculate_grade_for_percentage(percentage: float) -> str:
    if percentage >= 90:
        return "A"
    elif percentage >= 80:
        return "B"
    elif percentage >= 70:
        return "C"
    elif percentage >= 60:
        return "D"
    elif percentage >= 50:
        return "E"
    return "F"


def approve_all_marks(exam: Exam, user: User) -> None:
    with transaction.atomic():
        marks_snapshot = _build_marks_snapshot(exam)
        exam.marks.filter(status=ExamMark.Status.PENDING).update(
            status=ExamMark.Status.APPROVED,
            approved_by=user,
        )
        exam.status = Exam.Status.COMPLETED
        exam.save(update_fields=["status"])
        ExamApprovalHistory.objects.create(
            exam=exam,
            action=ExamApprovalHistory.Action.COMPLETED,
            performed_by=user,
            marks_snapshot=marks_snapshot,
        )
        _notify_students_approved(exam)


def approve_selected_marks(
    exam: Exam, mark_ids: List[int], user: User
) -> None:
    with transaction.atomic():
        ExamMark.objects.filter(id__in=mark_ids, exam=exam).update(
            status=ExamMark.Status.APPROVED,
            approved_by=user,
        )
        remaining = exam.marks.filter(status=ExamMark.Status.PENDING).count()
        if remaining == 0:
            exam.status = Exam.Status.COMPLETED
            exam.save(update_fields=["status"])
            ExamApprovalHistory.objects.create(
                exam=exam,
                action=ExamApprovalHistory.Action.COMPLETED,
                performed_by=user,
            )
        else:
            ExamApprovalHistory.objects.create(
                exam=exam,
                action=ExamApprovalHistory.Action.APPROVED,
                performed_by=user,
            )
    marks_approved = ExamMark.objects.filter(id__in=mark_ids, exam=exam).select_related("student")
    link = f"/dashboard/student/exams/"
    Notification.objects.bulk_create([
        Notification(
            recipient=mark.student,
            type=Notification.Type.APPROVAL,
            title=f"اعتماد نتيجة امتحان: {exam.title}",
            message=f"تم اعتماد نتيجتك في امتحان {exam.title}: {mark.percentage}% (تقدير {mark.grade})",
            link=link,
        )
        for mark in marks_approved
    ])


def _notify_students_approved(exam: Exam) -> None:
    exam_title = exam.title
    link = f"/dashboard/student/exams/"
    marks = exam.marks.filter(status=ExamMark.Status.APPROVED).select_related("student")
    Notification.objects.bulk_create([
        Notification(
            recipient=mark.student,
            type=Notification.Type.APPROVAL,
            title=f"اعتماد نتيجة امتحان: {exam_title}",
            message=f"تم اعتماد نتيجتك في امتحان {exam_title}: {mark.percentage}% (تقدير {mark.grade})",
            link=link,
        )
        for mark in marks
    ])


# ─── SEQUENCE 6: Mark Rejection ────────────────────────────────────


def reject_marks(
    exam: Exam,
    mark_ids: List[int],
    user: User,
    reason: str = "",
) -> None:
    with transaction.atomic():
        marks_snapshot = _build_marks_snapshot(exam)
        ExamMark.objects.filter(id__in=mark_ids, exam=exam).update(
            status=ExamMark.Status.REJECTED,
        )
        exam.status = Exam.Status.GRADING
        exam.save(update_fields=["status"])
        ExamApprovalHistory.objects.create(
            exam=exam,
            action=ExamApprovalHistory.Action.REJECTED,
            performed_by=user,
            reason=reason,
            marks_snapshot=marks_snapshot,
        )
        _notify_teacher_rejected(exam, reason)


def _notify_teacher_rejected(exam: Exam, reason: str) -> None:
    recipients = []
    if exam.assigned_teacher:
        recipients.append(exam.assigned_teacher)
    elif exam.circle and exam.circle.teacher:
        recipients.append(exam.circle.teacher)
    link = f"/dashboard/teacher/exams/{exam.pk}/grade/"
    reason_text = reason or "غير محدد"
    create_notifications(
        exam, recipients,
        ExamNotification.Type.MARKS_REJECTED,
        f"رفض نتائج: {exam.title}",
        f"تم رفض نتائج الامتحان {exam.title}. السبب: {reason_text}",
        link,
    )
    Notification.objects.bulk_create([
        Notification(
            recipient=r,
            type=Notification.Type.REJECTION,
            title=f"رفض نتائج امتحان: {exam.title}",
            message=f"تم رفض نتائج الامتحان {exam.title}. يرجى مراجعة الدرجات وإعادة التقديم. السبب: {reason_text}",
            link=link,
        ) for r in recipients
    ])


# ─── SEQUENCE 7: Student View Marks ────────────────────────────────


def get_student_marks(student: User) -> List[Dict[str, Any]]:
    marks = ExamMark.objects.filter(
        student=student,
        status=ExamMark.Status.APPROVED,
        exam__status=Exam.Status.COMPLETED,
    ).select_related("exam", "exam__circle", "approved_by").order_by("-exam__exam_date")
    return [_safe_mark_dict(m) for m in marks]


def _safe_mark_dict(mark: ExamMark) -> Dict[str, Any]:
    return {
        "id": mark.pk,
        "exam_id": mark.exam_id,
        "exam_title": mark.exam.title,
        "exam_type": mark.exam.get_exam_type_display(),
        "exam_date": mark.exam.exam_date,
        "circle_name": mark.exam.circle.name if mark.exam.circle else None,
        "max_marks": mark.exam.max_marks,
        "marks_obtained": mark.marks_obtained,
        "percentage": mark.percentage,
        "grade": mark.grade,
        "is_passed": mark.is_passed,
        "teacher_notes": mark.teacher_notes,
        "approved_by_name": mark.approved_by.full_name_ar if mark.approved_by else None,
        "approved_at": mark.updated_at,
    }


# ─── SEQUENCE 8: PDF Export ────────────────────────────────────────


def get_export_data(exam: Exam) -> Dict[str, Any]:
    marks = exam.marks.select_related("student", "entered_by", "approved_by").all()
    approved_marks = [m for m in marks if m.status == ExamMark.Status.APPROVED]
    passing = [m for m in approved_marks if m.is_passed]
    failing = [m for m in approved_marks if not m.is_passed]

    mark_values = [m.marks_obtained for m in approved_marks]
    percentages = [m.percentage for m in approved_marks]

    return {
        "exam": {
            "title": exam.title,
            "code": exam.exam_code,
            "type": exam.get_exam_type_display(),
            "date": exam.exam_date,
            "max_marks": exam.max_marks,
            "pass_percentage": exam.pass_percentage,
            "circle": exam.circle.name if exam.circle else "عام",
            "teacher": exam.assigned_teacher.full_name_ar if exam.assigned_teacher else (exam.circle.teacher.full_name_ar if exam.circle and exam.circle.teacher else "—"),
        },
        "marks": [
            {
                "student_name": m.student.full_name_ar,
                "marks_obtained": m.marks_obtained,
                "percentage": m.percentage,
                "grade": m.grade,
                "is_passed": m.is_passed,
                "notes": m.teacher_notes,
                "status": m.get_status_display(),
            }
            for m in marks
        ],
        "statistics": {
            "total_students": len(marks),
            "approved_count": len(approved_marks),
            "pass_count": len(passing),
            "fail_count": len(failing),
            "pass_rate": round(len(passing) / max(len(approved_marks), 1) * 100, 1),
            "average_marks": round(sum(mark_values) / max(len(mark_values), 1), 1) if mark_values else 0,
            "average_percentage": round(sum(percentages) / max(len(percentages), 1), 1) if percentages else 0,
            "highest_marks": max(mark_values) if mark_values else 0,
            "lowest_marks": min(mark_values) if mark_values else 0,
        },
    }


# ─── HELPERS ───────────────────────────────────────────────────────


def _log_history(exam: Exam, action: str, user: User, reason: str = "") -> None:
    ExamApprovalHistory.objects.create(
        exam=exam,
        action=action,
        performed_by=user,
        reason=reason,
    )


def _build_marks_snapshot(exam: Exam) -> Optional[Dict]:
    marks = exam.marks.select_related("student").all()
    if not marks:
        return None
    return {
        "total": marks.count(),
        "marks": [
            {
                "student_id": str(m.student_id),
                "student_name": m.student.full_name_ar,
                "marks_obtained": m.marks_obtained,
                "percentage": m.percentage,
                "grade": m.grade,
                "status": m.status,
            }
            for m in marks
        ],
    }

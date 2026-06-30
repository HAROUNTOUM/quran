from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, FileResponse
from django.shortcuts import render, redirect, get_object_or_404

from apps.accounts.models import User

from .models import Certificate, CertificateTemplate
from .services import issue_certificate, generate_certificate_pdf


@login_required
def certificate_list(request):
    if request.user.role not in (User.Role.ADMIN, User.Role.SUPERVISOR):
        raise PermissionDenied

    certs = Certificate.objects.select_related("student", "template", "issued_by").all()
    return render(request, "certificates/list.html", {"certificates": certs})


@login_required
def student_certificates(request):
    if request.user.role != User.Role.STUDENT:
        raise PermissionDenied

    certs = Certificate.objects.filter(
        student=request.user, status="issued",
    ).select_related("template", "issued_by").order_by("-issue_date")
    return render(request, "certificates/student_list.html", {"certificates": certs})


@login_required
def certificate_generate(request):
    if request.user.role not in (User.Role.ADMIN, User.Role.SUPERVISOR):
        raise PermissionDenied

    templates = CertificateTemplate.objects.filter(is_active=True)

    from apps.circles.models import Circle
    circles = Circle.objects.filter(status=Circle.Status.ACTIVE)

    from apps.exams.models import Exam
    exams = Exam.objects.filter(status=Exam.Status.COMPLETED).order_by("-exam_date")

    from django.db.models import Prefetch
    from apps.circles.models import CircleEnrollment
    students = User.objects.filter(
        role=User.Role.STUDENT,
        is_approved=User.ApprovalStatus.APPROVED,
        is_active=True,
    ).prefetch_related(
        Prefetch(
            "enrollments",
            queryset=CircleEnrollment.objects.filter(status=CircleEnrollment.Status.ACTIVE).select_related("circle"),
            to_attr="_active_enrollments",
        )
    ).only("id", "full_name_ar", "email")

    for s in students:
        s.circle_ids = ",".join(
            str(e.circle_id) for e in getattr(s, "_active_enrollments", [])
        )

    if request.method == "POST":
        template_id = request.POST.get("template")
        details = request.POST.get("details", "")
        circle_name = request.POST.get("circle_name", "")

        if not template_id:
            messages.error(request, "يرجى اختيار القالب")
            return render(request, "certificates/generate.html", {
                "templates": templates, "circles": circles, "exams": exams, "students": students,
            })

        template = get_object_or_404(CertificateTemplate, id=template_id, is_active=True)

        student_ids = set()
        raw_ids = request.POST.getlist("students")
        student_ids.update(int(x) for x in raw_ids if x.isdigit())

        circle_id = request.POST.get("circle")
        if circle_id and circle_id.isdigit():
            from apps.circles.models import CircleEnrollment
            enrolled = CircleEnrollment.objects.filter(
                circle_id=int(circle_id),
                status=CircleEnrollment.Status.ACTIVE,
            ).values_list("student_id", flat=True)
            student_ids.update(enrolled)

        exam_id = request.POST.get("exam")
        if exam_id and exam_id.isdigit():
            from apps.exams.models import ExamMark
            passed = ExamMark.objects.filter(
                exam_id=int(exam_id),
                is_passed=True,
            ).values_list("student_id", flat=True)
            student_ids.update(passed)

        juz_completed = request.POST.get("juz_completed")
        if juz_completed:
            try:
                min_juz = int(juz_completed)
                from apps.memorization.models import StudentAchievement
                achievers = StudentAchievement.objects.filter(
                    completed_juz__gte=min_juz
                ).values_list("student_id", flat=True)
                student_ids.update(achievers)
            except ValueError:
                pass

        if not student_ids:
            messages.error(request, "لم يتم اختيار أي طالب")
            return render(request, "certificates/generate.html", {
                "templates": templates, "circles": circles, "exams": exams, "students": students,
            })

        students_qs = User.objects.filter(id__in=student_ids, role=User.Role.STUDENT)
        metadata = {}
        if circle_name:
            metadata["circle_name"] = circle_name

        success_count = 0
        errors = []
        for student in students_qs:
            try:
                issue_certificate(
                    student=student,
                    template=template,
                    issued_by=request.user,
                    details=details,
                    metadata=metadata,
                )
                success_count += 1
            except Exception as e:
                errors.append(f"{student.full_name_ar}: {e}")

        if success_count:
            messages.success(request, f"تم إصدار {success_count} شهادة بنجاح")
        for err in errors:
            messages.error(request, err)

        return redirect("certificates:list")

    return render(request, "certificates/generate.html", {
        "templates": templates,
        "circles": circles,
        "exams": exams,
        "students": students,
    })


@login_required
def certificate_download(request, pk):
    cert = get_object_or_404(Certificate, pk=pk)
    if request.user.role not in (User.Role.ADMIN, User.Role.SUPERVISOR) and request.user != cert.student:
        raise PermissionDenied
    return FileResponse(cert.pdf_file.open(), as_attachment=True, filename=f"{cert.certificate_number}.pdf")


@login_required
def certificate_preview(request, pk):
    cert = get_object_or_404(Certificate, pk=pk)
    if request.user.role not in (User.Role.ADMIN, User.Role.SUPERVISOR) and request.user != cert.student:
        raise PermissionDenied
    pdf_bytes = generate_certificate_pdf(cert)
    return HttpResponse(pdf_bytes, content_type="application/pdf")


@login_required
def certificate_notify(request, pk):
    if request.user.role not in (User.Role.ADMIN, User.Role.SUPERVISOR):
        raise PermissionDenied
    cert = get_object_or_404(Certificate, pk=pk)
    if request.method == "POST":
        from apps.notifications.models import Notification
        Notification.objects.create(
            recipient=cert.student,
            type=Notification.Type.CERTIFICATE,
            title="شهادة جديدة",
            message=f"تم إصدار شهادة {cert.template.name} لك. يمكنك الاطلاع عليها وتحميلها من صفحة الشهادات.",
            link="/dashboard/certificates/own/",
        )
        messages.success(request, f"تم إرسال إشعار الشهادة إلى {cert.student.full_name_ar}")
    return redirect("certificates:list")


@login_required
def certificate_revoke(request, pk):
    if request.user.role not in (User.Role.ADMIN, User.Role.SUPERVISOR):
        raise PermissionDenied
    cert = get_object_or_404(Certificate, pk=pk)
    if request.method == "POST":
        cert.status = "revoked"
        cert.save(update_fields=["status"])
        messages.success(request, "تم إلغاء الشهادة")
        return redirect("certificates:list")
    return render(request, "certificates/revoke.html", {"certificate": cert})

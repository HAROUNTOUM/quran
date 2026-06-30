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
    students = User.objects.filter(role=User.Role.STUDENT, is_approved=User.ApprovalStatus.APPROVED, is_active=True)

    if request.method == "POST":
        student_id = request.POST.get("student")
        template_id = request.POST.get("template")
        details = request.POST.get("details", "")

        if not student_id or not template_id:
            messages.error(request, "يرجى اختيار الطالب والقالب")
            return render(request, "certificates/generate.html", {"templates": templates, "students": students})

        student = get_object_or_404(User, id=student_id, role=User.Role.STUDENT)
        template = get_object_or_404(CertificateTemplate, id=template_id, is_active=True)

        metadata = {}
        circle_name = request.POST.get("circle_name", "")
        if circle_name:
            metadata["circle_name"] = circle_name

        try:
            cert = issue_certificate(
                student=student,
                template=template,
                issued_by=request.user,
                details=details,
                metadata=metadata,
            )
            messages.success(request, f"تم إصدار الشهادة {cert.certificate_number} بنجاح")
            return redirect("certificates:list")
        except Exception as e:
            messages.error(request, f"حدث خطأ: {e}")

    return render(request, "certificates/generate.html", {"templates": templates, "students": students})


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

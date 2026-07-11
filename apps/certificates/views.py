import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, FileResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts import scoping

from .models import Certificate, CertificateTemplate
from .services import generate_certificate_pdf


def _require_cert_access(user, cert, allow_owner=False):
    """Object-level guard: MAIN_ADMIN sees all; a SUB_ADMIN may only touch a
    certificate whose student is in a batch they supervise; the student may
    view their own when ``allow_owner``. Everyone else is denied."""
    if allow_owner and user == cert.student:
        return
    if user.role not in (User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN):
        raise PermissionDenied
    # MAIN_ADMIN passes; SUB_ADMIN must supervise the student's batch.
    scoping.check_batch_access(user, cert.student.batch_id)


@login_required
def certificate_list(request):
    if request.user.role not in (User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN):
        raise PermissionDenied

    pending = Certificate.objects.filter(status="pending_upload").select_related(
        "student", "template", "issued_by"
    ).order_by("-created_at")
    issued = Certificate.objects.filter(status="issued").select_related(
        "student", "template", "issued_by"
    ).order_by("-issue_date")
    # SUB_ADMIN only sees certificates for students in their supervised batches.
    batch_ids = scoping.scoped_batch_ids(request.user)
    if batch_ids is not None:
        pending = pending.filter(student__batch_id__in=batch_ids)
        issued = issued.filter(student__batch_id__in=batch_ids)
    return render(request, "certificates/list.html", {
        "pending_certificates": pending,
        "issued_certificates": issued,
    })


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
    if request.user.role not in (User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN):
        raise PermissionDenied

    templates = CertificateTemplate.objects.filter(is_active=True)

    from apps.circles.models import Circle, CircleEnrollment
    circles = Circle.objects.filter(status=Circle.Status.ACTIVE)

    students = list(scoping.scoped_users(request.user, User.objects.filter(
        role=User.Role.STUDENT,
        is_approved=User.ApprovalStatus.APPROVED,
        is_active=True,
    )).only("id", "full_name_ar", "email"))

    sids = [s.id for s in students]
    enrollments = CircleEnrollment.objects.filter(
        student_id__in=sids,
        status=CircleEnrollment.Status.ACTIVE,
    ).values_list("student_id", "circle_id")

    circle_map = {}
    for sid, cid in enrollments:
        circle_map.setdefault(sid, []).append(str(cid))

    for s in students:
        s.circle_ids = ",".join(circle_map.get(s.id, []))

    if request.method == "POST":
        template_id = request.POST.get("template")
        details = request.POST.get("details", "")
        circle_name = request.POST.get("circle_name", "")

        if not template_id:
            messages.error(request, "يرجى اختيار القالب")
            return render(request, "certificates/generate.html", {
                "templates": templates, "circles": circles, "students": students,
            })

        template = get_object_or_404(CertificateTemplate, id=template_id, is_active=True)

        raw_ids = request.POST.getlist("students")
        student_ids = []
        for x in raw_ids:
            try:
                student_ids.append(uuid.UUID(x))
            except (ValueError, TypeError):
                pass

        if not student_ids:
            messages.error(request, "لم يتم اختيار أي طالب")
            return render(request, "certificates/generate.html", {
                "templates": templates, "circles": circles, "students": students,
            })

        if "pdf_file" not in request.FILES:
            messages.error(request, "يرجى رفع ملف PDF")
            return render(request, "certificates/generate.html", {
                "templates": templates, "circles": circles, "students": students,
            })

        from django.core.files.base import ContentFile
        uploaded = request.FILES["pdf_file"]
        if not uploaded.name.lower().endswith(".pdf"):
            messages.error(request, "يجب رفع ملف PDF فقط")
            return render(request, "certificates/generate.html", {
                "templates": templates, "circles": circles, "students": students,
            })

        pdf_data = uploaded.read()
        # Re-scope on the server: a tampered POST cannot target a student
        # outside the issuer's supervised batches.
        students_qs = scoping.scoped_users(
            request.user,
            User.objects.filter(id__in=student_ids, role=User.Role.STUDENT),
        )

        metadata = {}
        if circle_name:
            metadata["circle_name"] = circle_name

        success_count = 0
        errors = []
        for student in students_qs:
            try:
                from .services import generate_certificate_number
                cert = Certificate(
                    student=student,
                    template=template,
                    certificate_number=generate_certificate_number(),
                    status="issued",
                    issue_date=timezone.now().date(),
                    details=details,
                    issued_by=request.user,
                    metadata=metadata,
                )
                cert.pdf_file.save(uploaded.name, ContentFile(pdf_data), save=False)
                cert.save()

                from apps.notifications.models import Notification
                Notification.objects.create(
                    recipient=student,
                    type=Notification.Type.CERTIFICATE,
                    title="شهادة جديدة",
                    message=f"تم إصدار شهادة {template.name} لك. يمكنك الاطلاع عليها وتحميلها من صفحة الشهادات.",
                    link="/dashboard/certificates/own/",
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
        "students": students,
    })


@login_required
def teacher_certificate_create(request):
    if request.user.role != User.Role.TEACHER:
        raise PermissionDenied

    templates = CertificateTemplate.objects.filter(is_active=True)

    from apps.circles.models import Circle, CircleEnrollment
    teacher_circles = Circle.objects.filter(teacher=request.user, status=Circle.Status.ACTIVE)
    teacher_student_ids = CircleEnrollment.objects.filter(
        circle__in=teacher_circles,
        status=CircleEnrollment.Status.ACTIVE,
    ).values_list("student_id", flat=True).distinct()

    students = list(User.objects.filter(
        id__in=teacher_student_ids,
        role=User.Role.STUDENT,
        is_approved=User.ApprovalStatus.APPROVED,
        is_active=True,
    ).only("id", "full_name_ar", "email"))

    if request.method == "POST":
        template_id = request.POST.get("template")
        student_id = request.POST.get("student")
        details = request.POST.get("details", "")
        circle_name = request.POST.get("circle_name", "")

        if not template_id or not student_id:
            messages.error(request, "يرجى اختيار القالب والطالب")
            return render(request, "certificates/teacher_create.html", {
                "templates": templates, "students": students,
            })

        template = get_object_or_404(CertificateTemplate, id=template_id, is_active=True)
        try:
            student = User.objects.get(id=uuid.UUID(student_id), role=User.Role.STUDENT)
        except (ValueError, TypeError, User.DoesNotExist):
            messages.error(request, "الطالب غير موجود")
            return render(request, "certificates/teacher_create.html", {
                "templates": templates, "students": students,
            })

        metadata = {}
        if circle_name:
            metadata["circle_name"] = circle_name

        try:
            from .services import generate_certificate_number
            cert = Certificate(
                student=student,
                template=template,
                certificate_number=generate_certificate_number(),
                status="pending_upload",
                issue_date=timezone.now().date(),
                details=details,
                issued_by=request.user,
                metadata=metadata,
            )
            cert.save()
            messages.success(request, f"تم تقديم طلب الشهادة للطالب {student.full_name_ar}")

            from apps.notifications.models import Notification
            admins = User.objects.filter(
                role__in=[User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN],
                is_active=True,
            )
            for admin in admins:
                Notification.objects.create(
                    recipient=admin,
                    type=Notification.Type.CERTIFICATE,
                    title="طلب شهادة جديد",
                    message=f"قام المعلم {request.user.full_name_ar} بطلب إصدار شهادة {template.name} للطالب {student.full_name_ar}. يرجى رفع ملف PDF لإتمام الإصدار.",
                    link="/dashboard/certificates/",
                )
        except Exception as e:
            messages.error(request, f"حدث خطأ: {e}")

        return redirect("certificates:teacher_list")

    return render(request, "certificates/teacher_create.html", {
        "templates": templates,
        "students": students,
    })


@login_required
def teacher_certificate_list(request):
    if request.user.role != User.Role.TEACHER:
        raise PermissionDenied
    certs = Certificate.objects.filter(issued_by=request.user).select_related(
        "student", "template"
    ).order_by("-created_at")
    return render(request, "certificates/teacher_list.html", {"certificates": certs})


@login_required
def certificate_upload_pdf(request, pk):
    cert = get_object_or_404(Certificate, pk=pk)
    _require_cert_access(request.user, cert)

    if request.method == "POST":
        if "pdf_file" not in request.FILES:
            messages.error(request, "يرجى رفع ملف PDF")
            return redirect("certificates:list")

        from django.core.files.base import ContentFile
        uploaded = request.FILES["pdf_file"]
        if not uploaded.name.lower().endswith(".pdf"):
            messages.error(request, "يجب رفع ملف PDF فقط")
            return redirect("certificates:list")

        pdf_data = uploaded.read()
        cert.pdf_file.save(uploaded.name, ContentFile(pdf_data))
        cert.status = "issued"
        cert.save(update_fields=["status"])

        messages.success(request, f"تم رفع الملف وإصدار الشهادة {cert.certificate_number}")

        from apps.notifications.models import Notification
        Notification.objects.create(
            recipient=cert.student,
            type=Notification.Type.CERTIFICATE,
            title="شهادة جديدة",
            message=f"تم إصدار شهادة {cert.template.name} لك. يمكنك الاطلاع عليها وتحميلها من صفحة الشهادات.",
            link="/dashboard/certificates/own/",
        )
        return redirect("certificates:list")

    return render(request, "certificates/upload_pdf.html", {"certificate": cert})


@login_required
def certificate_download(request, pk):
    cert = get_object_or_404(Certificate, pk=pk)
    _require_cert_access(request.user, cert, allow_owner=True)
    if not cert.pdf_file:
        messages.error(request, "لم يتم رفع ملف PDF بعد")
        return redirect("certificates:list")
    try:
        return FileResponse(cert.pdf_file.open(), as_attachment=True, filename=f"{cert.certificate_number}.pdf")
    except FileNotFoundError:
        messages.error(request, "ملف PDF غير موجود على الخادم، يرجى إعادة رفعه")
        return redirect("certificates:list")


@login_required
def certificate_preview(request, pk):
    cert = get_object_or_404(Certificate, pk=pk)
    _require_cert_access(request.user, cert, allow_owner=True)
    if cert.pdf_file:
        try:
            return FileResponse(cert.pdf_file.open(), content_type="application/pdf")
        except FileNotFoundError:
            messages.error(request, "ملف PDF غير موجود على الخادم، يرجى إعادة رفعه")
            return redirect("certificates:list")
    pdf_bytes = generate_certificate_pdf(cert)
    return HttpResponse(pdf_bytes, content_type="application/pdf")


@login_required
def certificate_notify(request, pk):
    cert = get_object_or_404(Certificate, pk=pk)
    _require_cert_access(request.user, cert)
    if request.method == "POST":
        if cert.status != "issued" or not cert.pdf_file:
            messages.error(request, "يجب رفع ملف PDF أولاً قبل إرسال الإشعار")
            return redirect("certificates:list")
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
    cert = get_object_or_404(Certificate, pk=pk)
    _require_cert_access(request.user, cert)
    if request.method == "POST":
        cert.status = "revoked"
        cert.save(update_fields=["status"])
        messages.success(request, "تم إلغاء الشهادة")
        return redirect("certificates:list")
    return render(request, "certificates/revoke.html", {"certificate": cert})

import io
import uuid

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone
from weasyprint import HTML

from .models import Certificate, CertificateTemplate


def generate_certificate_number():
    today = timezone.now().date()
    prefix = "CERT"
    date_str = today.strftime("%Y%m%d")
    count = Certificate.objects.filter(issue_date=today).count()
    return f"{prefix}-{date_str}-{count + 1:04d}"


def generate_certificate_pdf(certificate: Certificate) -> bytes:
    template = certificate.template
    student = certificate.student
    issue_date = certificate.issue_date or timezone.now().date()
    context = {
        "student_name": student.full_name_ar,
        "circle_name": certificate.metadata.get("circle_name", ""),
        "date": issue_date.strftime("%d/%m/%Y"),
        "details": certificate.details,
        "certificate_number": certificate.certificate_number,
        "header_text": template.header_text,
        "body_template": template.body_template,
        "footer_text": template.footer_text,
        "metadata": certificate.metadata,
    }

    body = template.body_template.format(**context)
    context["body"] = body

    html_str = render_to_string("certificates/certificate_pdf.html", context)
    pdf_bytes = HTML(string=html_str).write_pdf()
    return pdf_bytes


def issue_certificate(student, template, issued_by, details="", metadata=None):
    cert = Certificate(
        student=student,
        template=template,
        certificate_number=generate_certificate_number(),
        status="issued",
        issue_date=timezone.now().date(),
        details=details,
        issued_by=issued_by,
        metadata=metadata or {},
    )
    pdf_bytes = generate_certificate_pdf(cert)
    from django.core.files.base import ContentFile
    cert.pdf_file.save(f"{cert.certificate_number}.pdf", ContentFile(pdf_bytes), save=False)
    cert.save()
    return cert

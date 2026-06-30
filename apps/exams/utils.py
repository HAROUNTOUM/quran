from __future__ import annotations

import io
from typing import Any, Dict, Optional

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone
from weasyprint import HTML


def generate_exam_pdf(export_data: Dict[str, Any], template: str = "exams/pdf/result_sheet.html") -> bytes:
    html_str = render_to_string(template, {"data": export_data})
    pdf_bytes = HTML(string=html_str).write_pdf()
    return pdf_bytes


def generate_exam_csv(export_data: Dict[str, Any]) -> str:
    import csv

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["اسم الطالب", "الدرجة", "النسبة المئوية", "التقدير", "النتيجة", "ملاحظات"])
    for mark in export_data.get("marks", []):
        writer.writerow([
            mark.get("student_name", ""),
            mark.get("marks_obtained", ""),
            mark.get("percentage", ""),
            mark.get("grade", ""),
            "ناجح" if mark.get("is_passed") else "راسب",
            mark.get("notes", ""),
        ])
    return output.getvalue()

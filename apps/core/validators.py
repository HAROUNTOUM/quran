"""Upload validators (HAF-11).

Baseline ingestion guards for user-supplied files: a size ceiling on every
upload, plus an extension check on PDFs (ImageField already validates images
via Pillow). Keeps the app off the unbounded-upload path without a heavy
content-sniffing dependency.
"""
from django.core.exceptions import ValidationError

MAX_UPLOAD_MB = 5
_MAX_BYTES = MAX_UPLOAD_MB * 1024 * 1024


def validate_file_size(f):
    if getattr(f, "size", 0) and f.size > _MAX_BYTES:
        raise ValidationError(
            f"حجم الملف يتجاوز الحد الأقصى ({MAX_UPLOAD_MB} ميغابايت)"
        )


def validate_pdf(f):
    validate_file_size(f)
    name = (getattr(f, "name", "") or "").lower()
    if not name.endswith(".pdf"):
        raise ValidationError("يجب أن يكون الملف بصيغة PDF")

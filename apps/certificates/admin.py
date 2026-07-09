from django.contrib import admin

from .models import Certificate, CertificateTemplate


@admin.register(CertificateTemplate)
class CertificateTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "is_active")
    list_filter = ("category", "is_active")
    search_fields = ("name",)


@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    list_display = ("certificate_number", "student", "template", "issue_date", "status")
    list_filter = ("status", "template__category", "issue_date")
    search_fields = ("certificate_number", "student__full_name_ar")
    date_hierarchy = "issue_date"
    readonly_fields = ("certificate_number", "created_at", "updated_at")

from django.contrib import admin

from apps.emailcenter.models import EmailCampaign, EmailLog


@admin.register(EmailCampaign)
class EmailCampaignAdmin(admin.ModelAdmin):
    list_display = ("subject", "audience", "status", "sent_count", "failed_count", "created_at")
    list_filter = ("status", "audience")
    search_fields = ("subject",)
    readonly_fields = ("total_recipients", "sent_count", "failed_count", "sent_at")


@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    list_display = ("to_email", "category", "status", "created_at")
    list_filter = ("status", "category")
    search_fields = ("to_email", "subject")

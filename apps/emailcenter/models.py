"""Email center: admin-composed broadcasts + a delivery log for every email
the platform sends (manual or automatic).

Given the platform runs on a host that blocks outbound SMTP (delivery goes
through the Brevo HTTPS API), an auditable per-recipient log is not a luxury —
it is the only way an admin can tell whether mail actually left the building.
Every send, whether an admin broadcast or an automatic approval/reminder mail,
writes one ``EmailLog`` row through :mod:`apps.emailcenter.services`.
"""
from django.conf import settings
from django.db import models


class EmailCategory(models.TextChoices):
    """Delivery categories. The auto-mail ones (all but BROADCAST) are gated by
    the matching ``automail_*`` system setting; BROADCAST is a deliberate admin
    action and is never auto-gated."""

    BROADCAST = "broadcast", "رسالة إدارية"
    APPROVAL = "approvals", "اعتماد/رفض حساب"
    REMINDER = "reminders", "تذكير"
    UPDATE = "updates", "تحديثات وإعلانات"
    CERTIFICATE = "certificates", "شهادة"


class Audience(models.TextChoices):
    ALL = "all", "كل المستخدمين"
    ROLE = "role", "دور محدد"
    CIRCLE = "circle", "حلقة محددة"
    USER = "user", "مستخدم واحد"


class EmailCampaignQuerySet(models.QuerySet):
    def for_list(self):
        """Rows for the admin list view without N+1 on the author."""
        return self.select_related("created_by", "audience_circle", "audience_user")

    def sent(self):
        return self.filter(status=EmailCampaign.Status.SENT)


class EmailCampaign(models.Model):
    """One admin-composed message and the audience it targets."""

    class Status(models.TextChoices):
        QUEUED = "queued", "في الانتظار"
        SENDING = "sending", "جارٍ الإرسال"
        SENT = "sent", "أُرسلت"
        FAILED = "failed", "فشلت"

    subject = models.CharField("الموضوع", max_length=255)
    body = models.TextField("النص")
    audience = models.CharField(
        "الجمهور", max_length=10, choices=Audience.choices, default=Audience.ALL
    )
    # Only one of these is used, per `audience`.
    audience_role = models.CharField("الدور", max_length=20, blank=True)
    audience_circle = models.ForeignKey(
        "circles.Circle", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+", verbose_name="الحلقة",
    )
    audience_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+", verbose_name="المستخدم",
    )

    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.QUEUED, db_index=True
    )
    total_recipients = models.PositiveIntegerField(default=0)
    sent_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="email_campaigns", verbose_name="أنشأها",
    )
    # When set, the campaign is sent through this connected Gmail (the admin's
    # own address as the sender) instead of the platform SMTP/Brevo backend.
    sender_account = models.ForeignKey(
        "emailcenter.GmailAccount", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="campaigns", verbose_name="المرسل (Gmail)",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    objects = EmailCampaignQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["-created_at"])]
        verbose_name = "حملة بريدية"
        verbose_name_plural = "الحملات البريدية"

    def __str__(self):
        return self.subject


class EmailLog(models.Model):
    """One row per recipient send attempt — the deliverability audit trail."""

    class Status(models.TextChoices):
        SENT = "sent", "أُرسلت"
        FAILED = "failed", "فشلت"
        SKIPPED = "skipped", "متوقفة"  # category disabled by an admin toggle

    campaign = models.ForeignKey(
        EmailCampaign, on_delete=models.CASCADE, null=True, blank=True,
        related_name="logs", verbose_name="الحملة",
    )
    category = models.CharField(
        max_length=20, choices=EmailCategory.choices, default=EmailCategory.BROADCAST
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="email_logs", verbose_name="المستلم",
    )
    to_email = models.EmailField("البريد")
    subject = models.CharField("الموضوع", max_length=255)
    status = models.CharField(max_length=10, choices=Status.choices)
    error = models.TextField("الخطأ", blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["category", "-created_at"]),
        ]
        verbose_name = "سجل بريد"
        verbose_name_plural = "سجل البريد"

    def __str__(self):
        return f"{self.to_email} — {self.get_status_display()}"


class GmailAccount(models.Model):
    """A Gmail address an admin/sub-admin connected via Google OAuth so the
    platform can send email *as them* (gmail.send scope). The refresh token
    is stored signed with SECRET_KEY — never render it anywhere."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="gmail_account", verbose_name="المستخدم",
    )
    email = models.EmailField("بريد Gmail")
    refresh_token_signed = models.TextField(editable=False)
    access_token = models.TextField(blank=True, editable=False)
    access_token_expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField("مفعّل", default=True)
    connected_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "حساب Gmail مرتبط"
        verbose_name_plural = "حسابات Gmail المرتبطة"

    def __str__(self):
        return f"{self.email} — {self.user.full_name_ar}"

    # ── refresh-token at-rest signing ────────────────────────────────
    def set_refresh_token(self, raw: str):
        from django.core import signing
        self.refresh_token_signed = signing.dumps(raw, salt="gmail-refresh")

    def get_refresh_token(self) -> str:
        from django.core import signing
        return signing.loads(self.refresh_token_signed, salt="gmail-refresh")

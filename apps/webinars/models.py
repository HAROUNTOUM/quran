import re
import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.accounts.models import User
from django.utils import timezone

from apps.core.models import TimeStampedModel


def generate_speaker_room_name() -> str:
    """Unguessable Jitsi room for the small speaker group only."""
    return f"hafezwebinar-{secrets.token_hex(12)}"


_YOUTUBE_PATTERNS = [
    re.compile(r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/live/)([\w-]{6,})"),
]


def parse_stream_embed(stream_url, host):
    """Map a stream URL to (embed_url, chat_url).

    YouTube Live gets a native player + its own live-chat sidebar (the chat
    requirement is satisfied by the streaming platform's embed — the
    platform itself ships no chat infrastructure, per Non-Negotiable #1's
    spirit). Any other URL is embedded as-is with no chat column.
    """
    if not stream_url:
        return None, None
    for pattern in _YOUTUBE_PATTERNS:
        match = pattern.search(stream_url)
        if match:
            video_id = match.group(1)
            return (
                f"https://www.youtube.com/embed/{video_id}?autoplay=1",
                f"https://www.youtube.com/live_chat?v={video_id}&embed_domain={host}",
            )
    return stream_url, None


class Webinar(TimeStampedModel):
    """One-off admin broadcast (Non-Negotiable #4): a small speaker group in
    a real Jitsi call, streamed out one-to-many; the audience watches the
    stream + chat sidebar and is NEVER inside the Jitsi room."""

    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "مجدولة"
        LIVE = "live", "مباشرة"
        ENDED = "ended", "منتهية"
        REPLAY = "replay", "إعادة"

    title = models.CharField("العنوان", max_length=255)
    description = models.TextField("الوصف", blank=True)
    scheduled_at = models.DateTimeField("موعد البث")
    stream_url = models.URLField(
        "رابط البث", max_length=500, blank=True,
        help_text="رابط YouTube Live (أو ما يعادله) الذي يشاهده الجمهور",
    )
    speaker_room_name = models.CharField(
        "غرفة المتحدثين", max_length=64, unique=True,
        default=generate_speaker_room_name,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="webinars_created", verbose_name="أنشأها",
        limit_choices_to={"role": User.Role.MAIN_ADMIN},
    )
    co_speakers = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True,
        related_name="webinars_speaking", verbose_name="المتحدثون",
    )
    status = models.CharField(
        "الحالة", max_length=20, choices=Status.choices, default=Status.SCHEDULED,
    )
    is_active = models.BooleanField("مفعلة", default=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-scheduled_at"]
        verbose_name = "ندوة"
        verbose_name_plural = "الندوات"

    def __str__(self):
        return self.title

    # ------------------------------------------------------------------
    # Permissions — creation/management is admin-only; the speaker Jitsi
    # room is restricted to admins + designated co-speakers; viewing is
    # any authenticated user (the platform is approval-gated already).
    # ------------------------------------------------------------------

    @staticmethod
    def can_manage(user) -> bool:
        return user.is_authenticated and user.role == User.Role.MAIN_ADMIN

    def can_join_speaker_room(self, user) -> bool:
        if not user.is_authenticated:
            return False
        if user.role == User.Role.MAIN_ADMIN:
            return True
        return self.co_speakers.filter(pk=user.pk).exists()

    def can_view(self, user) -> bool:
        return user.is_authenticated and self.is_active

    # ------------------------------------------------------------------
    # Lifecycle: scheduled → live → ended → (optionally) replay.
    # ------------------------------------------------------------------

    def start(self, by):
        if not self.can_manage(by):
            raise ValidationError("بدء الندوات صلاحية المشرف العام فقط")
        if self.status != self.Status.SCHEDULED:
            raise ValidationError("لا يمكن بدء ندوة ليست في حالة الجدولة")
        self.status = self.Status.LIVE
        self.started_at = timezone.now()
        self.save(update_fields=["status", "started_at", "updated_at"])
        return self

    def end(self, by):
        if not self.can_manage(by):
            raise ValidationError("إنهاء الندوات صلاحية المشرف العام فقط")
        if self.status != self.Status.LIVE:
            raise ValidationError("لا يمكن إنهاء ندوة غير مباشرة")
        self.status = self.Status.ENDED
        self.ended_at = timezone.now()
        self.save(update_fields=["status", "ended_at", "updated_at"])
        return self

    def enable_replay(self, by):
        if not self.can_manage(by):
            raise ValidationError("إتاحة الإعادة صلاحية المشرف العام فقط")
        if self.status != self.Status.ENDED:
            raise ValidationError("الإعادة تتاح بعد انتهاء الندوة فقط")
        if not self.stream_url:
            raise ValidationError("لا يوجد رابط بث لإتاحته كإعادة")
        self.status = self.Status.REPLAY
        self.save(update_fields=["status", "updated_at"])
        return self

    @property
    def is_watchable(self) -> bool:
        return self.status in (self.Status.LIVE, self.Status.REPLAY) and bool(self.stream_url)

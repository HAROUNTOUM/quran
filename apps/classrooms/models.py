import secrets

from django.conf import settings
from django.db import IntegrityError, models

from apps.accounts.models import User
from apps.core.models import TimeStampedModel


def generate_room_name() -> str:
    """Unguessable Jitsi room name — never derived from teacher name/id."""
    return f"hafezroom-{secrets.token_hex(12)}"


def generate_room_slug() -> str:
    """Random public URL slug, independent of the internal room name so the
    Jitsi room can be rotated without breaking shared links."""
    return secrets.token_urlsafe(9)


class TeacherRoom(TimeStampedModel):
    """Permanent virtual classroom — exactly one per teacher, created once,
    reused for every class (Non-Negotiable #3). Never per-session."""

    teacher = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="room", verbose_name="المعلم",
        limit_choices_to={"role": "teacher"},
    )
    slug = models.SlugField("معرف الرابط", max_length=32, unique=True, default=generate_room_slug)
    room_name = models.CharField("اسم غرفة Jitsi", max_length=64, unique=True, default=generate_room_name)
    is_active = models.BooleanField("مفعلة", default=True)

    class Meta:
        verbose_name = "قاعة معلم"
        verbose_name_plural = "قاعات المعلمين"

    def __str__(self):
        return f"قاعة {self.teacher.full_name_ar}"

    # ------------------------------------------------------------------

    @classmethod
    def get_or_create_for(cls, teacher):
        """Idempotent provisioning with a one-shot retry should the
        astronomically unlikely random collision ever happen."""
        try:
            room, _ = cls.objects.get_or_create(teacher=teacher)
            return room
        except IntegrityError:
            return cls.objects.create(
                teacher=teacher,
                slug=generate_room_slug(),
                room_name=generate_room_name(),
            )

    def can_join(self, user) -> bool:
        """Access policy (Section C, checked in order by the view):
        room active + teacher account active → owner always passes
        (independent of enrollment) → admin/supervisor oversight →
        otherwise an active enrollment with this teacher is required.
        Never URL obscurity."""
        if not (self.is_active and self.teacher.is_active):
            return False
        if not user.is_authenticated:
            return False
        if user.pk == self.teacher_id:
            return True
        if user.role in (User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN):
            return True
        return user.studies_with_teacher(self.teacher)

    def regenerate_room_name(self):
        """Rotate the internal Jitsi room (e.g. if the name leaked). The
        public slug — and thus every shared link — stays stable."""
        self.room_name = generate_room_name()
        self.save(update_fields=["room_name", "updated_at"])
        return self.room_name

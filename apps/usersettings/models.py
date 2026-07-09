from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction

from apps.accounts.models import User
from apps.core.models import TimeStampedModel
from apps.usersettings import registry


class SettingsChangeHistory(models.Model):
    """Immutable audit trail for every settings write (mandatory for
    critical settings, recorded for all). `user` is NULL for system-scope
    changes."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        null=True, blank=True, related_name="settings_changes",
        verbose_name="المستخدم المتأثر",
    )
    key = models.CharField("الإعداد", max_length=100)
    old_value = models.JSONField("القيمة السابقة", null=True)
    new_value = models.JSONField("القيمة الجديدة", null=True)
    is_critical = models.BooleanField("حرج", default=False)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name="settings_changes_made",
        verbose_name="غُيِّر بواسطة",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "سجل تغيير إعداد"
        verbose_name_plural = "سجل تغييرات الإعدادات"
        indexes = [models.Index(fields=["key", "-created_at"])]

    def __str__(self):
        who = self.user.full_name_ar if self.user else "النظام"
        return f"{self.key} ({who})"


class UserSettings(TimeStampedModel):
    """Per-user settings store. Values live in `data` keyed by registry key;
    a missing key means 'registry default'. All reads/writes go through
    get()/set() so validation + history are never skipped."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="settings", verbose_name="المستخدم",
    )
    data = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "إعدادات مستخدم"
        verbose_name_plural = "إعدادات المستخدمين"

    def __str__(self):
        return f"إعدادات {self.user.full_name_ar}"

    def _spec_for_write(self, key):
        spec = registry.get_spec(key)
        if spec.scope != registry.USER_SCOPE:
            raise ValidationError(f"{spec.label}: إعداد نظام — لا يُخزَّن على مستوى المستخدم")
        if self.user.role not in spec.roles:
            raise ValidationError(f"{spec.label}: غير متاح لدورك")
        return spec

    def get(self, key):
        spec = registry.get_spec(key)
        return self.data.get(key, spec.default)

    def set(self, key, value, changed_by=None):
        """The only supported write path: validates against the registry,
        records history, persists. Returns the cleaned value."""
        spec = self._spec_for_write(key)
        cleaned = registry.clean_value(spec, value)
        old = self.data.get(key, spec.default)
        if old == cleaned:
            return cleaned  # no-op: nothing to store or log
        self.data[key] = cleaned
        self.save(update_fields=["data", "updated_at"])
        SettingsChangeHistory.objects.create(
            user=self.user, key=key, old_value=old, new_value=cleaned,
            is_critical=spec.critical, changed_by=changed_by or self.user,
        )
        return cleaned

    def as_dict(self) -> dict:
        """Effective settings for this user's role (defaults merged with stored)."""
        merged = registry.defaults_for_role(self.user.role)
        for key, value in self.data.items():
            if key in merged:
                merged[key] = value
        return merged

    @transaction.atomic
    def reset_to_defaults(self, changed_by=None):
        """Back to registry defaults, logging one history row per changed key."""
        for key, stored in list(self.data.items()):
            spec = registry.REGISTRY.get(key)
            if spec is None:
                continue
            if stored != spec.default:
                SettingsChangeHistory.objects.create(
                    user=self.user, key=key, old_value=stored,
                    new_value=spec.default, is_critical=spec.critical,
                    changed_by=changed_by or self.user,
                )
        self.data = {}
        self.save(update_fields=["data", "updated_at"])

    @classmethod
    @transaction.atomic
    def bulk_push(cls, role, key, value, changed_by):
        """Admin bulk-push one setting value to every user of a role.
        Validates once against the registry, logs per-user history.
        Returns the number of users updated."""
        spec = registry.get_spec(key)
        if spec.scope != registry.USER_SCOPE or role not in spec.roles:
            raise ValidationError(f"{spec.label}: لا ينطبق على دور {role}")
        cleaned = registry.clean_value(spec, value)

        updated = 0
        qs = cls.objects.select_related("user").filter(user__role=role)
        for user_settings in qs.iterator():
            old = user_settings.data.get(key, spec.default)
            if old == cleaned:
                continue
            user_settings.data[key] = cleaned
            user_settings.save(update_fields=["data", "updated_at"])
            SettingsChangeHistory.objects.create(
                user=user_settings.user, key=key, old_value=old,
                new_value=cleaned, is_critical=spec.critical,
                changed_by=changed_by,
            )
            updated += 1
        return updated


class SystemSettings(models.Model):
    """Singleton store for system-scope settings (admin-managed)."""

    data = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "إعدادات النظام"
        verbose_name_plural = "إعدادات النظام"

    def __str__(self):
        return "إعدادات النظام"

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def get(self, key):
        spec = registry.get_spec(key)
        if spec.scope != registry.SYSTEM_SCOPE:
            raise ValidationError(f"{spec.label}: ليس إعداد نظام")
        return self.data.get(key, spec.default)

    def set(self, key, value, changed_by):
        """Admin-only validated write with mandatory history."""
        spec = registry.get_spec(key)
        if spec.scope != registry.SYSTEM_SCOPE:
            raise ValidationError(f"{spec.label}: ليس إعداد نظام")
        if changed_by is None or changed_by.role != User.Role.MAIN_ADMIN:
            raise ValidationError("إعدادات النظام يعدّلها المشرف العام فقط")
        cleaned = registry.clean_value(spec, value)
        old = self.data.get(key, spec.default)
        if old == cleaned:
            return cleaned
        self.data[key] = cleaned
        self.save(update_fields=["data", "updated_at"])
        SettingsChangeHistory.objects.create(
            user=None, key=key, old_value=old, new_value=cleaned,
            is_critical=spec.critical, changed_by=changed_by,
        )
        return cleaned

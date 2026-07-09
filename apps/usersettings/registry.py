from apps.accounts.models import User

"""Settings registry (Section B).

Every setting the platform supports is declared here: key, type, allowed
values/range, default, scope, which roles may see/edit it, and whether it
is critical. Every write anywhere in the system validates against this
registry — there is no other write path.

Scopes:
    user   — stored per-user on UserSettings.data
    system — stored once on SystemSettings.data, admin-editable
"""
from dataclasses import dataclass, field
from datetime import date, datetime

from django.core.exceptions import ValidationError

USER_SCOPE = "user"
SYSTEM_SCOPE = "system"


@dataclass(frozen=True)
class SettingSpec:
    key: str
    label: str
    type: str                     # bool | int | choice | date | str
    default: object
    scope: str = USER_SCOPE
    roles: tuple = ()             # user-scope: roles that see/edit it
    critical: bool = False        # critical ⇒ mandatory history + re-auth (Phase 4)
    min_value: int = None
    max_value: int = None
    choices: tuple = ()           # ((value, label), ...)
    help_text: str = ""
    group: str = ""


_SPECS = [
    # ── System scope (admin-managed) ─────────────────────────────────
    SettingSpec(
        key="maintenance_mode", label="وضع الصيانة", type="bool", default=False,
        scope=SYSTEM_SCOPE, critical=True, group="النظام",
        help_text="عند التفعيل يُمنع دخول غير المشرفين وتظهر صفحة صيانة",
    ),
    SettingSpec(
        key="max_students_per_teacher", label="الحد الأقصى للطلاب لكل معلم",
        type="int", default=30, min_value=1, max_value=200,
        scope=SYSTEM_SCOPE, critical=True, group="النظام",
    ),
    SettingSpec(
        key="auto_approve_requests", label="اعتماد الطلبات تلقائياً",
        type="bool", default=False, scope=SYSTEM_SCOPE, group="النظام",
        help_text="اعتماد طلبات الدعم الجديدة تلقائياً دون مراجعة",
    ),
    SettingSpec(
        key="default_session_timeout_minutes", label="مهلة الجلسة الافتراضية (دقائق)",
        type="int", default=60, min_value=5, max_value=480,
        scope=SYSTEM_SCOPE, critical=True, group="النظام",
        help_text="مدة خمول تسجيل الدخول قبل انتهاء الجلسة",
    ),
    SettingSpec(
        key="grade_calculation_method", label="طريقة حساب المعدل",
        type="choice", default="simple_average",
        choices=(("simple_average", "متوسط بسيط"), ("normalized_percent", "نسبة مئوية موزونة")),
        scope=SYSTEM_SCOPE, critical=True, group="الأكاديمية",
    ),
    SettingSpec(
        key="academic_term_start", label="بداية الفصل الدراسي", type="date",
        default=None, scope=SYSTEM_SCOPE, critical=True, group="الأكاديمية",
    ),
    SettingSpec(
        key="academic_term_end", label="نهاية الفصل الدراسي", type="date",
        default=None, scope=SYSTEM_SCOPE, critical=True, group="الأكاديمية",
    ),
    SettingSpec(
        key="request_overdue_days", label="أيام تأخر الطلب",
        type="int", default=3, min_value=1, max_value=30,
        scope=SYSTEM_SCOPE, group="النظام",
        help_text="عدد الأيام قبل اعتبار الطلب المفتوح متأخراً",
    ),
    SettingSpec(
        key="feature_exams_enabled", label="تفعيل وحدة الامتحانات",
        type="bool", default=True, scope=SYSTEM_SCOPE, group="الوحدات",
    ),
    SettingSpec(
        key="feature_certificates_enabled", label="تفعيل وحدة الشهادات",
        type="bool", default=True, scope=SYSTEM_SCOPE, group="الوحدات",
    ),
    SettingSpec(
        key="feature_leaderboard_enabled", label="تفعيل لوحة المتفوقين",
        type="bool", default=True, scope=SYSTEM_SCOPE, group="الوحدات",
    ),
    SettingSpec(
        key="feature_webinars_enabled", label="تفعيل وحدة الندوات",
        type="bool", default=True, scope=SYSTEM_SCOPE, group="الوحدات",
    ),

    # ── Automatic email categories ───────────────────────────────────
    # Master + per-category switches read by apps.emailcenter.services.
    SettingSpec(
        key="automail_enabled", label="تفعيل البريد التلقائي", type="bool",
        default=True, scope=SYSTEM_SCOPE, group="البريد الإلكتروني",
        help_text="المفتاح الرئيسي: عند إيقافه تتوقف كل الرسائل التلقائية",
    ),
    SettingSpec(
        key="automail_approvals", label="بريد اعتماد/رفض الحسابات", type="bool",
        default=True, scope=SYSTEM_SCOPE, group="البريد الإلكتروني",
        help_text="إرسال بريد عند اعتماد أو رفض حساب مستخدم",
    ),
    SettingSpec(
        key="automail_reminders", label="بريد التذكيرات", type="bool",
        default=True, scope=SYSTEM_SCOPE, group="البريد الإلكتروني",
        help_text="تذكيرات الحصص والمهام والمواعيد",
    ),
    SettingSpec(
        key="automail_updates", label="بريد التحديثات والإعلانات", type="bool",
        default=True, scope=SYSTEM_SCOPE, group="البريد الإلكتروني",
    ),
    SettingSpec(
        key="automail_certificates", label="بريد الشهادات", type="bool",
        default=True, scope=SYSTEM_SCOPE, group="البريد الإلكتروني",
    ),

    # ── Spaced-repetition (SRS) engine ───────────────────────────────
    SettingSpec(
        key="srs_first_interval_days", label="أول فاصل للمراجعة (أيام)",
        type="int", default=1, min_value=1, max_value=30,
        scope=SYSTEM_SCOPE, group="المراجعة المتباعدة",
        help_text="الفاصل الزمني عند أول حفظ للربع قبل أول مراجعة",
    ),
    SettingSpec(
        key="srs_max_interval_days", label="أقصى فاصل للمراجعة (أيام)",
        type="int", default=365, min_value=30, max_value=1095,
        scope=SYSTEM_SCOPE, group="المراجعة المتباعدة",
        help_text="الحد الأعلى للفاصل بين المراجعات",
    ),
    SettingSpec(
        key="srs_weak_overdue_days", label="أيام التأخر لاعتبار الحفظ ضعيفاً",
        type="int", default=7, min_value=1, max_value=90,
        scope=SYSTEM_SCOPE, group="المراجعة المتباعدة",
    ),
    SettingSpec(
        key="srs_weak_mistakes_threshold", label="حد الأخطاء لاعتبار الحفظ ضعيفاً",
        type="int", default=5, min_value=1, max_value=50,
        scope=SYSTEM_SCOPE, group="المراجعة المتباعدة",
    ),

    # ── Teacher scope ────────────────────────────────────────────────
    SettingSpec(
        key="default_session_duration_minutes", label="مدة الحصة الافتراضية (دقائق)",
        type="int", default=60, min_value=15, max_value=240,
        roles=("teacher",), group="الحصص",
    ),
    SettingSpec(
        key="auto_recording", label="تسجيل الحصص تلقائياً", type="bool",
        default=False, roles=("teacher",), group="الحصص",
    ),
    SettingSpec(
        key="allow_student_recording", label="السماح للطلاب بالتسجيل", type="bool",
        default=False, roles=("teacher",), group="الحصص",
    ),
    SettingSpec(
        key="max_participants", label="الحد الأقصى للمشاركين", type="int",
        default=30, min_value=1, max_value=100, roles=("teacher",), group="الحصص",
    ),
    SettingSpec(
        key="require_attendance_confirmation", label="اشتراط تأكيد الحضور",
        type="bool", default=True, roles=("teacher",), group="الحصص",
    ),
    SettingSpec(
        key="default_grading_scale", label="سلم التقييم الافتراضي", type="choice",
        default="out_of_20",
        choices=(("out_of_10", "من 10"), ("out_of_20", "من 20"), ("percent", "نسبة مئوية")),
        roles=("teacher",), group="التقييم",
    ),
    SettingSpec(
        key="notify_new_requests", label="إشعار بالطلبات الجديدة", type="bool",
        default=True, roles=("teacher",), group="الإشعارات",
    ),
    SettingSpec(
        key="notify_overdue_items", label="إشعار بالعناصر المتأخرة", type="bool",
        default=True, roles=("teacher",), group="الإشعارات",
    ),
    SettingSpec(
        key="calendar_visible_to_students", label="إظهار التقويم للطلاب", type="bool",
        default=True, roles=("teacher",), group="الحصص",
    ),

    # ── Student scope ────────────────────────────────────────────────
    SettingSpec(
        key="notify_channel_inapp", label="إشعارات داخل المنصة", type="bool",
        default=True, roles=("student",), group="الإشعارات",
    ),
    SettingSpec(
        key="notify_channel_email", label="إشعارات البريد الإلكتروني", type="bool",
        default=False, roles=("student",), group="الإشعارات",
    ),
    SettingSpec(
        key="email_digest_frequency", label="ملخص البريد الدوري", type="choice",
        default="weekly",
        choices=(("never", "أبداً"), ("daily", "يومي"), ("weekly", "أسبوعي")),
        roles=("student",), group="الإشعارات",
    ),
    # NOTE: the parent role was dropped (the platform is for adults), so the
    # former `grades_visible_to_parents` setting was removed — it controlled
    # nothing (HAF-22).
]

REGISTRY: dict = {spec.key: spec for spec in _SPECS}

assert len(REGISTRY) == len(_SPECS), "duplicate setting keys in registry"

_TRUTHY = {"true", "1", "yes", "on"}
_FALSY = {"false", "0", "no", "off", ""}


def get_spec(key) -> SettingSpec:
    try:
        return REGISTRY[key]
    except KeyError:
        raise ValidationError(f"إعداد غير معروف: {key}")


def specs_for_role(role, scope=USER_SCOPE):
    """The settings a given role may see/edit. System scope: admins only."""
    if scope == SYSTEM_SCOPE:
        if role != User.Role.MAIN_ADMIN:
            return []
        return [s for s in _SPECS if s.scope == SYSTEM_SCOPE]
    return [s for s in _SPECS if s.scope == USER_SCOPE and role in s.roles]


def defaults_for_role(role) -> dict:
    return {s.key: s.default for s in specs_for_role(role)}


def clean_value(spec: SettingSpec, value):
    """Validate & normalize a raw value against its spec. Raises ValidationError."""
    if spec.type == "bool":
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in _TRUTHY:
            return True
        if text in _FALSY:
            return False
        raise ValidationError(f"{spec.label}: قيمة منطقية غير صالحة")

    if spec.type == "int":
        try:
            cleaned = int(value)
        except (TypeError, ValueError):
            raise ValidationError(f"{spec.label}: يجب أن تكون رقماً صحيحاً")
        if spec.min_value is not None and cleaned < spec.min_value:
            raise ValidationError(f"{spec.label}: الحد الأدنى {spec.min_value}")
        if spec.max_value is not None and cleaned > spec.max_value:
            raise ValidationError(f"{spec.label}: الحد الأقصى {spec.max_value}")
        return cleaned

    if spec.type == "choice":
        valid = {c[0] for c in spec.choices}
        if value not in valid:
            raise ValidationError(f"{spec.label}: خيار غير صالح")
        return value

    if spec.type == "date":
        if value in (None, ""):
            return None
        if isinstance(value, datetime):
            value = value.date()
        if isinstance(value, date):
            return value.isoformat()
        try:
            return date.fromisoformat(str(value).strip()).isoformat()
        except ValueError:
            raise ValidationError(f"{spec.label}: تاريخ غير صالح (YYYY-MM-DD)")

    if spec.type == "str":
        cleaned = str(value).strip()
        if len(cleaned) > 500:
            raise ValidationError(f"{spec.label}: النص طويل جداً")
        return cleaned

    raise ValidationError(f"{spec.label}: نوع إعداد غير مدعوم")

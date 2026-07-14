"""Settings management UI (HAF-06).

The registry, validation and audit history already existed; this exposes them
so product admins/teachers/students can actually change settings without the
Django admin or a shell. Every write still goes through UserSettings.set /
SystemSettings.set, so validation (clean_value) and SettingsChangeHistory are
never bypassed.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render

from apps.accounts.models import User
from apps.usersettings import registry
from apps.usersettings.models import SystemSettings, UserSettings


def _base_template(role):
    return "dashboard/base.html"


def _raw_value(post, spec):
    """Pull one field's submitted value. Unchecked checkboxes are absent, so a
    bool spec maps to `key in post`."""
    if spec.type == "bool":
        return spec.key in post
    return post.get(spec.key, "")


def _grouped(specs, current):
    """[(group_label, [(spec, value), ...]), ...] preserving registry order."""
    groups, order = {}, []
    for spec in specs:
        g = spec.group or "أخرى"
        if g not in groups:
            groups[g] = []
            order.append(g)
        groups[g].append((spec, current.get(spec.key, spec.default)))
    return [(g, groups[g]) for g in order]


@login_required
def settings_home(request):
    user = request.user
    us, _ = UserSettings.objects.get_or_create(user=user)
    user_specs = registry.specs_for_role(user.role, registry.USER_SCOPE)
    system_specs = registry.specs_for_role(user.role, registry.SYSTEM_SCOPE)  # [] unless admin

    if request.method == "POST":
        scope = request.POST.get("scope")
        try:
            if scope == "system":
                if user.role != User.Role.MAIN_ADMIN:
                    raise ValidationError("إعدادات النظام يعدّلها المشرف العام فقط")
                store = SystemSettings.load()
                for spec in system_specs:
                    store.set(spec.key, _raw_value(request.POST, spec), changed_by=user)
            else:
                for spec in user_specs:
                    us.set(spec.key, _raw_value(request.POST, spec), changed_by=user)
            messages.success(request, "تم حفظ الإعدادات")
        except ValidationError as e:
            messages.error(request, "؛ ".join(getattr(e, "messages", [str(e)])))
        return redirect("usersettings:home")

    store = SystemSettings.load()

    # Connected-Gmail card (sender identity) — admins and sub-admins only.
    gmail_account = None
    gmail_oauth_enabled = False
    if user.role in (User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN):
        from apps.emailcenter.models import GmailAccount
        from apps.emailcenter import gmail as gmail_svc
        gmail_account = GmailAccount.objects.filter(user=user).first()
        gmail_oauth_enabled = gmail_svc.oauth_enabled()

    return render(request, "dashboard/settings/index.html", {
        "base_template": _base_template(user.role),
        "user_groups": _grouped(user_specs, us.data),
        "system_groups": _grouped(system_specs, store.data) if system_specs else [],
        "gmail_account": gmail_account,
        "gmail_oauth_enabled": gmail_oauth_enabled,
        "show_gmail_card": user.role in (User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN),
    })

import re
from datetime import timedelta
from functools import lru_cache

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect

from apps.accounts.models import User
from django.utils import timezone
from django.utils.cache import patch_vary_headers


class UserProfileMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            request.user_role = request.user.role
        return self.get_response(request)


class SecurityHeadersMiddleware:
    """Hardening headers for every response — CSP, HSTS, XSS, nosniff,
    referrer-policy, permissions-policy. CSP is intentionally relaxed on
    debug/API paths to avoid blocking dev tools and Swagger."""

    @property
    def CSP_DEFAULT(self):
        jitsi_domain = getattr(settings, "JITSI_DOMAIN", "meet.jit.si")
        jitsi_origin = f"https://{jitsi_domain}"
        return (
            "default-src 'self';"
            f"script-src 'self' 'unsafe-inline' 'unsafe-eval' {jitsi_origin} https://unpkg.com https://cdn.tailwindcss.com https://fonts.googleapis.com;"
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://unpkg.com;"
            "img-src 'self' data: https:;"
            "font-src 'self' https://fonts.gstatic.com;"
            f"connect-src 'self' ws: wss: {jitsi_origin} https://youtube.com https://www.youtube.com;"
            f"frame-src 'self' {jitsi_origin} https://www.youtube.com https://www.youtube-nocookie.com;"
            f"media-src 'self' https: {jitsi_origin};"
            "object-src 'none';"
            "base-uri 'self';"
            "form-action 'self';"
        )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        path = request.path_info

        if not getattr(settings, "SECURE_HSTS_ENABLED", True):
            return response

        if not settings.DEBUG:
            response["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
            response["X-Content-Type-Options"] = "nosniff"
            response["Referrer-Policy"] = "strict-origin-when-cross-origin"
            response["Permissions-Policy"] = (
                "camera=(self), microphone=(self), fullscreen=(self), "
                "display-capture=(self), autoplay=(self)"
            )

        csrf = getattr(settings, "CSRF_COOKIE_NAME", "csrftoken")
        session = getattr(settings, "SESSION_COOKIE_NAME", "sessionid")
        for cookie_key in (csrf, session):
            if cookie_key in response.cookies:
                c = response.cookies[cookie_key]
                c["samesite"] = "Lax"
                if not settings.DEBUG:
                    c["secure"] = True
                    c["httponly"] = True

        if not path.startswith("/admin/") and not path.startswith("/api/"):
            response["Content-Security-Policy"] = self.CSP_DEFAULT

        return response


class MaintenanceModeMiddleware:
    """If CoreSettings says maintenance_mode is on, non-admin GET requests
    (except login) see a downtime page instead of the real app."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._is_active() and not request.user.is_staff:
            allowed_paths = ("/login/", "/admin/")
            if request.method == "GET" and not request.path_info.startswith(allowed_paths):
                from django.shortcuts import render
                return render(request, "503.html", status=503)
        return self.get_response(request)

    def _is_active(self):
        # Read fresh each request so an admin toggling maintenance mode takes
        # effect immediately (the previous lru_cache pinned the first value
        # for the process lifetime).
        from apps.usersettings.services import get_system_setting
        try:
            return bool(get_system_setting("maintenance_mode"))
        except Exception:
            return False


class FeatureFlagMiddleware:
    """Central enforcement of optional-module toggles (HAF-05).

    Requests into a disabled module's URL space are bounced to the dashboard
    with a message, regardless of which sub-view they target — so disabling a
    module in settings actually takes effect everywhere, not just on the index
    page. Admins bypass (they need access to re-enable / administer)."""

    # URL path fragment → feature flag name. Webinars are intentionally omitted:
    # the webinars app already enforces its own flag (this middleware exists to
    # close the exams/certificates/leaderboard gap that had no enforcement).
    FEATURE_PATHS = (
        ("/exams/", "exams"),
        ("/certificates/", "certificates"),
        ("/leaderboard/", "leaderboard"),
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and user.role != User.Role.MAIN_ADMIN:
            path = request.path_info
            for fragment, feature in self.FEATURE_PATHS:
                if fragment in path and not self._enabled(feature):
                    messages.error(request, "هذه الوحدة غير مُفعّلة حالياً")
                    return redirect("accounts:dashboard")
        return self.get_response(request)

    @staticmethod
    def _enabled(feature):
        from apps.usersettings.services import feature_enabled
        try:
            return feature_enabled(feature)
        except Exception:
            return True  # fail soft — never lock users out on a settings error


class SessionIdleTimeoutMiddleware:
    """Log out authenticated users after a period of inactivity (HAF-11).

    The window is the admin setting `default_session_timeout_minutes`; it was
    defined in the registry but never enforced. Tracks last-activity in the
    session and, once exceeded, ends the session and redirects to login."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            now = int(timezone.now().timestamp())
            last = request.session.get("_last_activity")
            if last is not None and (now - last) > self._timeout_seconds():
                from django.contrib.auth import logout
                logout(request)
                messages.info(request, "انتهت الجلسة بسبب عدم النشاط، يرجى تسجيل الدخول مجدداً")
                return redirect(settings.LOGIN_URL)
            request.session["_last_activity"] = now
        return self.get_response(request)

    @staticmethod
    def _timeout_seconds():
        from apps.usersettings.services import get_system_setting
        try:
            return int(get_system_setting("default_session_timeout_minutes")) * 60
        except Exception:
            return 60 * 60



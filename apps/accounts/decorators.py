from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django_ratelimit.core import is_ratelimited

from apps.accounts.models import User


def auth_rate_limit(action, limit, window_seconds):
    """Per-IP POST throttle for the public auth endpoints (audit item A04).

    Backed by django-ratelimit over the shared cache (Redis in production).
    Fails open when the cache is unavailable — throttling must never take down
    login. Gated by RATELIMIT_ENABLE so dev and the test suite are unaffected.
    """
    rate = f"{limit}/{window_seconds}s"

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if request.method != "POST" or not getattr(settings, "RATELIMIT_ENABLE", True):
                return view_func(request, *args, **kwargs)
            try:
                limited = is_ratelimited(
                    request,
                    group=f"auth:{action}",
                    key="ip",
                    rate=rate,
                    method="POST",
                    increment=True,
                )
            except Exception:
                return view_func(request, *args, **kwargs)
            if limited:
                message = "محاولات كثيرة. يرجى الانتظار قليلاً ثم إعادة المحاولة."
                if getattr(request, "htmx", None):
                    return render(request, "accounts/partials/auth_message.html", {
                        "type": "error", "message": message,
                    }, status=429)
                messages.error(request, message)
                return redirect("accounts:login")
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


def role_required(*roles):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if request.user.role not in roles:
                raise PermissionDenied
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


def teacher_of_student_required(student_url_kwarg="pk"):
    """Dashboard counterpart of the API's IsTeacherOfStudent permission.

    Guards function views whose URL carries a student pk. Admin/supervisor
    pass through; a teacher passes only if User.teaches_student() confirms
    an active enrollment linking them to that student. Everyone else: 403.

    Usage:
        @login_required
        @teacher_of_student_required()          # student pk in kwargs["pk"]
        def teacher_student_progress(request, pk): ...

        @teacher_of_student_required("student_id")   # custom kwarg name
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated:
                raise PermissionDenied
            if user.role in (User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN):
                return view_func(request, *args, **kwargs)
            if user.role != User.Role.TEACHER:
                raise PermissionDenied
            student = get_object_or_404(
                User, pk=kwargs[student_url_kwarg], role=User.Role.STUDENT,
            )
            if not user.teaches_student(student):
                raise PermissionDenied
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator

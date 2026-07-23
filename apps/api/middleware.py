"""Rate limiting for the REST API surface.

Applies a single per-user (per-IP for anonymous) budget to every ``/api/``
request via django-ratelimit's core helper, instead of decorating each of the
~40 view classes. Returns the project's standard JSON error envelope with HTTP
429 so clients get a consistent shape (see apps.api.utils.custom_exception_handler).
"""

from django.conf import settings
from django.http import JsonResponse
from django_ratelimit import ALL
from django_ratelimit.core import is_ratelimited

API_PATH_PREFIX = "/api/"

# Arabic: "Too many requests. Please wait a moment and try again."
THROTTLED_MESSAGE = "محاولات كثيرة. يرجى الانتظار قليلاً ثم إعادة المحاولة."


class ApiRateLimitMiddleware:
    """Throttle /api/ requests with django-ratelimit.

    Placed after AuthenticationMiddleware so ``request.user`` is populated and
    the ``user_or_ip`` key throttles authenticated users individually, falling
    back to the client IP for anonymous traffic. Fails open: a cache error must
    never take down the API.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith(API_PATH_PREFIX) and self._is_limited(request):
            return JsonResponse(
                {
                    "success": False,
                    "message": THROTTLED_MESSAGE,
                    "data": None,
                    "errors": {"detail": THROTTLED_MESSAGE},
                },
                status=429,
            )
        return self.get_response(request)

    def _is_limited(self, request):
        if not getattr(settings, "RATELIMIT_ENABLE", True):
            return False
        try:
            return is_ratelimited(
                request,
                group="api",
                key="user_or_ip",
                rate=settings.API_RATELIMIT,
                method=ALL,
                increment=True,
            )
        except Exception:
            # Cache unavailable — never block the API on throttling failure.
            return False

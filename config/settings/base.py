import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

dotenv_path = BASE_DIR / ".env"
if dotenv_path.exists():
    import dotenv
    dotenv.load_dotenv(dotenv_path)

SECRET_KEY = os.environ["SECRET_KEY"]

DEBUG = False

ALLOWED_HOSTS = []

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_htmx",
    "widget_tweaks",
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    "django_filters",
    "django_ratelimit",
    "channels",
    "apps.core",
    "apps.accounts",
    "apps.references",
    "apps.circles",
    "apps.attendance.apps.AttendanceConfig",
    "apps.memorization",
    "apps.exams",
    "apps.notifications",
    "apps.requests",
    "apps.usersettings",
    "apps.classrooms",
    "apps.reports",
    "apps.certificates",
    "apps.announcements",
    "apps.api",
    "apps.webinars",
    "apps.chat",
    "apps.emailcenter",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "apps.core.middleware.SessionIdleTimeoutMiddleware",
    "apps.core.middleware.MaintenanceModeMiddleware",
    "apps.core.middleware.FeatureFlagMiddleware",
    "apps.core.middleware.SecurityHeadersMiddleware",
    "apps.core.middleware.UserProfileMiddleware",
    "apps.api.middleware.ApiRateLimitMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.pending_count",
                "apps.core.context_processors.unread_notifications",
                "apps.core.context_processors.feature_flags",
                "apps.core.context_processors.mobile_app",
                "apps.core.context_processors.unread_messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "ar"
TIME_ZONE = "Asia/Riyadh"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/dashboard/"

# ── Session & Cookie Security ──────────────────────────────────────
SESSION_COOKIE_AGE = 28800  # 8 hours — idle timeout (matches school-day length)
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_SAVE_EVERY_REQUEST = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_HSTS_ENABLED = not DEBUG
if not DEBUG:
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    if os.environ.get("SECURE_PROXY"):
        SECURE_SSL_REDIRECT = True
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    _csrf_origins = os.environ.get("CSRF_TRUSTED_ORIGINS", "")
    CSRF_TRUSTED_ORIGINS = [o.strip() for o in _csrf_origins.split(",") if o.strip()]

# ── File Upload Security ───────────────────────────────────────────
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024  # 5 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 1000

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_RENDERER_CLASSES": (
        "rest_framework.renderers.JSONRenderer",
    ),
    "DEFAULT_PAGINATION_CLASS": "apps.api.pagination.StandardResultsSetPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.api.utils.custom_exception_handler",
    "UNAUTHENTICATED_USER": None,
}

# Rate limiting (django-ratelimit) — replaces DRF's built-in throttling and the
# old hand-rolled auth decorator. Counting is backed by the default cache
# (Redis in production; see config/settings/production.py). Both the API
# middleware (apps.api.middleware.ApiRateLimitMiddleware) and the auth-endpoint
# decorator (apps.accounts.decorators.auth_rate_limit) honor RATELIMIT_ENABLE,
# so dev/tests turn it off in one place (config/settings/local.py).
RATELIMIT_ENABLE = True
# Per user (or IP for anonymous) budget for the whole /api/ surface. Tunable on
# Render via the API_RATELIMIT env var without a code deploy.
API_RATELIMIT = os.environ.get("API_RATELIMIT", "2000/h")
# django-ratelimit only "officially" supports memcached and warns (W001) for
# every other backend. Production uses Django's RedisCache, which does provide
# the atomic incr() the library needs, so the warning is a false positive for
# our setup — silence it to keep `manage.py check` clean. (E003, the shared-cache
# error, correctly passes for Redis and is left active as a real guard.)
SILENCED_SYSTEM_CHECKS = ["django_ratelimit.W001"]

from datetime import timedelta
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

SPECTACULAR_SETTINGS = {
    "TITLE": "الطبيب الحافظ API",
    "DESCRIPTION": "REST API for the Quran memorization platform",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

# Google OAuth (admins connect their Gmail as a sender for the email center).
GOOGLE_OAUTH_CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "")
GOOGLE_OAUTH_CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "")

# A hung SMTP socket must never freeze a request: Django's SMTP backend has
# NO default timeout, so an unreachable mail server blocked signup forever.
EMAIL_TIMEOUT = int(os.environ.get("EMAIL_TIMEOUT", "10"))

# Virtual classrooms / webinars (Section C/D) — override for self-hosted Jitsi
JITSI_DOMAIN = os.environ.get("JITSI_DOMAIN", "meet.jit.si")
# JWT auth for the self-hosted Jitsi (prosody token auth). When JITSI_APP_SECRET
# is set, Django mints per-user tokens so the Jitsi server enforces room access.
# Unset ⇒ no token ⇒ public-server fallback (dev).
JITSI_APP_ID = os.environ.get("JITSI_APP_ID", "hafez")
JITSI_APP_SECRET = os.environ.get("JITSI_APP_SECRET", "")
JITSI_JWT_TTL = int(os.environ.get("JITSI_JWT_TTL", "7200"))

# Student mobile app: URL to the downloadable Android APK (or Play Store page).
# The landing page shows an install button only when this is set.
MOBILE_APK_URL = os.environ.get("MOBILE_APK_URL", "")

ASGI_APPLICATION = "config.asgi.application"
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    },
}

"""Local / development settings (HAF-17).

Inherits everything from base and overrides only what differs for local http
development — mirroring production.py. Previously this file re-declared the
entire INSTALLED_APPS / MIDDLEWARE / TEMPLATES / REST_FRAMEWORK, which silently
drifted from base (dead-app removals and new middleware had to be done twice).
"""
import os

# base.py requires SECRET_KEY in the environment (correct for prod). Provide a
# dev fallback *before* importing base so local doesn't need one set. dotenv in
# base won't override an already-set var, so a real key in .env still wins if
# it was exported; the fallback only fills the gap.
os.environ.setdefault("SECRET_KEY", "django-insecure-dev-key-not-for-production")

from .base import *  # noqa: F401,F403,E402

DEBUG = True
ALLOWED_HOSTS = ["*"]

# base evaluated its production `if not DEBUG:` block at import time (base
# DEBUG=False), enabling Secure cookies + HSTS. Undo them so the app works over
# plain http locally.
SECURE_HSTS_ENABLED = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# Disable all rate limiting (django-ratelimit) in development and the test
# suite; production keeps base's RATELIMIT_ENABLE = True. Tests that exercise a
# limiter re-enable it via @override_settings(RATELIMIT_ENABLE=True).
RATELIMIT_ENABLE = False
# Dev/tests use the default LocMemCache, which works in-process but trips
# django-ratelimit's shared-cache error (E003). Add it to base's silenced list
# (which already covers W001) so `manage.py check`/`test` stay green locally.
SILENCED_SYSTEM_CHECKS = [*SILENCED_SYSTEM_CHECKS, "django_ratelimit.E003"]  # noqa: F405

# Email — SMTP (Gmail / any) or Brevo API (the same logic as production.py).
# Render's free tier blocks outbound SMTP, so on Render you must set BREVO_API_KEY.
# On a regular dev machine, the Gmail SMTP credentials in .env work fine.
EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend"
)
EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", 587))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_SSL = os.environ.get("EMAIL_USE_SSL", "False").lower() == "true"
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", str(not EMAIL_USE_SSL)).lower() == "true"
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "الطبيب الحافظ <noreply@tabibalhafiz.com>")

BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "")
if BREVO_API_KEY:
    EMAIL_BACKEND = "anymail.backends.brevo.EmailBackend"
    ANYMAIL = {"BREVO_API_KEY": BREVO_API_KEY}

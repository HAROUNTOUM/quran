"""Google OAuth + Gmail API sending, with no Google SDK — four plain HTTPS
endpoints via `requests` (already a dependency through Anymail):

  1. accounts.google.com/o/oauth2/v2/auth   — consent (gmail.send + openid email)
  2. oauth2.googleapis.com/token            — code→tokens / refresh
  3. openidconnect.googleapis.com userinfo  — the connected address
  4. gmail.googleapis.com …/messages/send   — send MIME as the connected user

Setup (Google Cloud console): create an OAuth *Web application* client, add
`<site>/dashboard/email/gmail/callback/` to the authorized redirect URIs, and
put the client id/secret in GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET.
"""
import base64
import logging
import secrets
from datetime import timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"
SEND_ENDPOINT = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
SCOPES = "https://www.googleapis.com/auth/gmail.send openid email"
HTTP_TIMEOUT = 15  # seconds — never hang a request on Google

STATE_SESSION_KEY = "gmail_oauth_state"


def oauth_enabled() -> bool:
    return bool(settings.GOOGLE_OAUTH_CLIENT_ID and settings.GOOGLE_OAUTH_CLIENT_SECRET)


def _raise_with_google_error(resp):
    """Google puts the actual reason (invalid_grant, redirect_uri_mismatch, …)
    in the response body — log it before raising, or debugging is blind."""
    if resp.status_code >= 400:
        logger.error("Google API error %s: %s", resp.status_code, resp.text[:500])
    resp.raise_for_status()


def build_authorize_url(request, redirect_uri: str) -> str:
    """Consent URL. `access_type=offline` + `prompt=consent` guarantee a
    refresh token even on re-connect. State guards the callback (CSRF)."""
    state = secrets.token_urlsafe(32)
    request.session[STATE_SESSION_KEY] = state
    return AUTH_ENDPOINT + "?" + urlencode({
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    })


def exchange_code(code: str, redirect_uri: str) -> dict:
    """Authorization code → {access_token, refresh_token, expires_in, ...}."""
    resp = requests.post(TOKEN_ENDPOINT, data={
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }, timeout=HTTP_TIMEOUT)
    _raise_with_google_error(resp)
    return resp.json()


def fetch_email(access_token: str) -> str:
    resp = requests.get(
        USERINFO_ENDPOINT,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=HTTP_TIMEOUT,
    )
    _raise_with_google_error(resp)
    return resp.json().get("email", "")


def ensure_access_token(account) -> str:
    """Return a valid access token for the account, refreshing if expired.
    Raises requests.HTTPError when Google refuses (e.g. access revoked)."""
    if (
        account.access_token
        and account.access_token_expires_at
        and account.access_token_expires_at > timezone.now() + timedelta(seconds=60)
    ):
        return account.access_token

    resp = requests.post(TOKEN_ENDPOINT, data={
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
        "refresh_token": account.get_refresh_token(),
        "grant_type": "refresh_token",
    }, timeout=HTTP_TIMEOUT)
    _raise_with_google_error(resp)
    data = resp.json()
    account.access_token = data["access_token"]
    account.access_token_expires_at = timezone.now() + timedelta(
        seconds=int(data.get("expires_in", 3600))
    )
    account.save(update_fields=["access_token", "access_token_expires_at"])
    return account.access_token


def send_gmail(account, subject: str, html_body: str, to_email: str) -> bool:
    """Send one HTML email *as the connected Gmail account*. Returns bool;
    failures are logged, never raised (mirrors send_html_email)."""
    try:
        token = ensure_access_token(account)

        from django.utils.html import strip_tags

        msg = MIMEMultipart("alternative")
        msg["To"] = to_email
        msg["From"] = account.email
        msg["Subject"] = subject
        # Same MIME shape as the platform backend: text/plain + text/html.
        msg.attach(MIMEText(strip_tags(html_body), "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

        resp = requests.post(
            SEND_ENDPOINT,
            headers={"Authorization": f"Bearer {token}"},
            json={"raw": raw},
            timeout=HTTP_TIMEOUT,
        )
        _raise_with_google_error(resp)
        return True
    except Exception:
        logger.exception("Gmail send failed for %s -> %s", account.email, to_email)
        return False

# Self-hosted Jitsi Meet (JWT auth)

Video conferencing for classrooms and webinars runs on our own Jitsi server —
no meet.jit.si, no JaaS, and users never see a Jitsi login. Access works like
this:

1. Django checks its own permissions (enrollment, role) and mints a short-lived
   JWT scoped to one room (`apps/classrooms/services.py`), with the user's
   Arabic display name and moderator flag baked in.
2. The page embeds the room through the IFrame API SDK
   (`templates/dashboard/classrooms/_jitsi_embed.html`) and passes that JWT.
3. Prosody (token auth) verifies the signature, issuer, audience, and room.
   Guests are disabled, so a Django-minted token is the only way into any room.

## Deploy

```bash
cd deploy/jitsi
cp .env.example .env
# edit .env: PUBLIC_URL, JITSI_APP_SECRET (openssl rand -hex 32),
# JICOFO_AUTH_PASSWORD / JVB_AUTH_PASSWORD (openssl rand -hex 16),
# JVB_ADVERTISE_IPS = the server's public IP
docker compose up -d
```

Firewall: open 80/tcp + 443/tcp (web) and 10000/udp (media).

Then set in the **Django** `.env` (values must match this directory's `.env`):

```
JITSI_DOMAIN=meet.tabibalhafiz.com
JITSI_APP_ID=hafez
JITSI_APP_SECRET=<same secret>
```

## Verify

- Open `https://<PUBLIC_URL>/testroom` directly in a browser — it must be
  rejected ("Authentication required"): anonymous access is off.
- Join a classroom from the platform — the meeting must load with your Arabic
  display name pre-filled, with no Jitsi login or account prompt.

## Notes

- The `jitsi-config/` directory created on first run holds generated configs;
  it is disposable but keep it between restarts. After changing `.env`, run
  `docker compose down && rm -rf jitsi-config && docker compose up -d` so the
  containers regenerate their configs.
- Token TTL is `JITSI_JWT_TTL` (Django side, default 7200s); it only gates
  joining, not staying in a call.

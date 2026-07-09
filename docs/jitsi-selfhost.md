# Self-Hosted Jitsi with JWT Auth

The platform can run its own Jitsi Meet instead of the public `meet.jit.si`. This is
required for privacy and, more importantly, for **access control**: on the public
server anyone who learns a room name can join. With the self-hosted stack, prosody
runs in **JWT token auth** mode and refuses any participant who does not present a
token signed by Django. Django only mints a token after its own permission checks
(`TeacherRoom.can_join`, webinar speaker membership), so the Jitsi room enforces the
same rules as the app.

## How it fits together

1. A user opens a classroom/webinar page.
2. The Django view runs the normal permission check.
3. If allowed, `apps/classrooms/services.py::mint_jitsi_jwt(user, room_name, moderator)`
   issues a short-lived HS256 token (`JITSI_APP_SECRET`), scoped to that exact room,
   with `context.user.moderator` = true for teachers/admins/supervisors.
4. The iframe loads `https://<JITSI_DOMAIN>/<room>?jwt=<token>#…`.
5. prosody validates the token (issuer, audience `jitsi`, room, expiry) and admits
   the user with the right role.

**Fallback:** if `JITSI_APP_SECRET` is empty (the dev default), no token is minted and
the embed points at the public server unchanged — local development needs no Jitsi
stack.

## Environment variables

Add to `.env` (used by both Django and the compose Jitsi services):

```
# Public HTTPS URL of your Jitsi web container (behind your reverse proxy)
JITSI_DOMAIN=meet.yourdomain.dz
JITSI_PUBLIC_URL=https://meet.yourdomain.dz

# Shared JWT secret — Django signs, prosody verifies. Keep secret, rotate carefully.
JITSI_APP_ID=hafez
JITSI_APP_SECRET=<openssl rand -hex 32>
JITSI_JWT_TTL=7200

# Internal Jitsi component secrets (compose only)
JICOFO_COMPONENT_SECRET=<openssl rand -hex 16>
JICOFO_AUTH_PASSWORD=<openssl rand -hex 16>
JVB_AUTH_PASSWORD=<openssl rand -hex 16>
```

## Bringing it up

```
docker compose up -d jitsi-prosody jitsi-jicofo jitsi-jvb jitsi-web
```

- The web container is published on `8443` (map it to `443` behind your reverse proxy
  / the existing nginx service, terminating TLS for `JITSI_DOMAIN`).
- The videobridge needs **UDP 10000** reachable from the public internet — open it on
  the host firewall and any cloud security group. This is the single most common
  cause of "participants can't see/hear each other".

## Server sizing

JVB is bandwidth-bound, not CPU-bound. Rough guide:

| Concurrent participants | vCPU | RAM  | Uplink        |
|-------------------------|------|------|---------------|
| ≤ 20 (one halaqa)       | 2    | 4 GB | 50 Mbps       |
| ≤ 75 (several halaqas)  | 4    | 8 GB | 150–200 Mbps  |
| Webinar speakers only   | 2    | 4 GB | small (≤10)   |

Webinars keep the Jitsi call to the small speaker group; the audience watches the
YouTube/stream embed, so JVB load stays low regardless of audience size.

## Rotating the secret

Changing `JITSI_APP_SECRET` invalidates all live tokens (users rejoin). Update `.env`,
`docker compose up -d jitsi-web jitsi-prosody`, and restart Django so it signs with the
new value.

## Verifying auth is on

Open a room URL **without** `?jwt=` — prosody should refuse admission. With a valid
token from the app, admission succeeds and teachers appear as moderators.

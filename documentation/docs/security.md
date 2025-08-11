# Security Model

## Token-based auth (optional)
- When enabled, the API expects `Authorization: Bearer <token>`.
- Generate: `POST /api/auth/generate` (persists to `backend/data/auth_token.txt`).
- Disable (temporary): `POST /api/auth/disable`.

**Scope**: Single admin token; treat it like a password. Rotating the token invalidates previous clients.

## Network placement
Run the service on a trusted LAN or behind a reverse proxy. Exposing it directly to the internet is not recommended without additional hardening (TLS, auth, IP filtering).

## Data at rest
- Config and backups are plain JSON on disk.
- Secrets (RTSP credentials, MQTT password) are stored as-is. Consider OS-level disk encryption and least-privilege file permissions.

## Future work
- Per-user tokens with roles (view/apply)
- Audit log (who changed what, when)
- Optional encrypted secrets store

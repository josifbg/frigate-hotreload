#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCS="$ROOT/documentation/docs"
MKDOCS_YML="$ROOT/documentation/mkdocs.yml"

mkdir -p "$DOCS"

# --- Write a file atomically
write() {
  local target="$1"; shift
  local tmp
  tmp="$(mktemp)"
  cat >"$tmp" <<'END'
__PLACEHOLDER__
END
  printf "%s" "$1" >"$tmp"
  mv "$tmp" "$target"
  echo "wrote $target"
}

# =========================
# Core pages
# =========================
cat > "$DOCS/index.md" <<'MD'
# Frigate Hot-Reload

A minimal, fast API + UI to edit and apply Frigate-like configuration **without restarts**.
Supports live validation, backups/rollback, camera cloning, reorder, bulk delete, import/export,
and optional Bearer-token auth.

- **Backend**: FastAPI + Uvicorn
- **UI**: Static HTML/JS (vanilla), talking to `/api/*` + `/ws`
- **Config store**: JSON at `backend/data/config.json` + rolling backups (default 5)

## Quick links
- [Quickstart](quickstart.md)
- [Configuration](configuration.md)
- [Cameras](cameras.md)
- [API](api.md)
- [UI guide](ui.md)
- [Troubleshooting](troubleshooting.md)
- [Roadmap](roadmap.md)
- [Changelog](changelog.md)

## Auth (optional)
If auth is enabled, include the token:
```bash
TOKEN="$(cat backend/data/auth_token.txt 2>/dev/null || true)"
curl -s ${TOKEN:+-H "Authorization: Bearer $TOKEN"} http://127.0.0.1:8080/api/ping | jq .
```

## Core flows at a glance
### Dry-run apply
```bash
TOKEN="$(cat backend/data/auth_token.txt 2>/dev/null || true)"
curl -s ${TOKEN:+-H "Authorization: Bearer $TOKEN"} \
  -H "Content-Type: application/json" \
  -X POST "http://127.0.0.1:8080/api/config/apply?dry=true" \
  --data-binary @backend/data/config.json | jq .
```

### Clone a camera (dry-run)
```bash
curl -s ${TOKEN:+-H "Authorization: Bearer $TOKEN"} -H "Content-Type: application/json" \
  -X POST http://127.0.0.1:8080/api/cameras/clone \
  -d '{"source_key":"cam1","target_key":"cam_new","apply":false}' | jq .
```

### Bulk delete (apply)
```bash
curl -s ${TOKEN:+-H "Authorization: Bearer $TOKEN"} -H "Content-Type: application/json" \
  -X POST http://127.0.0.1:8080/api/cameras/bulk_delete \
  -d '{"keys":["cam_tmp1","cam_tmp2"],"apply":true}' | jq .
```
MD

echo "wrote $DOCS/index.md"

cat > "$DOCS/quickstart.md" <<'MD'
# Quickstart

## 1) Run the backend
```bash
cd backend
source .venv/bin/activate 2>/dev/null || (python3 -m venv .venv && source .venv/bin/activate)
pip install -U pip "fastapi" "uvicorn[standard]" "pydantic>=2" "watchfiles"
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080
```
Serves API at `/api/*`, UI at `/ui/`.

## 2) Open the UI
http://127.0.0.1:8080/ui/

## 3) Optional auth
```bash
curl -s -X POST http://127.0.0.1:8080/api/auth/generate | jq .
# token is saved to backend/data/auth_token.txt
```

## 4) Sanity checks
```bash
curl -s http://127.0.0.1:8080/api/ping | jq .
TOKEN="$(cat backend/data/auth_token.txt 2>/dev/null || true)"
curl -s ${TOKEN:+-H "Authorization: Bearer $TOKEN"} http://127.0.0.1:8080/api/config | jq .
```

## 5) Edit & apply
- Use UI forms
- **Preview (dry)** → check diff
- **Apply** → instant hot reload
- **Undo** → restore latest backup
MD

echo "wrote $DOCS/quickstart.md"

cat > "$DOCS/api.md" <<'MD'
# API

Base: `http://127.0.0.1:8080`

- UI: `/ui/`
- WebSocket: `/ws`

Auth header when enabled:
```
Authorization: Bearer <token>
```

## Health
```
GET /api/ping → { "pong": true, "version": "x.y.z" }
```

## Auth
```
POST /api/auth/generate → { ok, token }
POST /api/auth/disable  → { ok, disabled: true }
GET  /api/auth/status   → { enabled, have_token }
```

## Config
```
GET  /api/config
POST /api/config/validate
POST /api/config/apply?dry=true
POST /api/config/apply
POST /api/config/import
GET  /api/config/export
POST /api/config/rollback
```

## Cameras
```
POST /api/cameras/clone
POST /api/cameras/delete
POST /api/cameras/reorder
POST /api/cameras/bulk_delete
POST /api/cameras/set
```
MD

echo "wrote $DOCS/api.md"

cat > "$DOCS/ui.md" <<'MD'
# UI Guide

Open http://127.0.0.1:8080/ui/

## Features
- Full config editing in browser
- Apply without restart; Dry-run preview
- Clone camera; Drag-and-drop reorder
- Bulk delete with checkboxes
- Undo (restore from latest backup)
- Optional token auth (banner warns if missing)

## Import/Export
- Export downloads current JSON
- Import replaces config; if safe apply fails, backend saves file and marks `"note":"fallback_apply"`
MD

echo "wrote $DOCS/ui.md"

cat > "$DOCS/configuration.md" <<'MD'
# Configuration

This project stores configuration as JSON at `backend/data/config.json`. The UI edits the same structure in-memory and applies changes without restart.

## Top-level keys
- `mqtt`: broker settings
- `cameras`: object whose keys are camera IDs (e.g., `cam1`, `front_door`)

### mqtt
```json
{
  "host": "mqtt",
  "port": 1883,
  "user": null,
  "password": null,
  "topic_prefix": "frigate"
}
```

### cameras[*]
Each camera entry supports the following fields:

```json
{
  "name": "Front Yard",
  "enabled": true,
  "ffmpeg": {
    "url": "rtsp://user:pass@host:554/Streaming/Channels/101",
    "hwaccel": null,
    "width": 1920,
    "height": 1080,
    "fps": 15
  },
  "onvif": {
    "host": "http://host:8000",
    "user": "user",
    "pass": "pass"
  },
  "zones": [],
  "detection": {
    "score_threshold": 0.6,
    "iou_threshold": 0.45
  },
  "retention": {
    "mode": "motion",
    "detection_days": 5,
    "recording_days": 2,
    "pre_capture_sec": 3,
    "post_capture_sec": 3
  }
}
```

> Note: All fields are optional unless your specific camera requires them. Unknown keys are preserved on round-trip.

## Backups
On each successful **Apply**, a copy of `config.json` is saved to `backend/data/backups/`. The default retention is 5 files. The **Undo** button restores the latest backup.

## Import/Export
- **Export**: `GET /api/config/export` → current JSON
- **Import**: `POST /api/config/import` with raw JSON. If a safe hot-apply is not possible, the backend will persist the file and return a `note: "fallback_apply"`.
MD

echo "wrote $DOCS/configuration.md"

cat > "$DOCS/cameras.md" <<'MD'
# Cameras

Cameras are defined under the `cameras` object where each key is a camera ID (`cam1`, `garage`, etc.).

## Common operations

### Clone
```bash
TOKEN="$(cat backend/data/auth_token.txt 2>/dev/null || true)"
curl -s ${TOKEN:+-H "Authorization: Bearer $TOKEN"} -H 'Content-Type: application/json' \
  -X POST http://127.0.0.1:8080/api/cameras/clone \
  -d '{"source_key":"cam1","target_key":"cam_new","overwrite":false,"apply":true}' | jq .
```

### Delete
```bash
curl -s ${TOKEN:+-H "Authorization: Bearer $TOKEN"} -H 'Content-Type: application/json' \
  -X POST http://127.0.0.1:8080/api/cameras/delete \
  -d '{"key":"cam_new","apply":true}' | jq .
```

### Reorder
```bash
ORDER=$(curl -s ${TOKEN:+-H "Authorization: Bearer $TOKEN"} http://127.0.0.1:8080/api/config | jq -c '{order:(.cameras|keys|reverse), apply:true}')
curl -s ${TOKEN:+-H "Authorization: Bearer $TOKEN"} -H 'Content-Type: application/json' \
  -X POST http://127.0.0.1:8080/api/cameras/reorder \
  -d "$ORDER" | jq .
```

### Bulk delete
```bash
curl -s ${TOKEN:+-H "Authorization: Bearer $TOKEN"} -H 'Content-Type: application/json' \
  -X POST http://127.0.0.1:8080/api/cameras/bulk_delete \
  -d '{"keys":["camA","camB"],"apply":true}' | jq .
```

## UI helpers
- **Clone from selected** button duplicates configuration to a new camera ID.
- **Drag to reorder** the list; click **Apply** to persist order.
- **Select all + Delete selected** removes multiple cameras at once.
MD

echo "wrote $DOCS/cameras.md"

cat > "$DOCS/troubleshooting.md" <<'MD'
# Troubleshooting

## 403 Forbidden (API)
- Auth is enabled but the request is missing/has a wrong token.
- Fix: include the header `Authorization: Bearer <token>` or disable auth via `POST /api/auth/disable` (temporary).

## Import returns 200 but with `"note":"fallback_apply"`
- The backend could not safely hot-apply. It saved the JSON to disk and returned success.
- Verify the config in UI, then **Apply** to confirm.

## WebSocket disconnects
- UI shows a brief disconnect on refresh; this is normal. Persistent 403 → check token.

## Diff shows no changes
- You may be doing a dry-run with identical content. Tweak a field and retry.

## Where are backups?
- `backend/data/backups/` (rolling, default max 5). Use **Undo** in the UI to restore the latest.
MD

echo "wrote $DOCS/troubleshooting.md"

cat > "$DOCS/roadmap.md" <<'MD'
# Roadmap

- ONVIF discovery helper (auto-fill RTSP URL and credentials)
- Camera health panel (ping, FPS, last frame timestamp)
- Audit log for changes (who, when, diff)
- Multi-user tokens with roles (view/apply)
- Presets/templates for common camera models
- Import from YAML (Frigate), export back to YAML
- Mobile app (iOS) companion for on-the-go edits
MD

echo "wrote $DOCS/roadmap.md"

# =========================
# NEW: FAQ / Security / Examples
# =========================
cat > "$DOCS/faq.md" <<'MD'
# FAQ

### Do I need to restart after config changes?
No. The backend applies changes live. If a safe hot-apply is not possible, the import will still save the JSON and return with a `note: "fallback_apply"`.

### Where is the config stored?
`backend/data/config.json`. Backups are in `backend/data/backups/`.

### How do I recover after a bad change?
Use **Undo** in the UI (restores latest backup). You can also import a known-good JSON via **Import**.

### Why do I get 403 Forbidden?
Auth is enabled and the request is missing or has a wrong token. Use:
```
Authorization: Bearer <token>
```
Generate a token via `POST /api/auth/generate`.

### Can I bulk delete cameras?
Yes: use the UI checkboxes with **Delete selected**, or the API `POST /api/cameras/bulk_delete`.

### How do I reorder cameras?
Drag-and-drop in the UI, then **Apply**. Or POST to `/api/cameras/reorder` with the desired `order` array.
MD

echo "wrote $DOCS/faq.md"

cat > "$DOCS/security.md" <<'MD'
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
MD

echo "wrote $DOCS/security.md"

cat > "$DOCS/examples.md" <<'MD'
# Examples

## Minimal single camera
```json
{
  "mqtt": {"host": "mqtt", "port": 1883, "topic_prefix": "frigate"},
  "cameras": {
    "front": {
      "name": "Front",
      "enabled": true,
      "ffmpeg": {"url": "rtsp://user:pass@host/stream", "width": 1920, "height": 1080, "fps": 15},
      "zones": []
    }
  }
}
```

## Two cameras with different FPS and retention
```json
{
  "mqtt": {"host": "mqtt", "port": 1883},
  "cameras": {
    "door": {
      "name": "Door",
      "enabled": true,
      "ffmpeg": {"url": "rtsp://user:pass@door/stream", "width": 2560, "height": 1440, "fps": 20},
      "retention": {"mode": "motion", "detection_days": 5, "recording_days": 2}
    },
    "yard": {
      "name": "Yard",
      "enabled": true,
      "ffmpeg": {"url": "rtsp://user:pass@yard/stream", "width": 1920, "height": 1080, "fps": 10},
      "detection": {"score_threshold": 0.55}
    }
  }
}
```

## Bulk clone via API (shell)
```bash
TOKEN="$(cat backend/data/auth_token.txt 2>/dev/null || true)"
for n in 2 3 4; do
  curl -s ${TOKEN:+-H "Authorization: Bearer $TOKEN"} -H 'Content-Type: application/json' \
    -X POST http://127.0.0.1:8080/api/cameras/clone \
    -d "{\"source_key\":\"front\",\"target_key\":\"front_$n\",\"overwrite\":false,\"apply\":true}" | jq -r '.ok'
done
```
MD

echo "wrote $DOCS/examples.md"

# =========================
# mkdocs.yml — ensure nav contains the new pages
# =========================
cat > "$MKDOCS_YML" <<'YML'
site_name: Frigate Hot-Reload
site_url: http://127.0.0.1:8000/
repo_url: https://github.com/josifbg/frigate-hotreload

theme:
  name: material
  language: en
  features:
    - navigation.instant
    - navigation.tracking
    - content.code.copy
    - search.highlight
    - search.suggest

markdown_extensions:
  - admonition
  - codehilite
  - toc:
      permalink: true

nav:
  - Home: index.md
  - Quickstart: quickstart.md
  - API: api.md
  - UI Guide: ui.md
  - Configuration: configuration.md
  - Cameras: cameras.md
  - Examples: examples.md
  - Security: security.md
  - FAQ: faq.md
  - Troubleshooting: troubleshooting.md
  - Roadmap: roadmap.md
  - Changelog: ../CHANGELOG.md
YML

echo "wrote $MKDOCS_YML"

# --- Commit & push ---
if git -C "$ROOT" rev-parse --git-dir >/dev/null 2>&1; then
  git -C "$ROOT" add documentation/docs/*.md documentation/mkdocs.yml || true
  if ! git -C "$ROOT" diff --cached --quiet; then
    git -C "$ROOT" commit -m "docs: add FAQ/Security/Examples and update mkdocs nav"
    git -C "$ROOT" push
  else
    echo "No changes to commit."
  fi
else
  echo "(!) Not a git repo here — skipping commit/push."
fi

echo "✅ Documentation pages updated."
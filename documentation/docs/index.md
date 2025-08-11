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

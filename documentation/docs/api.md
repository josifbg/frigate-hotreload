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

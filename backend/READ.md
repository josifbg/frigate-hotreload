# Backend (FastAPI) — Frigate Hotreload

## Стартиране
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt  # или: pip install fastapi "uvicorn[standard]" pydantic
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080
```

## Основни ендпойнти
- `GET /api/ping` — health/version (пример: `{ "pong": true, "version": "0.2.3" }`)
- `GET /api/config` — текущ JSON
- `POST /api/config/apply` (`?dry=true`) — apply/preview
- `POST /api/config/import` — импорт на конфигурация
- `GET /api/config/export` — експорт
- `POST /api/config/rollback` — rollback
- `GET /api/config/backups` — налични бекъпи

### Камери
- `POST /api/cameras/clone` — `{ source_key, target_key, overwrite, apply }`
- `POST /api/cameras/delete` — `{ key, apply }`
- `POST /api/cameras/bulk_delete` — `{ keys:[], apply }`
- `POST /api/cameras/reorder` — `{ order:[], apply }`
- `POST /api/cameras/set` — `{ key, value, apply }`

## Auth (Bearer token)
- `POST /api/auth/generate` — връща токен и го записва в `data/auth_token.txt`
- `GET /api/auth/status` — `{ enabled, have_token }`
- `POST /api/auth/disable` — изключва проверката

### Middleware защита
Всички API са защитени, с изключение на:
- `/ui`, `/docs`, `/redoc`, `/openapi.json`
- `/api/ping`
- `/api/auth/*`
- корен `/` (redirect към `/ui/`)

## Данни
- Конфигурацията се пази в `backend/data/config.json`
- Бекъпи в `backend/data/backups/` (max 5)
- Токен в `backend/data/auth_token.txt`

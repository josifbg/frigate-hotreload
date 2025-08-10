from __future__ import annotations
import os, base64, secrets
from typing import Dict, Any, Optional

from fastapi import FastAPI, WebSocket
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.websockets import WebSocketDisconnect

from .config_schema import RootConfig, CameraConfig, FFmpegInput, Zone
from .config_manager import ConfigManager
from .workers.camera_worker import CameraWorker
from .events import WSBus
from .storage import (
    load_config,
    save_config,
    list_backups,
    load_backup,
    create_backup,
)

# --- Basic Auth настройки (можеш да смениш с променливи на средата) ---
ADMIN_USER = os.getenv("FRIGATE_UI_USER", "admin")
ADMIN_PASS = os.getenv("FRIGATE_UI_PASS", "admin")

def _parse_basic(header: str) -> Optional[tuple[str, str]]:
    try:
        if not header or not header.lower().startswith("basic "):
            return None
        raw = header.split(" ", 1)[1].strip()
        decoded = base64.b64decode(raw).decode("utf-8")
        if ":" not in decoded:
            return None
        u, p = decoded.split(":", 1)
        return u, p
    except Exception:
        return None

def _check_basic(header: str) -> bool:
    pair = _parse_basic(header)
    if not pair:
        return False
    u, p = pair
    return secrets.compare_digest(u, ADMIN_USER) and secrets.compare_digest(p, ADMIN_PASS)

def _need_auth(path: str) -> bool:
    # Пази /ui, /api, /ws, /docs, /openapi зад Basic; остави /test отворено.
    protected_prefixes = ("/ui", "/api", "/ws", "/docs", "/openapi.json", "/redoc")
    return path == "/" or path.startswith(protected_prefixes)

app = FastAPI(title="Frigate Hot-Reload API")

# ---- HTTP Basic middleware за всички HTTP заявки ----
@app.middleware("http")
async def basic_auth_mw(request, call_next):
    path = request.url.path
    if _need_auth(path) and path != "/test":
        auth = request.headers.get("authorization", "")
        if not _check_basic(auth):
            return Response(
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="frigate-ui"'},
                content=b"Unauthorized",
                media_type="text/plain",
            )
    return await call_next(request)

# ---- Health ----
@app.get("/test")
def test():
    return {"status": "OK"}

# ---- Зареждане на конфигурация (от файл, ако съществува) ----
loaded = load_config()
if loaded:
    initial = RootConfig.model_validate(loaded)
else:
    initial = RootConfig(
        cameras={
            "cam1": CameraConfig(
                name="Front Yard",
                ffmpeg=FFmpegInput(url="rtsp://example/stream1", width=1920, height=1080, fps=15),
                zones=[Zone(name="door", points=[[0, 0], [100, 0], [100, 100], [0, 100]])],
            )
        }
    )

cfg = ConfigManager(initial)
workers: Dict[str, CameraWorker] = {n: CameraWorker(c) for n, c in cfg.running.cameras.items()}
for w in workers.values():
    w.start()

bus = WSBus()

# ---- API: четене/валидация/прилагане ----
@app.get("/api/config")
def get_config():
    return cfg.running.model_dump()

@app.post("/api/config/validate")
def validate_config(data: Dict[str, Any]):
    ok, msg = cfg.validate(data)
    return JSONResponse({"ok": ok, "message": msg}, status_code=(200 if ok else 400))

@app.post("/api/config/apply")
async def apply_config(data: Dict[str, Any], dry: bool = False):
    # Валидиране
    ok, msg = cfg.validate(data)
    if not ok:
        return JSONResponse({"ok": False, "message": msg}, status_code=400)

    # Подготовка на нов конфиг и diff
    new = RootConfig.model_validate(data)
    diff = cfg.diff(new)

    # Preview само праща diff
    if dry:
        await bus.broadcast({"event": "preview", "diff": diff})
        return {"ok": True, "dry": True, "diff": diff}

    # --- Бекъп на текущия ПРЕДИ прилагане ---
    prev_snapshot = cfg.running.model_dump()
    snap_name = create_backup(prev_snapshot)

    # Apply: оповестяване, прилагане, запис, финално оповестяване
    await bus.broadcast({"event": "apply_start", "diff": diff, "backup": snap_name})
    changes = cfg.apply(new, workers)
    save_config(cfg.running.model_dump())  # запис на новия активен (без нов бекъп)
    await bus.broadcast({"event": "apply_done", "applied": changes})
    return {"ok": True, "dry": False, "applied": changes, "backup": snap_name}

# ---- Backups / Rollback ----
@app.get("/api/config/backups")
def get_backups():
    """Списък с налични бекъпи (по име на файл)."""
    return {"backups": list_backups()}

@app.post("/api/config/rollback")
async def rollback(name: str | None = None):
    """
    Връща конфигурацията към посочен бекъп или към най-новия.
    Понеже бекапите се правят ПРЕДИ apply, 'latest' е предишното състояние.
    """
    backups = list_backups()
    if not backups:
        return JSONResponse({"ok": False, "message": "no backups available"}, status_code=404)

    target_name = name if name else backups[-1]  # последният е най-новият бекъп (предишно състояние)
    data = load_backup(target_name)
    if data is None:
        return JSONResponse({"ok": False, "message": f"backup '{target_name}' not found or unreadable"}, status_code=404)

    # Валидиране и прилагане на бекъпа
    try:
        new = RootConfig.model_validate(data)
    except Exception as e:
        return JSONResponse({"ok": False, "message": f"invalid backup data: {e}"}, status_code=400)

    diff = cfg.diff(new)
    await bus.broadcast({"event": "rollback_start", "target": target_name, "diff": diff})

    # (по избор) бекъпни текущото преди да върнеш назад:
    create_backup(cfg.running.model_dump())

    changes = cfg.apply(new, workers)
    save_config(cfg.running.model_dump())  # запис на върнатото състояние (без нов бекъп)
    await bus.broadcast({"event": "rollback_done", "target": target_name, "applied": changes})
    return {"ok": True, "target": target_name, "applied": changes}

# ---- Reset to disk ----
@app.post("/api/config/reset")
async def reset_to_disk():
    """
    Взема конфигурацията директно от data/config.json и я прави 'running'.
    Бекапваме текущото състояние ПРЕДИ reset, за да може да се върнеш с Rollback latest.
    """
    data = load_config()
    if not data:
        return JSONResponse({"ok": False, "message": "no config.json on disk"}, status_code=404)

    # Валидиране
    try:
        new = RootConfig.model_validate(data)
    except Exception as e:
        return JSONResponse({"ok": False, "message": f"invalid on-disk config: {e}"}, status_code=400)

    # Бекъп на текущото преди reset
    snap_name = create_backup(cfg.running.model_dump())

    diff = cfg.diff(new)
    await bus.broadcast({"event": "reset_start", "backup": snap_name, "diff": diff})
    changes = cfg.apply(new, workers)
    save_config(cfg.running.model_dump())  # синхронизира активния към диска
    await bus.broadcast({"event": "reset_done", "applied": changes})
    return {"ok": True, "applied": changes, "backup": snap_name}

# ---- Export / Import ----
@app.get("/api/config/export")
def export_config():
    """Сваля текущия 'running' конфиг като файл."""
    payload = cfg.running.model_dump()
    content = JSONResponse(content=payload).body
    headers = {"Content-Disposition": 'attachment; filename="config.json"'}
    return Response(content=content, media_type="application/json", headers=headers)

@app.post("/api/config/import")
async def import_config(data: Dict[str, Any]):
    """
    Импорт на конфигурация от JSON тяло.
    Бекапваме текущото преди импорт, прилагаме, записваме на диск.
    """
    # Валидиране
    try:
        new = RootConfig.model_validate(data)
    except Exception as e:
        return JSONResponse({"ok": False, "message": f"invalid import data: {e}"}, status_code=400)

    # Бекъп преди импорт
    snap_name = create_backup(cfg.running.model_dump())

    diff = cfg.diff(new)
    await bus.broadcast({"event": "import_start", "backup": snap_name, "diff": diff})
    changes = cfg.apply(new, workers)
    save_config(cfg.running.model_dump())
    await bus.broadcast({"event": "import_done", "applied": changes})
    return {"ok": True, "applied": changes, "backup": snap_name}

# ---- WebSocket с Basic Auth проверка ----
@app.websocket("/ws")
async def ws(ws: WebSocket):
    # проверка на Basic от headers (или токен в query ?auth=)
    auth = ws.headers.get("authorization") or ""
    if not _check_basic(auth):
        # fallback: ?auth=base64(user:pass)
        token = ws.query_params.get("auth")
        if not token:
            await ws.close(code=1008, reason="Unauthorized")
            return
        try:
            pair = base64.b64decode(token).decode("utf-8")
            if ":" not in pair:
                await ws.close(code=1008, reason="Unauthorized")
                return
            u, p = pair.split(":", 1)
            if not (secrets.compare_digest(u, ADMIN_USER) and secrets.compare_digest(p, ADMIN_PASS)):
                await ws.close(code=1008, reason="Unauthorized")
                return
        except Exception:
            await ws.close(code=1008, reason="Unauthorized")
            return

    await bus.register(ws)
    try:
        while True:
            await ws.receive_text()  # keep-alive
    except WebSocketDisconnect:
        pass
    finally:
        await bus.unregister(ws)

# ---- UI на /ui (НЕ на /) ----
app.mount("/ui", StaticFiles(directory="app/static", html=True), name="static")

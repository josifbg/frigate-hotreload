from __future__ import annotations
import asyncio
import json
import traceback
import logging
from pathlib import Path
from typing import Optional, List, Any, Dict
from types import SimpleNamespace

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query, Request
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import secrets
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.requests import Request
import secrets

from .config_manager import ConfigManager

# Опитай да импортнеш Pydantic модела, ако съществува
try:
    from .config_schema import Config as ConfigModel  # type: ignore
except Exception:
    ConfigModel = None  # type: ignore

# -----------------------------------------------------------------------------
# Помощници
# -----------------------------------------------------------------------------
def _to_attr(obj: Any) -> Any:
    """Рекурсивно превръща dict/list в обекти с атрибути за достъп (dot-access)."""
    if isinstance(obj, dict):
        return SimpleNamespace(**{k: _to_attr(v) for k, v in obj.items()})
    if isinstance(obj, list):
        return [_to_attr(x) for x in obj]
    return obj

def _as_model_or_attr(raw_cfg: dict) -> Any:
    """Предпочитай Pydantic модел; иначе dot-access обект."""
    if ConfigModel is not None:
        try:
            return ConfigModel(**raw_cfg)  # типово-сигурно, има .mqtt и т.н.
        except Exception:
            pass
    return _to_attr(raw_cfg)

# -----------------------------------------------------------------------------
# Init
# -----------------------------------------------------------------------------
app = FastAPI(title="Frigate Hot-Reload Prototype", version="0.2.3")

# -----------------------------------------------------------------------------
# Global JSON error handlers (force JSON for unhandled exceptions and HTTPException)
# -----------------------------------------------------------------------------
from starlette.requests import Request
from fastapi.exceptions import RequestValidationError
from starlette.responses import PlainTextResponse

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    # Ensure JSON body for all HTTP errors
    payload = {"ok": False, "error": {"error": exc.detail if isinstance(exc.detail, str) else exc.detail, "type": "HTTPException"}}
    return JSONResponse(payload, status_code=exc.status_code)

@app.exception_handler(RequestValidationError)
async def request_validation_handler(request: Request, exc: RequestValidationError):
    payload = {"ok": False, "error": {"error": "validation error", "type": "RequestValidationError", "detail": exc.errors()}}
    return JSONResponse(payload, status_code=422)

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # Last-resort catcher to avoid text/plain bodies
    err = {"error": str(exc), "type": exc.__class__.__name__, "trace": traceback.format_exc()}
    logger.error("Unhandled exception: %s", err["error"])  
    return JSONResponse({"ok": False, "applied": False, "error": err}, status_code=500)
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# -----------------------------------------------------------------------------
# Auth token helpers
# -----------------------------------------------------------------------------
TOKEN_FILE = DATA_DIR / "auth_token.txt"

def _load_token() -> str | None:
    try:
        if TOKEN_FILE.exists():
            t = TOKEN_FILE.read_text().strip()
            return t or None
    except Exception:
        pass
    return None

def _save_token(token: str) -> None:
    TOKEN_FILE.write_text(token)

manager = ConfigManager(DATA_DIR)  # твоята имплементация

# -----------------------------------------------------------------------------
# Compatibility adapters
# -----------------------------------------------------------------------------
def _fallback_default_config() -> Dict[str, Any]:
    return {
        "mqtt": {"host": "mqtt", "port": 1883, "user": None, "password": None, "topic_prefix": "frigate"},
        "cameras": {
            "cam1": {
                "name": "Front Yard",
                "enabled": True,
                "ffmpeg": {"url": "rtsp://example/stream1", "hwaccel": None, "width": 1920, "height": 1080, "fps": 15},
                "zones": [{"name": "door", "points": [[0, 0], [100, 0], [100, 100], [0, 100]]}],
                "detection": {"score_threshold": 0.6, "iou_threshold": 0.45},
                "retention": {"mode": "motion", "detection_days": 5, "recording_days": 2, "pre_capture_sec": 3, "post_capture_sec": 3},
            }
        },
    }

def _read_config_from_disk() -> Dict[str, Any]:
    path = DATA_DIR / "config.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return _fallback_default_config()

if not hasattr(manager, "get_running_config"):
    def _mgr_get_running() -> Dict[str, Any]:
        candidates = ["get_current", "current", "get_running", "load_running", "read_running", "read", "load", "get"]
        for name in candidates:
            fn = getattr(manager, name, None)
            if callable(fn):
                try:
                    res = fn()
                    if isinstance(res, dict):
                        return res
                except TypeError:
                    try:
                        res = fn(DATA_DIR)
                        if isinstance(res, dict):
                            return res
                    except Exception:
                        pass
                except Exception:
                    pass
        return _read_config_from_disk()
    manager.get_running_config = _mgr_get_running  # type: ignore

# apply_config адаптер – винаги подава ПРАВИЛНИЯ payload (модел или attr-обект)
import inspect
if not hasattr(manager, "apply_config"):
    if hasattr(manager, "apply") and callable(getattr(manager, "apply")):
        sig = inspect.signature(manager.apply)
        if "workers" in sig.parameters:
            def _apply_cfg(cfg: dict):
                payload = _as_model_or_attr(cfg)
                return manager.apply(payload, workers={})
        else:
            def _apply_cfg(cfg: dict):
                payload = _as_model_or_attr(cfg)
                return manager.apply(payload)
        manager.apply_config = _apply_cfg  # type: ignore
    elif hasattr(manager, "set_config") and callable(getattr(manager, "set_config")):
        def _apply_cfg(cfg: dict):
            payload = _as_model_or_attr(cfg)
            return manager.set_config(payload)  # type: ignore
        manager.apply_config = _apply_cfg  # type: ignore
    else:
        def _apply_fallback(cfg: dict) -> dict:
            path = DATA_DIR / "config.json"
            path.write_text(json.dumps(cfg, indent=2))
            return {"saved_to": str(path)}
        manager.apply_config = _apply_fallback  # type: ignore

if not hasattr(manager, "diff_configs"):
    def _diff_fallback(a: dict, b: dict) -> dict:
        return {"before": a, "after": b}
    manager.diff_configs = _diff_fallback  # type: ignore

# -----------------------------------------------------------------------------
# WS Bus
# -----------------------------------------------------------------------------
class WSBus:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    async def broadcast(self, message: dict | str) -> None:
        payload = json.dumps(message) if not isinstance(message, str) else message
        dead: List[WebSocket] = []
        for ws in list(self._clients):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

bus = WSBus()

# -----------------------------------------------------------------------------
# HTTP Middleware for Bearer token auth on mutating routes
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# Auth endpoints
# -----------------------------------------------------------------------------
@app.get("/api/auth/status")
def auth_status() -> dict:
    t = _load_token()
    return {"enabled": bool(t), "have_token": bool(t)}

@app.post("/api/auth/generate")
def auth_generate() -> dict:
    # Generate and persist a new token (idempotent: always generates fresh one)
    token = secrets.token_urlsafe(32)
    _save_token(token)
    return {"ok": True, "token": token}

@app.post("/api/auth/disable")
def auth_disable() -> dict:
    try:
        if TOKEN_FILE.exists():
            TOKEN_FILE.unlink()
        return {"ok": True, "disabled": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -----------------------------------------------------------------------------
# Centralized apply with rich error reporting
# -----------------------------------------------------------------------------
logger = logging.getLogger("hotreload")
logging.basicConfig(level=logging.INFO)

def _candidate_payloads(raw_cfg: dict) -> list[Any]:
    """Върни варианти: dict, Pydantic модел (ако има), attr-обект."""
    variants: list[Any] = [raw_cfg]
    model = None
    if ConfigModel is not None:
        try:
            model = ConfigModel(**raw_cfg)
            variants.append(model)
        except Exception:
            pass
    variants.append(_to_attr(raw_cfg))
    return variants

def _apply_config_safe(new_cfg: dict):
    """Пробвай различни сигнатури и payload типове (dict / модел / attr-обект)."""
    tried: list[str] = []
    payloads = _candidate_payloads(new_cfg)

    for fn_name in ("apply_config", "apply"):
        fn = getattr(manager, fn_name, None)
        if not callable(fn):
            continue
        for payload in payloads:
            try:
                return fn(payload)
            except Exception as e:
                tried.append(f"{fn_name}({type(payload).__name__}) -> {e}")
            try:
                return fn(payload, workers={})
            except Exception as e2:
                tried.append(f"{fn_name}({type(payload).__name__}, workers={{}}) -> {e2}")

    # Last resort
    path = DATA_DIR / "config.json"
    path.write_text(json.dumps(new_cfg, indent=2))
    return {"saved_to": str(path), "note": "fallback_apply", "tried": tried}

async def _ws_event(event: str, **payload):
    try:
        await bus.broadcast({"event": event, **payload})
    except Exception:
        logger.debug("WS broadcast failed", exc_info=True)

def _apply_with_errors(new_cfg: dict, ws_event: str | None = None, ws_payload: dict | None = None):
    try:
        result = _apply_config_safe(new_cfg)
        if ws_event:
            try:
                loop = asyncio.get_event_loop()
                loop.create_task(_ws_event(ws_event, **(ws_payload or {})))
            except RuntimeError:
                pass
        return JSONResponse({"ok": True, "applied": True, "result": result})
    except Exception as e:
        err = {"error": str(e), "type": e.__class__.__name__, "trace": traceback.format_exc()}
        logger.error("apply failed: %s", err["error"])
        return JSONResponse({"ok": False, "applied": False, "error": err}, status_code=500)

# -----------------------------------------------------------------------------
# Models (request bodies)
# -----------------------------------------------------------------------------
class CameraCloneReq(BaseModel):
    source_key: str
    target_key: str
    overwrite: bool = False
    apply: bool = True


class CameraDeleteReq(BaseModel):
    key: str
    apply: bool = True

class CameraBulkDeleteReq(BaseModel):
    keys: List[str]
    apply: bool = True

class CameraReorderReq(BaseModel):
    order: List[str]
    apply: bool = True

class CameraSetReq(BaseModel):
    key: str
    value: Dict[str, Any]
    apply: bool = True

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _deepcopy(obj: Any) -> Any:
    return json.loads(json.dumps(obj))

def _ensure_cameras(cfg: dict) -> dict:
    cfg.setdefault("cameras", {})
    return cfg

def _ok(**kw) -> JSONResponse:
    return JSONResponse({"ok": True, **kw})

# -----------------------------------------------------------------------------
# Routes: basic + static
# -----------------------------------------------------------------------------
@app.get("/test")
def test() -> dict:
    return {"status": "OK"}

# Root handler: redirect to UI
@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url="/ui/")

# Ping route for quick version checks
@app.get("/api/ping")
def ping() -> dict:
    return {"pong": True, "version": app.version}

app.mount("/ui", StaticFiles(directory=BASE_DIR / "static", html=True), name="ui")

# -----------------------------------------------------------------------------
# Validation helpers
# -----------------------------------------------------------------------------
from typing import Tuple

def _is_bool(x: Any) -> bool:
    return isinstance(x, bool)

def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def validate_config_full(cfg: dict) -> List[Dict[str, Any]]:
    """Return a list of validation error objects. Empty list means OK.
    This keeps it lightweight but catches common mistakes.
    """
    errors: List[Dict[str, Any]] = []
    if not isinstance(cfg, dict):
        return [{"path": [], "msg": "config must be an object"}]

    # mqtt
    mqtt = cfg.get("mqtt")
    if not isinstance(mqtt, dict):
        errors.append({"path": ["mqtt"], "msg": "mqtt must be an object"})
    else:
        host = mqtt.get("host")
        port = mqtt.get("port")
        if not isinstance(host, str) or not host:
            errors.append({"path": ["mqtt", "host"], "msg": "host must be non-empty string"})
        if not _is_int(port) or not (0 < port < 65536):
            errors.append({"path": ["mqtt", "port"], "msg": "port must be integer in (0,65536)"})

    # cameras
    cams = cfg.get("cameras")
    if cams is None:
        errors.append({"path": ["cameras"], "msg": "cameras is required"})
        return errors
    if not isinstance(cams, dict):
        errors.append({"path": ["cameras"], "msg": "cameras must be an object of key -> camera"})
        return errors

    for key, cam in cams.items():
        if not isinstance(key, str) or not key:
            errors.append({"path": ["cameras"], "msg": "camera key must be string"})
            continue
        if not isinstance(cam, dict):
            errors.append({"path": ["cameras", key], "msg": "camera value must be an object"})
            continue
        # enabled (optional)
        en = cam.get("enabled", True)
        if not isinstance(en, bool):
            errors.append({"path": ["cameras", key, "enabled"], "msg": "enabled must be boolean"})
        # ffmpeg
        ff = cam.get("ffmpeg", {})
        if not isinstance(ff, dict):
            errors.append({"path": ["cameras", key, "ffmpeg"], "msg": "ffmpeg must be an object"})
        else:
            url = ff.get("url")
            if not isinstance(url, str) or not url:
                errors.append({"path": ["cameras", key, "ffmpeg", "url"], "msg": "url must be non-empty string"})
            w = ff.get("width")
            h = ff.get("height")
            fps = ff.get("fps")
            if w is not None and not _is_int(w):
                errors.append({"path": ["cameras", key, "ffmpeg", "width"], "msg": "width must be integer"})
            if h is not None and not _is_int(h):
                errors.append({"path": ["cameras", key, "ffmpeg", "height"], "msg": "height must be integer"})
            if fps is not None and (not _is_int(fps) or not (1 <= fps <= 240)):
                errors.append({"path": ["cameras", key, "ffmpeg", "fps"], "msg": "fps must be integer in [1,240]"})

    return errors

# -----------------------------------------------------------------------------
# Routes: config
# -----------------------------------------------------------------------------
@app.get("/api/config")
def get_config() -> dict:
    return manager.get_running_config()

@app.post("/api/config/validate")
def validate_config(cfg: dict) -> dict:
    try:
        json.dumps(cfg)  # structural JSON check
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    errs = validate_config_full(cfg)
    if errs:
        raise HTTPException(status_code=400, detail={"errors": errs})
    return {"ok": True}

@app.post("/api/config/apply")
def apply_config(cfg: dict, dry: bool = Query(False, description="Preview only")) -> JSONResponse:
    current = manager.get_running_config()
    new_cfg = _deepcopy(cfg)
    if dry:
        diff = manager.diff_configs(current, new_cfg)
        return _ok(dry=True, diff=diff)
    return _apply_with_errors(
        new_cfg,
        ws_event="applied",
        ws_payload={"ts": (asyncio.get_event_loop().time() if asyncio.get_event_loop().is_running() else None)},
    )

@app.get("/api/config/backups")
def list_backups() -> dict:
    if hasattr(manager, "list_backups"):
        files = manager.list_backups()  # type: ignore
    else:
        bdir = DATA_DIR / "backups"
        files = sorted([p.name for p in bdir.glob("*.json")]) if bdir.exists() else []
    return {"backups": files}

@app.post("/api/config/rollback")
def rollback(name: Optional[str] = Query(None)) -> JSONResponse:
    if hasattr(manager, "rollback"):
        ok = manager.rollback(name)  # type: ignore
    else:
        raise HTTPException(status_code=501, detail="rollback not implemented in manager")
    if ok:
        return _ok(rolled_back=True, name=name or "latest")
    raise HTTPException(status_code=400, detail="rollback failed")

@app.post("/api/config/reset")
def reset_to_disk() -> JSONResponse:
    if hasattr(manager, "reset_to_disk"):
        ok = manager.reset_to_disk()  # type: ignore
    else:
        raise HTTPException(status_code=501, detail="reset not implemented in manager")
    if ok:
        return _ok(reset=True)
    raise HTTPException(status_code=400, detail="reset failed")

@app.get("/api/config/export")
def export_cfg() -> FileResponse:
    path = DATA_DIR / "config.json"
    if not path.exists():
        current = manager.get_running_config()
        path.write_text(json.dumps(current, indent=2))
    return FileResponse(path, media_type="application/json", filename="config.json")

@app.post("/api/config/import")
def import_cfg(cfg: dict) -> JSONResponse:
    """Import and apply a full config payload with robust error reporting."""
    try:
        # 1) structural JSON check
        try:
            json.dumps(cfg)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

        # 2) domain validation
        errs = validate_config_full(cfg)
        if errs:
            raise HTTPException(status_code=400, detail={"errors": errs})

        # 3) deepcopy and apply via centralized path
        new_cfg = _deepcopy(cfg)
        return _apply_with_errors(new_cfg, ws_event="imported")

    except HTTPException:
        # Let FastAPI handle 4xx as-is
        raise
    except Exception as e:
        # Force JSON body for 5xx and log details
        err = {"error": str(e), "type": e.__class__.__name__, "trace": traceback.format_exc()}
        logger.error("/api/config/import failed: %s", err["error"]) 
        return JSONResponse({"ok": False, "applied": False, "error": err}, status_code=500)

# -----------------------------------------------------------------------------
# NEW: Camera management API
# -----------------------------------------------------------------------------
@app.post("/api/cameras/clone")
def api_cam_clone(req: CameraCloneReq) -> JSONResponse:
    cfg = manager.get_running_config()
    cams = _ensure_cameras(cfg)["cameras"]

    if req.source_key not in cams:
        raise HTTPException(status_code=404, detail=f"source_key '{req.source_key}' not found")
    if (req.target_key in cams) and not req.overwrite:
        raise HTTPException(status_code=409, detail=f"target_key '{req.target_key}' exists (use overwrite=true)")

    new_cfg = _deepcopy(cfg)
    new_cams = _ensure_cameras(new_cfg)["cameras"]
    new_cams[req.target_key] = _deepcopy(new_cams[req.source_key])
    if not new_cams[req.target_key].get("name"):
        new_cams[req.target_key]["name"] = req.target_key

    if not req.apply:
        diff = manager.diff_configs(cfg, new_cfg)
        return _ok(dry=True, diff=diff)

    return _apply_with_errors(
        new_cfg,
        ws_event="cam_cloned",
        ws_payload={"from": req.source_key, "to": req.target_key},
    )

@app.post("/api/cameras/delete")
def api_cam_delete(req: CameraDeleteReq) -> JSONResponse:
    cfg = manager.get_running_config()
    cams = cfg.get("cameras", {})
    if req.key not in cams:
        raise HTTPException(status_code=404, detail=f"key '{req.key}' not found")

    new_cfg = _deepcopy(cfg)
    new_cfg.get("cameras", {}).pop(req.key, None)

    if not req.apply:
        diff = manager.diff_configs(cfg, new_cfg)
        return _ok(dry=True, diff=diff)

    return _apply_with_errors(
        new_cfg,
        ws_event="cam_deleted",
        ws_payload={"key": req.key},
    )


@app.post("/api/cameras/bulk_delete")
def api_cam_bulk_delete(req: CameraBulkDeleteReq) -> JSONResponse:
    cfg = manager.get_running_config()
    cams = cfg.get("cameras", {})
    req_keys = list(dict.fromkeys(req.keys))  # unique preserve order
    existing = [k for k in req_keys if k in cams]
    missing = [k for k in req_keys if k not in cams]

    # Build the prospective new config by removing only existing keys
    new_cfg = _deepcopy(cfg)
    for k in existing:
        new_cfg.get("cameras", {}).pop(k, None)

    if not req.apply:
        # DRY-RUN: do not error if some are missing; report what would happen
        diff = manager.diff_configs(cfg, new_cfg)
        return _ok(dry=True, diff=diff, to_delete=existing, missing=missing)

    # APPLY mode: if any are missing, keep strict behavior
    if missing:
        raise HTTPException(status_code=404, detail={"missing": missing})

    return _apply_with_errors(
        new_cfg,
        ws_event="cams_deleted",
        ws_payload={"keys": existing},
    )

@app.post("/api/cameras/reorder")
def api_cam_reorder(req: CameraReorderReq) -> JSONResponse:
    cfg = manager.get_running_config()
    cams = cfg.get("cameras", {})
    if not cams:
        raise HTTPException(status_code=400, detail="no cameras to reorder")

    ordered_keys = [k for k in req.order if k in cams]
    for k in cams.keys():
        if k not in ordered_keys:
            ordered_keys.append(k)

    new_cfg = _deepcopy(cfg)
    new_cfg["cameras"] = {k: cams[k] for k in ordered_keys}

    if not req.apply:
        diff = manager.diff_configs(cfg, new_cfg)
        return _ok(dry=True, diff=diff, order=ordered_keys)

    resp = _apply_with_errors(
        new_cfg,
        ws_event="cam_reordered",
        ws_payload={"order": ordered_keys},
    )
    if resp.status_code == 200:
        data = json.loads(resp.body.decode())
        data["order"] = ordered_keys
        return JSONResponse(data)
    return resp

# -----------------------------------------------------------------------------
# Camera set endpoint
# -----------------------------------------------------------------------------
@app.post("/api/cameras/set")
def api_cam_set(req: CameraSetReq) -> JSONResponse:
    cfg = manager.get_running_config()
    if not isinstance(req.value, dict):
        raise HTTPException(status_code=400, detail="value must be an object")

    new_cfg = _deepcopy(cfg)
    new_cfg.setdefault("cameras", {})[req.key] = _deepcopy(req.value)

    if not req.apply:
        diff = manager.diff_configs(cfg, new_cfg)
        return _ok(dry=True, diff=diff)

    return _apply_with_errors(
        new_cfg,
        ws_event="cam_set",
        ws_payload={"key": req.key},
    )


# -----------------------------------------------------------------------------
# Auth helpers (token file, load/save)
# -----------------------------------------------------------------------------
TOKEN_FILE = DATA_DIR / "auth_token.txt"
def _load_token():
    try:
        if TOKEN_FILE.exists():
            return TOKEN_FILE.read_text().strip()
    except Exception:
        pass
    return None
def _save_token(token: str):
    TOKEN_FILE.write_text(token.strip())

# -----------------------------------------------------------------------------
# Stricter middleware: protect all endpoints except UI/static/auth/docs/ping
# -----------------------------------------------------------------------------
from fastapi.responses import JSONResponse

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path

    # Whitelist unauthenticated endpoints and static/UI assets
    WHITELIST_PREFIXES = (
        "/ui",              # UI + static
        "/docs", "/redoc", "/openapi.json",  # docs
        "/api/ping",        # health
        "/api/auth/",       # auth ops
        "/favicon.ico",
    )
    # Allow exact root path only
    if path == "/":
        return await call_next(request)
    if any(path == p or path.startswith(p) for p in WHITELIST_PREFIXES):
        return await call_next(request)

    token = _load_token()
    if not token:
        # No token configured -> open access (dev mode)
        return await call_next(request)

    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if not auth or not auth.lower().startswith("bearer "):
        return JSONResponse({"ok": False, "error": {"error": "Missing Bearer token", "type": "AuthError"}}, status_code=403)
    sent = auth.split(" ", 1)[1].strip()
    if secrets.compare_digest(sent, token):
        return await call_next(request)
    return JSONResponse({"ok": False, "error": {"error": "Invalid token", "type": "AuthError"}}, status_code=403)

# -----------------------------------------------------------------------------
# Auth endpoints (keep existing, do not modify)
# -----------------------------------------------------------------------------
# (Assume already present elsewhere in code)

# -----------------------------------------------------------------------------
# WebSocket
# -----------------------------------------------------------------------------
@app.websocket("/ws")
async def ws(ws: WebSocket):
    await bus.connect(ws)
    try:
        while True:
            _ = await ws.receive_text()  # ping/pong
    except WebSocketDisconnect:
        bus.disconnect(ws)

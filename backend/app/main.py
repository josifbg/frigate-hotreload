from __future__ import annotations
import asyncio
import json
import traceback
import logging
from pathlib import Path
from typing import Optional, List, Any, Dict
from types import SimpleNamespace

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

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
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

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

app.mount("/ui", StaticFiles(directory=BASE_DIR / "static", html=True), name="ui")

# -----------------------------------------------------------------------------
# Routes: config
# -----------------------------------------------------------------------------
@app.get("/api/config")
def get_config() -> dict:
    return manager.get_running_config()

@app.post("/api/config/validate")
def validate_config(cfg: dict) -> dict:
    try:
        json.dumps(cfg)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

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
    result = manager.apply_config(_deepcopy(cfg))
    return _ok(imported=True, result=result)

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

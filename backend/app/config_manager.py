from __future__ import annotations
from typing import Dict, Any, Tuple
from pydantic import ValidationError
from .config_schema import RootConfig, CameraConfig

class ConfigManager:
    def __init__(self, initial: RootConfig | None = None):
        self._running = initial or RootConfig()

    @property
    def running(self) -> RootConfig:
        return self._running

    def validate(self, data: Dict[str, Any]) -> Tuple[bool, str]:
        try:
            RootConfig.model_validate(data)
            return True, "ok"
        except ValidationError as ve:
            return False, ve.json()

    def diff(self, new: RootConfig):
        result = {"hot": [], "warm": []}

        if new.mqtt != self._running.mqtt:
            result["hot"].append({"component": "mqtt"})

        old = self._running.cameras
        newc = new.cameras

        for name in old.keys() - newc.keys():
            result["warm"].append({"component": f"camera:{name}", "action": "remove"})
        for name in newc.keys() - old.keys():
            result["warm"].append({"component": f"camera:{name}", "action": "add"})

        for name in old.keys() & newc.keys():
            o: CameraConfig = old[name]
            n: CameraConfig = newc[name]
            if o.enabled != n.enabled or o.ffmpeg != n.ffmpeg:
                result["warm"].append({"component": f"camera:{name}", "field": "ffmpeg/enabled"})
            if o.zones != n.zones or o.detection != n.detection or o.retention != n.retention:
                result["hot"].append({"component": f"camera:{name}", "field": "zones/detection/retention"})

        return result

    def apply(self, new: RootConfig, workers):
        changes = self.diff(new)

        for c in [c for c in changes["hot"] if c["component"].startswith("camera:")]:
            cname = c["component"].split(":", 1)[1]
            if cname in workers:
                workers[cname].apply_update(new.cameras[cname])

        for c in changes["warm"]:
            if c["component"].startswith("camera:"):
                cname = c["component"].split(":", 1)[1]
                if c.get("action") == "remove" and cname in workers:
                    workers[cname].stop()
                    workers.pop(cname, None)
                elif c.get("action") == "add":
                    from .workers.camera_worker import CameraWorker
                    w = CameraWorker(new.cameras[cname])
                    workers[cname] = w
                    w.start()
                else:
                    if cname in workers:
                        workers[cname].graceful_restart(new.cameras[cname])

        self._running = new
        return changes

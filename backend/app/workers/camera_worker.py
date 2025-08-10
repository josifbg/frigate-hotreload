from __future__ import annotations
import threading, time
from .base import Worker
from ..config_schema import CameraConfig

class CameraWorker(Worker):
    def __init__(self, cfg: CameraConfig):
        self.cfg = cfg
        self._t = None
        self._running = False

    def _run(self):
        while self._running:
            time.sleep(0.5)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()

    def stop(self) -> None:
        self._running = False
        if self._t:
            self._t.join(timeout=2)
            self._t = None

    def apply_update(self, cfg: CameraConfig) -> None:
        self.cfg.zones = cfg.zones
        self.cfg.detection = cfg.detection
        self.cfg.retention = cfg.retention

    def graceful_restart(self, cfg: CameraConfig) -> None:
        self.stop()
        self.cfg = cfg
        self.start()

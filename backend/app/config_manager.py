from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import datetime

class ConfigManager:
    """Minimal, robust manager that works with plain dict configs.
    - Persists to data/config.json
    - Keeps up to 5 rotating backups in data/backups/
    - Provides apply(), get_running_config(), list_backups(), rollback(), reset_to_disk()
    - Diff is simplified (before/after) but stable for preview
    """

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir = self.data_dir / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.data_dir / "config.json"
        self._max_backups = 5
        self._running: Dict[str, Any] = self._read_disk() or self._default()
        # Ensure persisted on first boot
        self._persist(self._running)

    # ------------------------------------------------------------------
    # Public API used by FastAPI app
    # ------------------------------------------------------------------
    def get_running_config(self) -> Dict[str, Any]:
        # Deep copy via JSON to guarantee plain types
        return json.loads(json.dumps(self._running))

    def diff_configs(self, old: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
        return {"before": old, "after": new}

    def apply(self, new_cfg: Any, workers: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Accept dict or model-like and make it the running config.
        The 'workers' arg is accepted for compatibility and ignored here.
        """
        new_dict = self._to_dict(new_cfg)
        # rotate backup of current running
        self._rotate_backup()
        # set and persist
        self._running = json.loads(json.dumps(new_dict))
        self._persist(self._running)
        return {"applied": True, "path": str(self.config_path)}

    def list_backups(self) -> List[str]:
        files = sorted([p.name for p in self.backup_dir.glob("*.json")])
        # only keep tail for display as well
        return files[-self._max_backups:]

    def rollback(self, name: Optional[str] = None) -> bool:
        try:
            if name:
                target = self.backup_dir / name
            else:
                files = sorted(self.backup_dir.glob("*.json"))
                if not files:
                    return False
                target = files[-1]
            if not target.exists():
                return False
            data = json.loads(target.read_text())
            self._running = data
            self._persist(self._running)
            return True
        except Exception:
            return False

    def reset_to_disk(self) -> bool:
        data = self._read_disk()
        if not data:
            return False
        self._running = data
        self._persist(self._running)
        return True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _persist(self, cfg: Dict[str, Any]) -> None:
        self.config_path.write_text(json.dumps(cfg, indent=2))

    def _rotate_backup(self) -> None:
        try:
            if not self.config_path.exists():
                return
            ts = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
            bak = self.backup_dir / f"config.{ts}.json"
            bak.write_text(self.config_path.read_text())
            files = sorted(self.backup_dir.glob("*.json"))
            excess = len(files) - self._max_backups
            for i in range(excess):
                files[i].unlink(missing_ok=True)
        except Exception:
            # best-effort; do not fail apply
            pass

    def _read_disk(self) -> Optional[Dict[str, Any]]:
        try:
            if self.config_path.exists():
                return json.loads(self.config_path.read_text())
        except Exception:
            return None
        return None

    def _default(self) -> Dict[str, Any]:
        return {
            "mqtt": {"host": "mqtt", "port": 1883, "user": None, "password": None, "topic_prefix": "frigate"},
            "cameras": {
                "cam1": {
                    "name": "Front Yard",
                    "enabled": True,
                    "ffmpeg": {"url": "rtsp://example/stream1", "hwaccel": None, "width": 1920, "height": 1080, "fps": 15},
                    "zones": [],
                    "detection": {"score_threshold": 0.6, "iou_threshold": 0.45},
                    "retention": {"mode": "motion", "detection_days": 5, "recording_days": 2, "pre_capture_sec": 3, "post_capture_sec": 3}
                }
            }
        }

    def _to_dict(self, cfg: Any) -> Dict[str, Any]:
        if isinstance(cfg, dict):
            return cfg
        # Pydantic v2
        try:
            from pydantic import BaseModel  # type: ignore
            if isinstance(cfg, BaseModel):
                return cfg.model_dump()  # type: ignore[attr-defined]
        except Exception:
            pass
        # Generic object -> dict recursively
        try:
            return json.loads(json.dumps(cfg, default=lambda o: getattr(o, "__dict__", str(o))))
        except Exception:
            return json.loads(json.dumps(cfg, default=str))

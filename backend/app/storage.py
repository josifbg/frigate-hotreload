from __future__ import annotations
import json
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime

CONFIG_PATH = Path("data/config.json")
BACKUP_DIR = Path("data/backups")
MAX_KEEP = 5  # максимум 5 бекъпа

def _ts() -> str:
    # пример: 2025-08-10_18-03-45
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

def load_config() -> Optional[Dict[str, Any]]:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None

def save_config(cfg: Dict[str, Any]) -> None:
    """Записва активния конфиг на диск (без да прави нов бекъп)."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

def create_backup(cfg: Dict[str, Any]) -> str:
    """Създава бекъп (с timestamp име) и подрязва старите. Връща името на файла."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{_ts()}.json"
    p = BACKUP_DIR / name
    p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    _prune_backups(MAX_KEEP)
    return name

def list_backups() -> List[str]:
    if not BACKUP_DIR.exists():
        return []
    files = [p.name for p in BACKUP_DIR.glob("*.json")]
    files.sort()  # най-старите първи, най-новият е files[-1]
    return files

def load_backup(name: str) -> Optional[Dict[str, Any]]:
    p = BACKUP_DIR / name
    if not p.exists() or not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None

def _prune_backups(max_keep: int) -> None:
    files = sorted(BACKUP_DIR.glob("*.json"))
    excess = len(files) - max_keep
    for i in range(excess):
        try:
            files[i].unlink(missing_ok=True)
        except Exception:
            pass

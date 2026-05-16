"""Tiny JSON persistence helpers for standalone CoLearn."""

from __future__ import annotations

import json
import os
from pathlib import Path
from threading import RLock
from typing import Any


class JsonStateStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path.cwd() / ".colearn" / "state"
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    def read_json(self, name: str, default: Any) -> Any:
        path = self.root / name
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default

    def write_json(self, name: str, value: Any) -> None:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n"
        tmp_path = path.with_name(f".{path.name}.tmp")
        with self._lock:
            tmp_path.write_text(payload, encoding="utf-8")
            os.replace(tmp_path, path)

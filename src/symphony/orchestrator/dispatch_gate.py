"""Persistent master dispatch brake for unattended worker starts."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class DispatchGate:
    """Small runtime-only state file. Missing/corrupt state fails closed."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.RLock()
        self._enabled = False
        self._updated_at: str | None = None
        self._load()

    @property
    def enabled(self) -> bool:
        with self._lock:
            return self._enabled

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self._enabled,
                "default": "off",
                "state_path": str(self._path),
                "updated_at": self._updated_at,
            }

    def set_enabled(self, enabled: bool) -> dict[str, Any]:
        with self._lock:
            self._enabled = bool(enabled)
            self._updated_at = datetime.now(timezone.utc).isoformat()
            self._persist()
            return self.snapshot()

    def _load(self) -> None:
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return
        if not isinstance(payload, dict) or not isinstance(payload.get("enabled"), bool):
            return
        self._enabled = payload["enabled"]
        updated = payload.get("updated_at")
        self._updated_at = updated if isinstance(updated, str) else None

    def _persist(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(f".{self._path.name}.{os.getpid()}.tmp")
        payload = {
            "version": 1,
            "enabled": self._enabled,
            "updated_at": self._updated_at,
        }
        tmp.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, self._path)

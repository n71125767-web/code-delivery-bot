from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
STATE_FILE = Path("/tmp/mcs_runtime_state.json")


def _load_root() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {}
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        logger.exception("RUNTIME_STATE_LOAD_FAILED path=%s", STATE_FILE)
        return {}


def _save_root(root: dict[str, Any]) -> None:
    try:
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(root, ensure_ascii=False), encoding="utf-8")
        tmp.replace(STATE_FILE)
    except Exception:
        logger.exception("RUNTIME_STATE_SAVE_FAILED path=%s", STATE_FILE)


_ROOT = _load_root()


class PersistentDict(dict):
    def __init__(self, name: str):
        self.name = name
        raw = _ROOT.get(name, {})
        if not isinstance(raw, dict):
            raw = {}
        super().__init__((int(k) if str(k).lstrip("-").isdigit() else k, v) for k, v in raw.items())

    def _sync(self) -> None:
        _ROOT[self.name] = {str(k): v for k, v in self.items()}
        _save_root(_ROOT)

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self._sync()

    def pop(self, key, default=None):
        value = super().pop(key, default)
        self._sync()
        return value

    def clear(self):
        super().clear()
        self._sync()

    def update(self, *args, **kwargs):
        super().update(*args, **kwargs)
        self._sync()


class PersistentSet(set):
    def __init__(self, name: str):
        self.name = name
        raw = _ROOT.get(name, [])
        if not isinstance(raw, list):
            raw = []
        super().__init__(int(x) if str(x).lstrip("-").isdigit() else x for x in raw)

    def _sync(self) -> None:
        _ROOT[self.name] = list(self)
        _save_root(_ROOT)

    def add(self, value):
        super().add(value)
        self._sync()

    def discard(self, value):
        super().discard(value)
        self._sync()

    def pop(self):
        value = super().pop()
        self._sync()
        return value

    def clear(self):
        super().clear()
        self._sync()

async def restore_runtime_state() -> None:
    """State is loaded at module import; kept for bot compatibility."""
    return None


async def save_runtime_state() -> None:
    _save_root(_ROOT)


async def runtime_state_loop() -> None:
    import asyncio
    while True:
        await asyncio.sleep(30)
        await save_runtime_state()

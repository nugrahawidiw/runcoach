"""Tiny JSON file cache so each activity is fetched once (API calls are rationed)."""
from __future__ import annotations

import json
from pathlib import Path


class Cache:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def _path(self, kind: str, key: str | int) -> Path:
        return self.root / kind / f"{key}.json"

    def has(self, kind: str, key) -> bool:
        return self._path(kind, key).exists()

    def get(self, kind: str, key):
        p = self._path(kind, key)
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def put(self, kind: str, key, obj) -> None:
        p = self._path(kind, key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(obj), encoding="utf-8")

    def ids(self, kind: str) -> list[str]:
        d = self.root / kind
        return sorted(p.stem for p in d.glob("*.json")) if d.exists() else []

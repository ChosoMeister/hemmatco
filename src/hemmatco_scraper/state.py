from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable


class State:
    """Persistent store of processed post URLs."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._processed: set[str] = set()
        self._loaded = False

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> None:
        if self._loaded:
            return
        if self._path.exists():
            with self._path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
                self._processed = set(data.get("processed_posts", []))
        else:
            self._path.parent.mkdir(parents=True, exist_ok=True)
        self._loaded = True

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"processed_posts": sorted(self._processed)}
        with self._path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)

    def is_processed(self, url: str) -> bool:
        self.load()
        return url in self._processed

    def mark_processed(self, urls: Iterable[str]) -> None:
        self.load()
        self._processed.update(urls)

    def processed_urls(self) -> set[str]:
        self.load()
        return set(self._processed)


__all__ = ["State"]

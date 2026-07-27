from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable


class State:
    """Persistent store of processed post URLs."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._processed: set[str] = set()
        self._announced: set[str] = set()
        self._processed_images: dict[str, set[str]] = {}
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
                self._announced = set(data.get("announced_posts", []))
                self._processed_images = {
                    post_url: set(image_urls)
                    for post_url, image_urls in data.get("processed_images", {}).items()
                    if isinstance(post_url, str) and isinstance(image_urls, list)
                }
        else:
            self._path.parent.mkdir(parents=True, exist_ok=True)
        self._loaded = True

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "processed_posts": sorted(self._processed),
            "announced_posts": sorted(self._announced),
            "processed_images": {
                post_url: sorted(image_urls)
                for post_url, image_urls in sorted(self._processed_images.items())
                if image_urls
            },
        }
        temporary_path = self._path.with_suffix(f"{self._path.suffix}.tmp")
        with temporary_path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
            fh.flush()
            os.fsync(fh.fileno())
        temporary_path.replace(self._path)

    def is_processed(self, url: str) -> bool:
        self.load()
        return url in self._processed

    def mark_processed(self, urls: Iterable[str]) -> None:
        self.load()
        for url in urls:
            self._processed.add(url)
            self._announced.discard(url)
            self._processed_images.pop(url, None)

    def is_announced(self, url: str) -> bool:
        self.load()
        return url in self._announced

    def mark_announced(self, url: str) -> None:
        self.load()
        self._announced.add(url)

    def is_image_processed(self, post_url: str, image_url: str) -> bool:
        self.load()
        return image_url in self._processed_images.get(post_url, set())

    def mark_image_processed(self, post_url: str, image_url: str) -> None:
        self.load()
        self._processed_images.setdefault(post_url, set()).add(image_url)

    def processed_urls(self) -> set[str]:
        self.load()
        return set(self._processed)

    def clear(self) -> None:
        """Forget every processed URL and persist the empty state."""

        self._processed = set()
        self._announced = set()
        self._processed_images = {}
        self._loaded = True
        self.save()


__all__ = ["State"]

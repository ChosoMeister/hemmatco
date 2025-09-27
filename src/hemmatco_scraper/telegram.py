from __future__ import annotations

import logging
from typing import Iterable, Optional

import requests

logger = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org"
MESSAGE_LIMIT = 4000


def chunk_lines(lines: Iterable[str], limit: int = MESSAGE_LIMIT) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in lines:
        line_len = len(line)
        if current and current_len + line_len + 1 > limit:
            chunks.append("\n".join(current))
            current = [line]
            current_len = line_len
        else:
            current.append(line)
            current_len += line_len if not current_len else line_len + 1
    if current:
        chunks.append("\n".join(current))
    return chunks


def send_messages(
    token: str,
    chat_id: str,
    topic_id: Optional[int],
    lines: Iterable[str],
    disable_preview: bool = True,
) -> None:
    payloads = chunk_lines(lines)
    for index, text in enumerate(payloads):
        data = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": disable_preview,
        }
        if topic_id is not None:
            data["message_thread_id"] = topic_id
        url = f"{API_BASE}/bot{token}/sendMessage"
        response = requests.post(url, json=data, timeout=30)
        try:
            response.raise_for_status()
        except requests.HTTPError:
            logger.error("Telegram API error: %s", response.text)
            raise
        logger.info("Sent message %s/%s to Telegram", index + 1, len(payloads))


def send_photos(
    token: str,
    chat_id: str,
    topic_id: Optional[int],
    image_urls: Iterable[str],
) -> None:
    photos = list(image_urls)
    if not photos:
        return
    total = len(photos)
    for index, image_url in enumerate(photos, start=1):
        data = {
            "chat_id": chat_id,
            "photo": image_url,
        }
        if topic_id is not None:
            data["message_thread_id"] = topic_id
        url = f"{API_BASE}/bot{token}/sendPhoto"
        response = requests.post(url, data=data, timeout=60)
        try:
            response.raise_for_status()
        except requests.HTTPError:
            logger.error("Telegram API error while sending photo: %s", response.text)
            raise
        logger.info("Sent photo %s/%s to Telegram", index, total)


__all__ = ["send_messages", "send_photos"]

from __future__ import annotations

import logging
import mimetypes
import os
import time
from typing import Iterable, Optional
from urllib.parse import unquote, urlparse

import requests

logger = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org"
MESSAGE_LIMIT = 4000
DEFAULT_RETRY_DELAY = 5
TELEGRAM_TIMEOUT = 30


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


def _extract_retry_after(response: requests.Response) -> int:
    try:
        payload = response.json()
    except ValueError:
        return DEFAULT_RETRY_DELAY

    if isinstance(payload, dict):
        retry_after = payload.get("retry_after")
        parameters = payload.get("parameters")
        if isinstance(parameters, dict) and retry_after is None:
            retry_after = parameters.get("retry_after")
        try:
            if retry_after is not None:
                retry_value = int(retry_after)
                if retry_value > 0:
                    return retry_value
        except (TypeError, ValueError):
            pass
    return DEFAULT_RETRY_DELAY


def _post_telegram(url: str, *, timeout: int = TELEGRAM_TIMEOUT, **kwargs) -> requests.Response:
    while True:
        response = requests.post(url, timeout=timeout, **kwargs)
        if response.status_code != 429:
            return response
        delay = _extract_retry_after(response)
        logger.warning(
            "Telegram rate limit encountered for %s; sleeping %s second(s) before retrying",
            url,
            delay,
        )
        time.sleep(max(1, delay))


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
        response = _post_telegram(url, json=data)
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
    *,
    download_headers: Optional[dict[str, str]] = None,
    download_timeout: int = 60,
) -> None:
    photos = list(image_urls)
    if not photos:
        return
    total = len(photos)
    for index, image_url in enumerate(photos, start=1):
        try:
            filename, content_type, payload = _download_image(
                image_url,
                headers=download_headers,
                timeout=download_timeout,
            )
        except requests.RequestException as exc:
            logger.error("Failed to download %s: %s", image_url, exc)
            raise

        data = {
            "chat_id": chat_id,
        }
        if topic_id is not None:
            data["message_thread_id"] = topic_id
        files = {
            "photo": (filename, payload, content_type or "application/octet-stream"),
        }
        url = f"{API_BASE}/bot{token}/sendPhoto"
        response = _post_telegram(url, data=data, files=files, timeout=download_timeout)
        try:
            response.raise_for_status()
        except requests.HTTPError:
            logger.error("Telegram API error while sending photo: %s", response.text)
            raise
        logger.info("Sent photo %s/%s to Telegram", index, total)


def _download_image(
    url: str,
    *,
    headers: Optional[dict[str, str]] = None,
    timeout: int,
) -> tuple[str, Optional[str], bytes]:
    response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    content_type = response.headers.get("Content-Type")
    filename = _infer_filename(url, content_type)
    return filename, content_type, response.content


def _infer_filename(url: str, content_type: Optional[str]) -> str:
    parsed = urlparse(url)
    candidate = unquote(os.path.basename(parsed.path))
    if not candidate:
        candidate = "photo"
    if "." not in candidate and content_type:
        mime = content_type.split(";", 1)[0].strip()
        extension = mimetypes.guess_extension(mime)
        if extension:
            candidate = f"{candidate}{extension}"
    return candidate


__all__ = ["send_messages", "send_photos"]

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Iterable, Iterator, List, Mapping, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests import Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import Settings
from .state import State

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class Post:
    title: str
    url: str
    image_urls: list[str]


class SourceUnavailableError(RuntimeError):
    """Raised when the WordPress API cannot provide a complete post listing."""


def create_session(settings: Settings) -> Session:
    session = requests.Session()
    retries = Retry(
        total=2,
        connect=2,
        read=2,
        status=2,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "POST"),
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({
        "User-Agent": settings.user_agent,
        "Accept-Language": "en-US,en;q=0.9,fa;q=0.8",
    })
    return session


def iter_api_posts(
    session: Session,
    settings: Settings,
) -> Iterator[tuple[str, str, str, str | None]]:
    api_url = urljoin(settings.base_url, "/wp-json/wp/v2/posts")
    per_page = max(1, min(settings.posts_per_page, 100))
    cached_pages: dict[int, list] = {}
    cached_headers: dict[int, Mapping[str, str]] = {}

    class PaginationComplete(Exception):
        """Raised when the API indicates there are no more pages."""

    def fetch_page(page: int) -> list:
        params = {
            "page": page,
            "per_page": per_page,
            "orderby": "date",
            "order": "desc",
            "_embed": "wp:featuredmedia",
            "_fields": "id,link,title.rendered,content.rendered,featured_media,_embedded",
        }
        response = session.get(
            api_url,
            params=params,
            timeout=(settings.connect_timeout, settings.request_timeout),
        )
        if response.status_code == 400:
            raise PaginationComplete
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as exc:
            raise ValueError(f"Invalid JSON payload on page {page}: {exc}") from exc
        if not isinstance(payload, list):
            raise ValueError(f"Unexpected JSON payload on page {page}: {payload!r}")
        cached_pages[page] = payload
        cached_headers[page] = response.headers
        return payload

    try:
        fetch_page(1)
    except PaginationComplete:
        logger.info("No posts returned by the API")
        return
    except requests.RequestException as exc:
        raise SourceUnavailableError(
            f"Hemmatco WordPress API is unavailable: {exc}"
        ) from exc
    except ValueError as exc:
        raise SourceUnavailableError(str(exc)) from exc

    header_total: int | None = None
    try:
        headers = cached_headers.get(1)
        if headers is not None:
            header_total = int(headers.get("X-WP-TotalPages", ""))
    except (ValueError, TypeError):
        header_total = None

    if header_total is None:
        total_pages = settings.total_pages if settings.total_pages > 0 else 1
    else:
        total_pages = header_total

    if settings.total_pages > 0:
        total_pages = min(total_pages, settings.total_pages)

    total_pages = max(1, total_pages)

    for page in range(total_pages, 0, -1):
        if page in cached_pages:
            items = cached_pages[page]
        else:
            try:
                items = fetch_page(page)
            except PaginationComplete:
                raise SourceUnavailableError(
                    f"WordPress API ended unexpectedly at page {page}"
                )
            except requests.RequestException as exc:
                raise SourceUnavailableError(
                    f"Failed to retrieve WordPress API page {page}: {exc}"
                ) from exc
            except ValueError as exc:
                raise SourceUnavailableError(str(exc)) from exc

        if not items:
            continue

        for item in reversed(items):
            link = (item.get("link") or "").strip()
            title_html = item.get("title", {}).get("rendered", "")
            title = BeautifulSoup(title_html, "html.parser").get_text(" ", strip=True)
            content_html = item.get("content", {}).get("rendered", "")
            featured_url = _featured_image_url(item)
            if not link:
                continue
            yield (title or link, link, content_html, featured_url)


def _featured_image_url(item: Mapping) -> str | None:
    embedded = item.get("_embedded")
    if not isinstance(embedded, Mapping):
        return None
    media_items = embedded.get("wp:featuredmedia")
    if not isinstance(media_items, list) or not media_items:
        return None
    media = media_items[0]
    if not isinstance(media, Mapping):
        return None
    source_url = media.get("source_url")
    return source_url.strip() if isinstance(source_url, str) and source_url.strip() else None


def _parse_srcset(value: str) -> list[Tuple[str, float]]:
    candidates: list[Tuple[str, float]] = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        parts = item.split()
        if not parts:
            continue
        source = parts[0]
        descriptor = parts[1] if len(parts) > 1 else ""
        score = 0.0
        if descriptor.endswith("w"):
            try:
                score = float(descriptor[:-1])
            except ValueError:
                score = 0.0
        elif descriptor.endswith("x"):
            try:
                score = float(descriptor[:-1]) * 1000
            except ValueError:
                score = 0.0
        candidates.append((source, score))
    return candidates


def _select_best_image(img, base_url: str) -> str | None:
    priority_sources: list[Tuple[str, float]] = []
    for attr in (
        "data-full-image",
        "data-full_image",
        "data-large_image",
        "data-large_image_url",
        "data-original",
        "data-orig-file",
    ):
        value = (img.get(attr) or "").strip()
        if value:
            priority_sources.append((urljoin(base_url, value), 1_000_000.0))

    for attr in ("data-srcset", "data-src-set", "srcset"):
        value = img.get(attr)
        if not value:
            continue
        for source, score in _parse_srcset(value):
            priority_sources.append((urljoin(base_url, source), score))

    for attr in ("data-src", "data-lazy-src", "src"):
        value = (img.get(attr) or "").strip()
        if value:
            priority_sources.append((urljoin(base_url, value), -1.0))

    if not priority_sources:
        return None

    best_url, _ = max(priority_sources, key=lambda item: item[1])
    return best_url


def extract_images_from_html(
    html: str,
    base_url: str,
    featured_url: str | None = None,
) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    image_urls: list[str] = []
    seen: set[str] = set()

    def append_images(elements: Iterable) -> None:
        for img in elements:
            best = _select_best_image(img, base_url)
            if not best:
                continue
            absolute = best.strip()
            if absolute in seen:
                continue
            seen.add(absolute)
            image_urls.append(absolute)

    if featured_url:
        absolute_featured_url = urljoin(base_url, featured_url.strip())
        seen.add(absolute_featured_url)
        image_urls.append(absolute_featured_url)

    append_images(soup.select("img"))

    return image_urls


def collect_new_posts(session: Session, settings: Settings, state: State) -> List[Post]:
    state.load()
    seen = state.processed_urls()
    posts: list[Post] = []
    seen_in_run: set[str] = set()
    for title, post_url, content_html, featured_url in iter_api_posts(session, settings):
        if post_url in seen or post_url in seen_in_run:
            continue
        image_urls = extract_images_from_html(content_html, post_url, featured_url)
        posts.append(Post(title=title, url=post_url, image_urls=image_urls))
        seen_in_run.add(post_url)
    return posts


def sleep_between_posts(index: int, total: int, settings: Settings, initial_run: bool) -> None:
    if total <= 1:
        return
    if initial_run:
        delay = settings.initial_sleep_seconds
    else:
        delay = settings.subsequent_sleep_seconds
    if delay <= 0:
        return
    logger.info("Sleeping %.1f seconds before processing next post (%s/%s)", delay, index + 1, total)
    time.sleep(delay)


__all__ = [
    "Post",
    "SourceUnavailableError",
    "collect_new_posts",
    "create_session",
    "extract_images_from_html",
    "sleep_between_posts",
]

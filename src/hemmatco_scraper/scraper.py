from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Iterable, Iterator, List, Mapping
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests import Response, Session
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


def create_session(settings: Settings) -> Session:
    session = requests.Session()
    retries = Retry(
        total=5,
        backoff_factor=0.5,
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


def _fetch(session: Session, url: str, settings: Settings) -> Response:
    logger.debug("Fetching %s", url)
    resp = session.get(url, timeout=settings.request_timeout)
    resp.raise_for_status()
    return resp


def iter_api_posts(session: Session, settings: Settings) -> Iterator[tuple[str, str]]:
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
            "_fields": "link,title.rendered",
        }
        response = session.get(api_url, params=params, timeout=settings.request_timeout)
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
        logger.warning("Stopping pagination at page 1 due to error: %s", exc)
        return
    except ValueError as exc:
        logger.warning("%s", exc)
        return

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
                logger.warning("Reached end of available posts at page %s", page)
                continue
            except requests.RequestException as exc:
                logger.warning("Stopping pagination at page %s due to error: %s", page, exc)
                break
            except ValueError as exc:
                logger.warning("%s", exc)
                continue

        if not items:
            continue

        for item in reversed(items):
            link = (item.get("link") or "").strip()
            title_html = item.get("title", {}).get("rendered", "")
            title = BeautifulSoup(title_html, "html.parser").get_text(" ", strip=True)
            if not link:
                continue
            yield (title or link, link)


def extract_images(session: Session, url: str, settings: Settings) -> list[str]:
    response = _fetch(session, url, settings)
    soup = BeautifulSoup(response.text, "html.parser")
    image_urls: list[str] = []
    seen: set[str] = set()
    selectors = [
        "div.blog-details img",
        "article img",
        "main img",
    ]

    def append_images(elements: Iterable) -> None:
        for img in elements:
            src = img.get("data-src") or img.get("data-lazy-src") or img.get("src")
            if not src:
                continue
            absolute = urljoin(url, src.strip())
            if absolute in seen:
                continue
            seen.add(absolute)
            image_urls.append(absolute)

    for selector in selectors:
        append_images(soup.select(selector))
        if image_urls:
            break

    if not image_urls:
        candidates = []
        for img in soup.select("img"):
            ancestor_classes = " ".join(
                " ".join(parent.get("class", [])) if hasattr(parent, "get") else ""
                for parent in img.parents
            ).lower()
            img_classes = " ".join(img.get("class", [])).lower()
            if "logo" in ancestor_classes or "logo" in img_classes:
                continue
            candidates.append(img)
        append_images(candidates)

    return image_urls


def collect_new_posts(session: Session, settings: Settings, state: State) -> List[Post]:
    state.load()
    seen = state.processed_urls()
    posts: list[Post] = []
    seen_in_run: set[str] = set()
    for title, post_url in iter_api_posts(session, settings):
        if post_url in seen or post_url in seen_in_run:
            continue
        try:
            image_urls = extract_images(session, post_url, settings)
        except requests.RequestException as exc:
            logger.warning("Failed to fetch %s: %s", post_url, exc)
            continue
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
    "collect_new_posts",
    "create_session",
    "sleep_between_posts",
]

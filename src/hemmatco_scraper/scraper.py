from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Iterable, List
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


def iter_blog_pages(settings: Settings) -> Iterable[str]:
    # Start from the oldest page (highest page number) back to the newest.
    for page in range(settings.total_pages, 0, -1):
        if page == 1:
            yield settings.base_url
        else:
            yield settings.base_url.rstrip("/") + f"/page/{page}/"


def parse_post_links(html: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    posts: list[tuple[str, str]] = []
    for article in soup.select("article"):
        heading = article.find(["h2", "h3"], class_=lambda _: True)
        anchor = heading.find("a", href=True) if heading else article.find("a", href=True)
        if not anchor:
            continue
        title = anchor.get_text(strip=True)
        url = anchor["href"].strip()
        if not title or not url:
            continue
        posts.append((title, url))
    return posts


def extract_images(session: Session, url: str, settings: Settings) -> list[str]:
    response = _fetch(session, url, settings)
    soup = BeautifulSoup(response.text, "html.parser")
    image_urls: list[str] = []
    for img in soup.select("article img"):
        src = img.get("data-src") or img.get("data-lazy-src") or img.get("src")
        if not src:
            continue
        absolute = urljoin(url, src.strip())
        if absolute not in image_urls:
            image_urls.append(absolute)
    return image_urls


def collect_new_posts(session: Session, settings: Settings, state: State) -> List[Post]:
    state.load()
    seen = state.processed_urls()
    posts: list[Post] = []
    seen_in_run: set[str] = set()
    for page_url in iter_blog_pages(settings):
        try:
            response = _fetch(session, page_url, settings)
        except requests.RequestException as exc:
            logger.warning("Skipping %s due to error: %s", page_url, exc)
            continue
        post_links = list(reversed(parse_post_links(response.text)))
        for title, post_url in post_links:
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

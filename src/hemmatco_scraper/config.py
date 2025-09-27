from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Optional


@dataclass(slots=True)
class Settings:
    """Runtime configuration for the scraper."""

    base_url: str
    total_pages: int
    posts_per_page: int
    request_timeout: int
    initial_sleep_seconds: float
    subsequent_sleep_seconds: float
    state_file: Path
    telegram_token: str
    telegram_chat_id: str
    telegram_topic_id: Optional[int]
    user_agent: str

    @classmethod
    def from_env(cls) -> "Settings":
        base_url = os.getenv("BLOG_BASE_URL", "https://hemmatco.com/blog/")
        total_pages = int(os.getenv("BLOG_TOTAL_PAGES", "48"))
        posts_per_page = int(os.getenv("BLOG_POSTS_PER_PAGE", "10"))
        request_timeout = int(os.getenv("BLOG_REQUEST_TIMEOUT", "30"))
        initial_sleep_seconds = float(os.getenv("INITIAL_POST_SLEEP_SECONDS", "5"))
        subsequent_sleep_seconds = float(os.getenv("SUBSEQUENT_POST_SLEEP_SECONDS", "1"))
        state_file = Path(os.getenv("STATE_FILE", "state/processed_posts.json"))
        telegram_token = os.environ["TELEGRAM_BOT_TOKEN"]
        telegram_chat_id = os.environ["TELEGRAM_CHAT_ID"]
        telegram_topic = os.getenv("TELEGRAM_TOPIC_ID")
        telegram_topic_id = int(telegram_topic) if telegram_topic else None
        user_agent = os.getenv(
            "SCRAPER_USER_AGENT",
            "hemmatco-scraper/1.0 (+https://github.com/)",
        )

        return cls(
            base_url=base_url,
            total_pages=total_pages,
            posts_per_page=posts_per_page,
            request_timeout=request_timeout,
            initial_sleep_seconds=initial_sleep_seconds,
            subsequent_sleep_seconds=subsequent_sleep_seconds,
            state_file=state_file,
            telegram_token=telegram_token,
            telegram_chat_id=telegram_chat_id,
            telegram_topic_id=telegram_topic_id,
            user_agent=user_agent,
        )


__all__ = ["Settings"]

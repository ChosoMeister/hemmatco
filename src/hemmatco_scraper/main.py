from __future__ import annotations

import logging
from typing import Iterable

from .config import Settings
from .scraper import Post, collect_new_posts, create_session, sleep_between_posts
from .state import State
from .telegram import send_messages, send_photos

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


def format_post(post: Post) -> Iterable[str]:
    yield f"📌 {post.title}"


def dispatch_posts(settings: Settings, posts: list[Post], state: State) -> None:
    if not posts:
        # Ensure the state file exists so downstream cache steps have a
        # concrete path even when no new posts are discovered.
        state.save()
        logger.info("No new posts to dispatch")
        return

    initial_run = not state.processed_urls()
    total = len(posts)
    logger.info("Dispatching %s post(s) to Telegram", total)

    for idx, post in enumerate(posts):
        logger.info("Processing post %s/%s: %s", idx + 1, total, post.url)
        if not post.image_urls:
            logger.info("Skipping %s because no images were found", post.url)
        else:
            send_messages(
                settings.telegram_token,
                settings.telegram_chat_id,
                settings.telegram_topic_id,
                format_post(post),
            )
            send_photos(
                settings.telegram_token,
                settings.telegram_chat_id,
                settings.telegram_topic_id,
                post.image_urls,
            )
            logger.info("Sent %s with %s image(s)", post.url, len(post.image_urls))
        state.mark_processed([post.url])
        state.save()
        logger.info("Recorded %s as processed", post.url)
        if idx < total - 1:
            sleep_between_posts(idx, total, settings, initial_run)


def main() -> None:
    settings = Settings.from_env()
    state = State(settings.state_file)
    if settings.reset_state:
        logger.info("RESET_STATE enabled – clearing processed posts cache")
        state.clear()
    session = create_session(settings)
    posts = collect_new_posts(session, settings, state)
    dispatch_posts(settings, posts, state)


if __name__ == "__main__":
    main()

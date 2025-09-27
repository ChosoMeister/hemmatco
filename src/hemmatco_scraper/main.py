from __future__ import annotations

import logging
from typing import Iterable

from .config import Settings
from .scraper import Post, collect_new_posts, create_session, sleep_between_posts
from .state import State
from .telegram import send_messages

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


def format_post(post: Post) -> Iterable[str]:
    header = f"📌 {post.title}\n{post.url}"
    yield header
    for index, image_url in enumerate(post.image_urls, start=1):
        yield f"{index}. {image_url}"


def dispatch_posts(settings: Settings, posts: list[Post], state: State) -> None:
    if not posts:
        logger.info("No new posts to dispatch")
        return

    initial_run = not state.processed_urls()
    total = len(posts)

    for idx, post in enumerate(posts):
        if not post.image_urls:
            logger.info("Skipping %s because no images were found", post.url)
        else:
            send_messages(
                settings.telegram_token,
                settings.telegram_chat_id,
                settings.telegram_topic_id,
                format_post(post),
            )
        state.mark_processed([post.url])
        state.save()
        if idx < total - 1:
            sleep_between_posts(idx, total, settings, initial_run)


def main() -> None:
    settings = Settings.from_env()
    state = State(settings.state_file)
    session = create_session(settings)
    posts = collect_new_posts(session, settings, state)
    dispatch_posts(settings, posts, state)


if __name__ == "__main__":
    main()

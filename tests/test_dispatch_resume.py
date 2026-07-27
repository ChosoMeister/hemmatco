from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import requests

from hemmatco_scraper.main import DispatchIncompleteError, dispatch_posts
from hemmatco_scraper.scraper import Post
from hemmatco_scraper.state import State


def settings() -> SimpleNamespace:
    return SimpleNamespace(
        telegram_token="token",
        telegram_chat_id="chat",
        telegram_topic_id=None,
        user_agent="test",
        initial_sleep_seconds=0,
        subsequent_sleep_seconds=0,
    )


class DispatchResumeTests(unittest.TestCase):
    def test_interrupted_post_resumes_at_next_image(self) -> None:
        with self.subTest("resume"):
            import tempfile

            with tempfile.TemporaryDirectory() as directory:
                state_path = Path(directory) / "state.json"
                post = Post(
                    "Title",
                    "https://example.test/post",
                    ["image-1", "image-2", "image-3"],
                )
                sent: list[str] = []

                def fail_on_second_photo(*args, **kwargs) -> None:
                    image_url = args[3][0]
                    if image_url == "image-2":
                        raise RuntimeError("interrupted")
                    sent.append(image_url)

                with (
                    patch("hemmatco_scraper.main.send_messages") as send_message,
                    patch(
                        "hemmatco_scraper.main.send_photos",
                        side_effect=fail_on_second_photo,
                    ),
                    self.assertRaises(RuntimeError),
                ):
                    dispatch_posts(settings(), [post], State(state_path))

                self.assertEqual(sent, ["image-1"])
                send_message.assert_called_once()

                with (
                    patch("hemmatco_scraper.main.send_messages") as resumed_message,
                    patch(
                        "hemmatco_scraper.main.send_photos",
                        side_effect=lambda *args, **kwargs: sent.append(args[3][0]),
                    ),
                ):
                    dispatch_posts(settings(), [post], State(state_path))

                self.assertEqual(sent, ["image-1", "image-2", "image-3"])
                resumed_message.assert_not_called()
                self.assertTrue(State(state_path).is_processed(post.url))

    def test_old_state_format_still_loads(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            state_path.write_text(
                '{"processed_posts": ["https://example.test/done"]}',
                encoding="utf-8",
            )

            state = State(state_path)

            self.assertTrue(state.is_processed("https://example.test/done"))
            self.assertFalse(state.is_announced("https://example.test/new"))

    def test_failed_image_does_not_block_later_images(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            post = Post(
                "Title",
                "https://example.test/post",
                ["image-1", "image-2", "image-3"],
            )
            sent: list[str] = []

            def fail_middle_image(*args, **kwargs) -> None:
                image_url = args[3][0]
                if image_url == "image-2":
                    raise requests.RequestException("bad image")
                sent.append(image_url)

            with (
                patch("hemmatco_scraper.main.send_messages"),
                patch(
                    "hemmatco_scraper.main.send_photos",
                    side_effect=fail_middle_image,
                ),
                self.assertRaises(DispatchIncompleteError),
            ):
                dispatch_posts(settings(), [post], State(state_path))

            self.assertEqual(sent, ["image-1", "image-3"])
            state = State(state_path)
            self.assertTrue(state.is_image_processed(post.url, "image-1"))
            self.assertFalse(state.is_image_processed(post.url, "image-2"))
            self.assertTrue(state.is_image_processed(post.url, "image-3"))
            self.assertFalse(state.is_processed(post.url))


if __name__ == "__main__":
    unittest.main()

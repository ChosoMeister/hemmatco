from types import SimpleNamespace
import unittest
from unittest.mock import patch

import requests

from hemmatco_scraper.scraper import (
    SourceUnavailableError,
    extract_images_from_html,
    iter_api_posts,
)


class FakeResponse:
    def __init__(self, payload: list[dict], total_pages: int = 1) -> None:
        self._payload = payload
        self.headers = {"X-WP-TotalPages": str(total_pages)}
        self.status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> list[dict]:
        return self._payload


class FakeSession:
    def __init__(self, pages: dict[int, list[dict]]) -> None:
        self.pages = pages
        self.requested_pages: list[int] = []

    def get(self, url, *, params, timeout, verify):
        page = params["page"]
        self.requested_pages.append(page)
        return FakeResponse(self.pages[page], total_pages=len(self.pages))


def api_item(post_id: int) -> dict:
    return {
        "id": post_id,
        "link": f"https://hemmatco.com/post-{post_id}/",
        "title": {"rendered": f"Post {post_id}"},
        "content": {
            "rendered": f'<p><img src="/uploads/image-{post_id}.jpg"></p>',
        },
        "featured_media": 0,
        "_embedded": {},
    }


class WordPressApiTests(unittest.TestCase):
    def settings(self) -> SimpleNamespace:
        return SimpleNamespace(
            base_url="https://hemmatco.com/blog/",
            posts_per_page=100,
            total_pages=0,
            connect_timeout=10,
            request_timeout=30,
            expired_cert_sha256="PIN",
            source_tls_verify=True,
        )

    def test_posts_are_returned_oldest_to_newest_across_pages(self) -> None:
        # WordPress returns each API page newest-first.
        session = FakeSession(
            {
                1: [api_item(4), api_item(3)],
                2: [api_item(2), api_item(1)],
            }
        )
        posts = list(iter_api_posts(session, self.settings()))

        self.assertEqual(
            [post_url for _, post_url, _, _ in posts],
            [
                "https://hemmatco.com/post-1/",
                "https://hemmatco.com/post-2/",
                "https://hemmatco.com/post-3/",
                "https://hemmatco.com/post-4/",
            ],
        )

    def test_unavailable_api_fails_without_returning_partial_results(self) -> None:
        class UnavailableSession:
            def get(self, *args, **kwargs):
                raise requests.Timeout("source timed out")

        with self.assertRaises(SourceUnavailableError):
            list(iter_api_posts(UnavailableSession(), self.settings()))

    def test_expired_certificate_uses_fallback_only_after_pin_match(self) -> None:
        class ExpiredThenAvailableSession:
            def __init__(self) -> None:
                self.calls: list[bool] = []

            def get(self, *args, **kwargs):
                verify = kwargs["verify"]
                self.calls.append(verify)
                if verify:
                    raise requests.exceptions.SSLError("certificate has expired")
                return FakeResponse([api_item(1)])

        session = ExpiredThenAvailableSession()
        settings = self.settings()
        with patch("hemmatco_scraper.scraper.allow_pinned_expired_certificate") as pin:
            posts = list(iter_api_posts(session, settings))

        pin.assert_called_once()
        self.assertEqual(session.calls, [True, False])
        self.assertFalse(settings.source_tls_verify)
        self.assertEqual(len(posts), 1)

    def test_expired_certificate_is_rejected_when_pin_changes(self) -> None:
        class ExpiredSession:
            def get(self, *args, **kwargs):
                raise requests.exceptions.SSLError("certificate has expired")

        with (
            patch(
                "hemmatco_scraper.scraper.allow_pinned_expired_certificate",
                side_effect=OSError("fingerprint changed"),
            ),
            self.assertRaises(SourceUnavailableError),
        ):
            list(iter_api_posts(ExpiredSession(), self.settings()))

    def test_featured_then_inline_images_preserve_content_order(self) -> None:
        html = """
        <p>
          <img src="/small-1.jpg"
               srcset="/small-1.jpg 300w, /large-1.jpg 1600w">
          <img data-src="/image-2.jpg">
          <img src="/large-1.jpg">
        </p>
        """

        images = extract_images_from_html(
            html,
            "https://hemmatco.com/example/",
            "https://hemmatco.com/featured.jpg",
        )

        self.assertEqual(
            images,
            [
                "https://hemmatco.com/featured.jpg",
                "https://hemmatco.com/large-1.jpg",
                "https://hemmatco.com/image-2.jpg",
            ],
        )


if __name__ == "__main__":
    unittest.main()

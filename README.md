# Hemmatco Blog Scraper

This project scrapes the Hemmatco blog, collects direct links to all images inside each post, and forwards the results to a Telegram forum thread. It only runs when manually triggered from GitHub Actions.

## Features

- Reads all available posts from the WordPress REST API in chronological order.
- Extracts featured and inline images directly from the API response without opening every post page.
- On the first run it processes the entire available history starting from the oldest post and waits 5 seconds between Telegram posts.
- Subsequent runs only send newly discovered posts and use a shorter (configurable) delay.
- Downloads and sends the discovered image files to a Telegram forum topic via a bot.
- Persists progress after every Telegram message and image in `state/processed_posts.json`, so an interrupted run resumes from the next unsent image.

## Local execution

1. Create and activate a Python 3.11 virtual environment.
2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Create a `.env` file or export the required environment variables (see below).
4. Run the scraper:

   ```bash
   python -m hemmatco_scraper
   ```

## Required environment variables

| Variable | Description |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token that has access to the destination group. |
| `TELEGRAM_CHAT_ID` | Numeric ID of the Telegram group (e.g., `-1001234567890`). |
| `TELEGRAM_TOPIC_ID` | ID of the forum topic inside the group. Leave empty for non-topic groups. |

### Optional configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `BLOG_BASE_URL` | `https://hemmatco.com/blog/` | Base blog URL. |
| `BLOG_TOTAL_PAGES` | `0` | Optional page cap. `0` follows the API-reported total and reads the full history. |
| `BLOG_POSTS_PER_PAGE` | `100` | Number of WordPress posts requested per API page. |
| `BLOG_CONNECT_TIMEOUT` | `10` | Connection timeout in seconds. |
| `BLOG_REQUEST_TIMEOUT` | `30` | HTTP timeout in seconds. |
| `INITIAL_POST_SLEEP_SECONDS` | `5` | Delay between posts during the very first full crawl. |
| `SUBSEQUENT_POST_SLEEP_SECONDS` | `1` | Delay between posts on later runs. |
| `STATE_FILE` | `state/processed_posts.json` | Location of the JSON state file. |
| `RESET_STATE` | `false` | When `true`, clears the cached list of processed posts before running (useful for tests). |
| `SCRAPER_USER_AGENT` | `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36` | Custom User-Agent header for requests. |

## Manual GitHub Actions run

The repository includes `.github/workflows/scrape.yml`, which has no schedule and only runs via manual dispatch. Configure the following repository secrets so the workflow can send Telegram updates:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `TELEGRAM_TOPIC_ID` (optional)

The workflow preserves `state/processed_posts.json` across runs using the GitHub Actions cache. Do not delete the workflow cache if you want to keep the history and per-image progress.

When you trigger the workflow manually you can optionally set the `reset_state` input to `true` to clear the cached history before scraping. This is useful for test runs where you want to resend every post from the beginning.

## Telegram permissions

Ensure the bot is added to the group and has permission to post messages inside the desired forum topic. Provide the bot token, group ID, and topic ID when setting up the environment variables.

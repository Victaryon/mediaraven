# Config keys

42 keys customizable per chat/user. Defaults and full descriptions live in `customization.example.en.json` (with `_doc_KEY` next to each key).

## Prompts and timeouts

| Key | Default | Description | Min | Max |
|---|---|---|---|---|
| `ASK_DL_TIMEOUT` | `5.0` | Seconds to click the download button | 1 | 60 |
| `ASK_LANG_TIMEOUT` | `10.0` | Seconds to choose dub language | 1 | 60 |
| `ASK_CAPTION_TIMEOUT` | `5.0` | Seconds to choose include social media caption | 1 | 60 |
| `ASK_ARTICLE_TIMEOUT` | `5.0` | Seconds to choose include article body | 1 | 60 |
| `ASK_SCREENSHOT_TIMEOUT` | `5.0` | Seconds to choose taking screenshot | 1 | 60 |
| `ASK_DL_DEFAULT` | `"yes"` | Behavior on timeout: `"yes"` downloads, `"no"` ignores | — | — |
| `ASK_CAPTION_DEFAULT` | `"no"` | Behavior on timeout: `"yes"` includes, `"no"` discards | — | — |
| `ASK_ARTICLE_DEFAULT` | `"yes"` | Behavior on timeout: `"yes"` sends article, `"no"` discards | — | — |
| `ASK_SCREENSHOT_DEFAULT` | `"yes"` | Behavior on timeout: `"yes"` takes shot, `"no"` falls back to fail+retry | — | — |
| `PROMPT_DOWNLOAD_ENABLED` | `true` | `false` downloads directly without asking | — | — |
| `PROMPT_CAPTION_ENABLED` | `true` | `false` respects ASK_CAPTION_DEFAULT silently | — | — |
| `PROMPT_LANG_ENABLED` | `true` | `false` downloads original language directly | — | — |

## YT-DLP

| Key | Default | Description | Min | Max |
|---|---|---|---|---|
| `YTDLP_MAX_HEIGHT` | `1920` | Max video height (480/720/1080/1920/2160/4320) | 144 | — |
| `YTDLP_SOCKET_TIMEOUT` | `90` | yt-dlp socket timeout (seconds) | 30 | 600 |
| `YTDLP_YT_CLIENTS` | `"default"` | CSV of extractor clients (`default,mweb` + PO Token for age-restricted) | — | — |

## Generic scraper

| Key | Default | Description | Min | Max |
|---|---|---|---|---|
| `SCRAPE_MAX_PARALLEL_DOWNLOADS` | `6` | Files downloaded in parallel | 1 | 20 |
| `SCRAPE_MAX_MEDIA_URLS` | `60` | Candidate limit | 1 | 500 |
| `SCRAPE_SCROLL_MAX_ROUNDS` | `4` | Scrolls for lazy-load | 0 | 20 |
| `SCRAPE_SCROLL_PAUSE_MS` | `3000` | Pause (ms) between scrolls | 500 | 10000 |
| `SCRAPE_MIN_IMAGE_SIZE` | `50` | Min (px) of image | 1 | 500 |
| `SCRAPE_HLS_TIMEOUT_S` | `180` | ffmpeg timeout muxing HLS/DASH | 30 | 600 |
| `SCRAPE_FAST_PATH_TIMEOUT_S` | `12` | Fast path HTTP timeout | 5 | 60 |
| `SCRAPE_SCREENSHOT_FALLBACK` | `"yes"` | Offers screenshot when nothing finds | — | — |
| `SCRAPE_GALLERY_DL_ENABLE` | `"yes"` | Enables gallery-dl | — | — |
| `SCRAPE_GALLERY_DL_TIMEOUT_S` | `90` | Per gallery-dl call timeout | 30 | 300 |
| `SCRAPE_GALLERY_DL_PARALLEL_FILES` | `3` | Album files downloaded in parallel | 1 | 8 |
| `SCRAPE_PAYWALL_BYPASS` | `"yes"` | Enables Googlebot UA + archive.ph | — | — |
| `SCRAPE_ARCHIVE_TIMEOUT_S` | `15` | archive.ph timeout | 5 | 60 |
| `SCRAPE_ARTICLE_EXTRACT` | `"yes"` | Extracts article body via trafilatura | — | — |
| `SCRAPE_ARTICLE_MIN_CHARS` | `300` | Min chars to consider article | 100 | 2000 |

## Telegram / sending

| Key | Default | Description | Min | Max |
|---|---|---|---|---|
| `MAX_URLS_PER_MESSAGE` | `20` | Max URLs per message | 1 | 50 |
| `MEDIA_GROUP_CHUNK_SIZE` | `10` | sendMediaGroup chunk size (Telegram caps at 10) | 1 | 10 |
| `MEDIA_GROUP_DELAY` | `4.0` | Delay (s) between chunks of 10 — controls flood-risk | 0 | 30 |
| `STATUS_CYCLE_INTERVAL` | `5.0` | Interval (s) between status message rotations | 1 | 30 |
| `TELEGRAM_UPLOAD_TIMEOUT` | `600` | Telegram upload timeout (s) | 30 | 3600 |
| `TELEGRAM_MAX_UPLOAD_MB` | `2000` | Max file size (MB) — Bot API hard limit for bots (Premium doesn't affect) | 50 | 2000 |
| `VIDEO_CONVERT_TIMEOUT` | `900` | Timeout (s) for ffmpeg MP4 conversion (webm/mkv/avi/flv) | 60 | 3600 |

## Platform-specific

| Key | Default | Description | Min | Max |
|---|---|---|---|---|
| `IG_CAPTION_MAX` | `1000` | Max IG caption before truncating | 100 | 2200 |
| `IG_USER_AGENT` | `Instagram 219...` | UA to download IG audio | — | — |
| `IG_QUEUE_WARN_THRESHOLD` | `5` | Instagram queue size for warning | 1 | 100 |
| `THREADS_MIN_IMAGE_SIZE` | `500` | Min (px) of Threads image | 1 | 1000 |
| `REDDIT_JSON_UA` | Firefox 123 UA | UA used in Reddit JSON API | — | — |

## Other

| Key | Default | Description | Min | Max |
|---|---|---|---|---|
| `DOWNLOAD_TIMEOUT_SECONDS` | `15` | Per-file timeout via aiohttp | 5 | 120 |
| `DOWNLOAD_SEGMENTS` | `4` | Connections (Range segments) per file ≥ 4 MB | 1 | 16 |
| `PW_GOTO_TIMEOUT_MS` | `25000` | `page.goto()` timeout (ms) | 5000 | 120000 |
| `SAFE_URL_MAX_LENGTH` | `200` | Max chars of URL in logs | 50 | 1000 |

## What is NOT customizable (system-level)

Lives in `.env`, applies to the whole process:

- **Auth/identity**: `TELEGRAM_BOT_TOKEN`, `ALLOWED_*`, `ALLOW_ALL`, `FIREFOX_PROFILE_PATH`
- **Endpoints**: `LOCAL_API_HOST`
- **Paths**: `BASE_DOWNLOAD_DIR`, `FIREFOX_PROFILE_PATH`
- **Logger**: `LOG_LEVEL`, `LOG_MAX_BYTES`, `LOG_BACKUP_COUNT`
- **Pools (boot-time)**: `YTDLP_WORKERS`, `IG_WORKERS`, `IO_WORKERS`, `PW_CONCURRENCY`
- **Global aiohttp session**: `AIOHTTP_TOTAL_TIMEOUT`, `AIOHTTP_CONNECT_TIMEOUT`, `AIOHTTP_READ_TIMEOUT`, `AIOHTTP_CONN_LIMIT`, `AIOHTTP_UA_DEFAULT`
- **Playwright (boot-time)**: `PW_VIEWPORT_*`, `PLAYWRIGHT_UA`, `PW_REFRESH_*`
- **TTL caches (boot-time)**: `TTL_RETRIES_SECONDS`, `TTL_FUTURES_SECONDS`
- **Background tasks**: `SHUTDOWN_TASKS_TIMEOUT`, `METRICS_LOG_INTERVAL_MIN`
- **Boot-parsed extensions**: `IMAGE_EXTS_EXTRA`, `VIDEO_EXTS_EXTRA`

# Troubleshooting

## Configuration errors

### `BASE_DOWNLOAD_DIR must be an absolute path`

The bot rejects relative paths at boot. Use:

- Linux/macOS: `BASE_DOWNLOAD_DIR=/mnt/storage/mediaraven`
- Windows: `BASE_DOWNLOAD_DIR=C:/mediaraven/downloads` (forward slashes, not backslashes)

### `LOCAL_API_HOST not configured in .env`

You need the local Bot API server running + `LOCAL_API_HOST=host:port` pointing to it. Details in [Configuration](getting-started/config.md#1-local-bot-api-required).

### `Token not configured`

Missing `TELEGRAM_BOT_TOKEN` in `.env`. Get the token from @BotFather.

## Bot doesn't respond

### Private chat works, but group doesn't

Authorization missing. Check:

- `ALLOWED_USER_IDS` contains your user ID (from @userinfobot)
- or `ALLOWED_CHAT_ID` contains the chat ID
- or `ALLOW_ALL=yes` (careful: public bot)

### In groups

- **Group Privacy** off in @BotFather (Bot Settings → Group Privacy → OFF)
- Bot added to group (not just the handle in chat)
- `ALLOWED_CHAT_ID` contains group ID (`-100...` for supergroups, `-...` for regular groups)

### No apparent errors

Check the log: `tail -f bot.log`. If "📥 Starting download" appears but nothing comes, it's a specific downloader issue. If even that doesn't appear, the handler wasn't fired — check whitelist.

## Downloader errors

### `Invalid file http url specified`

Local Bot API isn't reachable. Check:

- Bot API Docker container is running (`docker ps`)
- `LOCAL_API_HOST` points to the right host:port
- Port 8081 isn't in use by another process

### `ffmpeg not found`

IG posts with external music need ffmpeg to mix audio + photo. Reddit videos need it to merge DASH.

```bash
sudo apt install ffmpeg              # Linux
brew install ffmpeg                  # macOS
choco install ffmpeg                 # Windows
```

### Instagram asks for login / challenge

`Instagram web API failed` or `No Instagram session in Firefox` in the log. Possible causes:

- The Instagram session in Firefox dropped (password change, logout, account recovery)
- Account flagged for suspicious activity

Solution: open the Firefox profile at `FIREFOX_PROFILE_PATH` and log in to Instagram again. The bot reads the cookies from disk — no restart needed.

If still fails, use VPN or wait a few hours. In persistent cases, switch account — IG blocks accounts that appear doing mass downloads.

### YouTube: "Sign in to confirm you're not a bot"

YouTube is detecting as bot. Cookies from a logged-in Firefox account solve it:

```ini
FIREFOX_PROFILE_PATH=/path/firefox/profile
```

Make sure the profile has recent cookies (you opened YouTube in Firefox recently).

### YouTube: age-restricted video

Cookies from a logged-in adult account **and** a PO Token for the `mweb` client — see [YouTube → Age-restricted](platforms/youtube.md#age-restricted-po-token-bgutil).

### YouTube: private / removed / geo-blocked video

Since v1.2.9 the bot detects these yt-dlp errors and replies with a clear message (🔒/🗑️/🌍/etc.) instead of falling through to the generic scraper (which used to send the YouTube/Google logo from the error page). Full list at [YouTube → Unrecoverable error detection](platforms/youtube.md#unrecoverable-error-detection-v129).

For an actually private video there's no way — only if your Firefox account has access.

### YouTube: `.webm` video arrived as a document with no player

Pre-v1.2.5 the bot sent `webm`/`mkv`/`avi`/`flv` as video, but Telegram only renders the native player for MP4 H.264+AAC. From v1.2.5 on, video in these formats is converted to MP4 before sending (probe + minimal remux/re-encode via ffmpeg). Configurable via `VIDEO_CONVERT_TIMEOUT` (default 900s).

### Reddit: 403 Forbidden

Since 2026-10-21 Reddit's JSON API returns 403 to any anonymous client, and the bot reads the post page instead (see [Reddit](platforms/reddit.md#post-page-when-the-json-api-returns-403)). If it still fails, the page's JS challenge may have changed format — open an issue with a `LOG_LEVEL=DEBUG` log.

### Threads: "Post X not found in HTML JSON scripts"

Threads changed the SSR format. Open issue on GitHub.

## Generic scraper errors

### "No media found on the page"

Could be:

1. Page is heavy SPA (React/Angular/Vue) without SSR — Playwright should catch but might fail
2. og:image / og:video / JSON-LD absent — site without basic SEO
3. Content behind hard paywall (Substack, Patreon)
4. Content behind login

Try the screenshot prompt (default active).

### UI images being sent (avatar, logo)

`SCRAPE_MIN_IMAGE_SIZE` too low. Increase to 100-200 (if 50 isn't filtering).

### Takes too long

Check the tiers running:

```bash
grep "🕸️\|⚡\|🧩\|🖼️" bot.log | tail -20
```

If Playwright is taking 30s+, lower `PW_GOTO_TIMEOUT_MS`. If gallery-dl is slow, lower `SCRAPE_GALLERY_DL_TIMEOUT_S` or disable (`SCRAPE_GALLERY_DL_ENABLE=no`).

## Captions

### Caption didn't come

You have 5 seconds to click the prompt "📝 Description found — include as caption?". If you ignore, default is `no` (discards).

To change default: `ASK_CAPTION_DEFAULT=yes` in `customization.json`.

### Twitter caption without `@username`

URL is `/i/status/...` (anonymous) and the tweet JSON also doesn't have screen_name. Bot tries lookup but might not find. Workaround: use canonical URL `/<username>/status/<id>`.

## Performance

### Bot slow, RAM growing

Playwright leaks memory over time. The bot auto-recycles when RSS > `PW_REFRESH_RSS_MB_THRESHOLD` (default 1500MB). If still bad, lower threshold or increase `PW_REFRESH_CHECK_INTERVAL_MIN` (more frequent check).

### CPU 100%

Possible causes:

- ffmpeg processing big video (wait it out)
- yt-dlp on a giant video
- Playwright pool full

Check via `LOG_LEVEL=DEBUG` what's running.

## For deep debug

```ini
LOG_LEVEL=DEBUG
```

All modules (including `httpx`, `urllib3`, `playwright`, etc.) come back to log. Volume goes up A LOT — turn off afterwards.

## Reporting bugs

If you found a bug:

1. Reproduce with `LOG_LEVEL=DEBUG`
2. Note the exact URL that failed (obfuscate sensitive info)
3. Paste the relevant log excerpt
4. Mention version (`python -c "from version import __version__; print(__version__)"`)
5. Open issue at [github.com/LordAztur/mediaraven/issues](https://github.com/LordAztur/mediaraven/issues)

# Reddit

Reddit has **two dedicated paths**:

## 1. Reddit JSON (`reddit_json.py`)

Adds `.json?raw_json=1` to the URL and parses. Covers:

- ✅ Single image posts
- ✅ Galleries (`media_metadata` + `gallery_data`)
- ✅ Reposts from other subs
- ❌ Videos (delegates to yt-dlp because DASH needs merge)
- ❌ NSFW posts without login → falls into Playwright
- ❌ Spoilers blurred → falls into Playwright

Firefox cookies are auto-injected into the `aiohttp` session when available.

### Post page (when the JSON API returns 403)

Since **2026-10-21** the JSON API answers `403 Blocked` to anonymous clients — residential or datacenter IP, with or without cookies — and yt-dlp fails with *"Account authentication is required"*. The post page still opens, and the same `reddit_json.py` reads it instead:

1. **Browser TLS fingerprint:** the GET goes through `curl_cffi` (`impersonate="firefox"`); with `aiohttp` Reddit returns 403 even after solving the challenge.
2. **JS challenge:** the first response is a hidden form plus a `(async e=>e+e)("<seed>")` script. The bot doubles the seed and resubmits the form via GET (`solution`, `js_challenge`, `jsc_token`, `jsc_orig_r`), getting the full page.
3. **`<shreddit-post>`:** gives `post-title`, `post-type` and `content-href`:
    - image/gallery → the `i.redd.it` URLs in the post body, in order (avatars and icons are skipped)
    - video → the post's `<shreddit-player>` `src` (HLS), which the dispatcher hands straight to yt-dlp
    - text → the post body (`…-post-rtjson-content`), one paragraph per line; a text-only post comes back as a message (`downloader_status.reddit_text_only`), no media
    - crosspost → `content-href` relative to the original post (made absolute); the video is on the page itself
    - no `post-type` → uses `content-href` if it is an image
4. **App `/s/` links:** Reddit redirects with the slug encoded twice (`hist%25C3%25B3ria`) and the page can't find the post; the bot decodes it first.
5. **Deleted media:** if the image returns 404 on `i.redd.it`, the answer is `downloader_status.reddit_media_removed` (*"🗑️ This post's media was removed from Reddit."*), without going through yt-dlp.

## 2. Reddit Playwright (`reddit_playwright.py`)

When JSON fails (NSFW gate, spoilers, "no preview"), opens `old.reddit.com` in Playwright:

> ⚠️ Since Oct/2026 `old.reddit.com` sends anonymous clients to login (`reason=lor2`); this path only works with logged-in session cookies.

- ✅ Auto-clicks the NSFW button
- ✅ Removes spoiler blur (including Shadow DOM)
- ✅ Extracts media from Shadow Tree
- ❌ Videos (same reason: DASH)

## Relevant configs

| Key | Default | What it does |
|---|---|---|
| `REDDIT_JSON_UA` | Firefox 123 UA | UA used in JSON API. Reddit detects bot UAs — use a realistic one. |

## Caption

Comes from `title` + `selftext`:

```
📄 Post title
Self-text here (if any)...

🔗 Original Link
```

Username/subreddit aren't in the caption today (could be added — open an issue if you want).

## Reddit videos

URL like `v.redd.it/xxx` or post with `is_video=true` → `reddit_json` detects and **returns empty on purpose**, making the dispatcher fall into `yt-dlp`. yt-dlp downloads the DASH stream (separate video + audio) and mixes.

Video caption comes from yt-dlp's `info_dict` (title + description).

When the post came from the page (JSON API blocked), yt-dlp gets the `<shreddit-player>` HLS URL instead of the post link, and the caption uses the post title.

## NSFW

Bot can download NSFW if you have Firefox cookies from a logged-in session with NSFW enabled in Reddit preferences. Without cookies, `reddit_playwright` clicks the NSFW button automatically as fallback.

## Common failures

- **403 / "blocked"** on the JSON API → expected since 2026-10-21; the bot reads the post page (above). If the page returns 403 too, check whether the JS challenge changed format (log `reddit_json.usando_pagina_html` followed by an error).
- **"🗑️ This post's media was removed from Reddit."** → the image was deleted (404 on `i.redd.it`); nothing to download.
- **Gallery with some images missing** → API sometimes returns partial `media_metadata`. Bot uses what came.
- **`v.redd.it` returns no audio** → yt-dlp + ffmpeg should mix. If not, ffmpeg isn't in PATH or DASH failed. Enable `LOG_LEVEL=DEBUG`.

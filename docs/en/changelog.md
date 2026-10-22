# Changelog

## v1.3.3 — Reddit downloads again without the JSON API

**Root cause:** on 2026-10-21 Reddit started answering `403 Blocked` on the JSON API to any anonymous client (residential or datacenter IP, with or without cookies), and yt-dlp — including that day's build — fails with *"Account authentication is required"*. Every Reddit link failed with "🔑 Video requires login".

- 👽 **Post page instead of the API:** on a JSON 403, `reddit_json` opens the page through `curl_cffi` (Firefox TLS fingerprint), solves Reddit's JS challenge (doubles the seed and resubmits the form) and reads `<shreddit-post>`: images and galleries come from the post's `i.redd.it` URLs; videos go to yt-dlp via the `<shreddit-player>` HLS URL, with the post title as caption.
- 🔁 **Crosspost:** the `content-href` relative to the original becomes an absolute URL and the video on the page itself is used — it used to become a broken "external link".
- 🔤 **Accented titles:** the app's `/s/` link arrives with the slug encoded twice (`%25C3%25…`) and the page couldn't find the post; it is now decoded first.
- 🖼️ **Post without `post-type`:** uses `content-href` when it is an image.
- 🗑️ **Deleted media:** an image returning 404 on `i.redd.it` answers *"This post's media was removed from Reddit."* (new key `downloader_status.reddit_media_removed`) instead of "Video requires login", without spending 4 yt-dlp attempts.
- ✅ 428 tests (new: JS challenge, page with gallery/video/crosspost/no type, double-encoded slug, deleted media).

## v1.3.2 — Post titles always whole

**Root cause:** in the caption attached to the media, the title was cut with `...` — at **80 characters** on Reddit (with no author, the title moves to the header and inherited the author-name limit) and at 120 elsewhere. Reddit titles go up to 300.

- 📝 **The title is never cut:** the description gives up space in the short caption instead, and still goes out whole in the separate text when it doesn't fit.
- ✅ 425 tests (new: a 300-char Reddit title comes out whole and the caption stays ≤ 1024).

## v1.3.1 — Ignored download becomes a 🙈 reaction, no message

- 🙈 **Ignoring the download no longer sends text:** with a single link, the prompt disappears and the original message's reaction switches to `reaction_ignored` (default 🙈 — Telegram only accepts a fixed emoji list as bot reactions, no ❌). With several links in the same message, or if the chat refuses the reaction, the `status.download_ignored` text is kept.
- ✅ 424 tests (new: reaction + prompt deleted; several links keep the text; refused reaction falls back to text).

## v1.3.0 — instagrapi removed: Instagram only through the Firefox web session

**Why:** since Oct 2, 2026, instagrapi's fresh password login gets **HTTP 429** for everyone ([instagrapi #2852](https://github.com/subzeroid/instagrapi/issues/2852)), and every bot restart spent one attempt of the account's login budget. v1.2.35 already fetched the same JSON through the web API with the Firefox session; instagrapi became dead weight.

**Breaking changes:**

- 🗑️ **`IG_USER`, `IG_PASS` and `IG_SESSION_FILE` are gone** — remove them from `.env`, along with `ig_session.json`. The Instagram session is now Firefox's (`FIREFOX_PROFILE_PATH`): log in to Instagram there.
- 📦 **`instagrapi` dropped from dependencies** (and with it `pydantic`, `pycryptodomex` and `PySocks`).

**Major changes:**

- 🌐 **`downloaders/instagram.py` web API only** (`download_instagram_instagrapi` → `download_instagram_api`): shortcode → id and JSON → media object in ~30 lines, with instagrapi's same choice (highest image and video resolution). Photo + music, carousels and login-required posts work the same.
- 📖 **Stories** (`/stories/<user>/<id>/`) recognized by the web API.
- 🛡️ **A new key missing from the user's `messages.json` falls back to `messages.example.json`** instead of killing the download with `KeyError` after an update.
- 🚀 No login at startup: restarting the bot no longer makes any Instagram login attempt.
- ✅ Validated: 421 tests in a fresh venv built only from `requirements.txt` (no instagrapi leftovers); the web API call honors `HTTPS_PROXY` (with the proxy down it fails instead of egressing through the server IP).

## v1.2.35 — Instagram without Instagrapi: web API with the Firefox session (photo + music included)

**Root cause:** with Instagrapi's login down ([instagrapi #2852](https://github.com/subzeroid/instagrapi/issues/2852)), the authenticated Instagram path gave up right away ("client is not logged in"). **Photo + music** posts — which the embed deliberately hands off and yt-dlp can't download (*"No video formats found"*) — arrived silent or via the generic scraper.

**Major changes:**

- 🌐 **`media/{pk}/info` through the web API** when Instagrapi isn't logged in — using the Firefox cookies (`FIREFOX_PROFILE_PATH`). The JSON is the same as the app API's: instagrapi's own `extract_media_v1` builds the `media_info`, and the rest of the flow is unchanged (CDN download, `progressive_download_url` + `audio_asset_start_time_in_ms` / `overlap_duration_in_ms` → ffmpeg). Carousels, reels and login-required posts come along.
- 🏷️ New status `📸 Instagram Web (...)` — **if you use your own `messages.json`, add `downloader_status.instagram_web`** (a missing key raises `KeyError`).
- ✅ Validated: 415 tests; a real photo + music post became an H.264 1088×1104 + AAC `.mp4` of **exactly 90 s** (the segment picked in the post), with no Instagrapi.

## v1.2.34 — Login-required Instagram: gallery-dl with the Firefox session when Instagrapi can't log in

**Root cause:** since Oct 2, 2026, Instagrapi's fresh password login gets **HTTP 429** on credential submission (CAA flow) — a general problem with no fix yet ([instagrapi #2852](https://github.com/subzeroid/instagrapi/issues/2852)). Without an Instagrapi session, a post yt-dlp flagged as "login required" had nowhere left to go: the bot deliberately skips every other path (so it won't send the error page logo).

**Major changes:**

- 🖼️ **gallery-dl runs after Instagrapi** on Instagram authentication errors (`sign_in_required`, `age_restricted`, `unavailable`). It uses the **web session** from the Firefox cookies (`FIREFOX_PROFILE_PATH`), not the app API — so it keeps working while Instagrapi's login is down. Honors `SCRAPE_GALLERY_DL_ENABLE`.
- ⬆️ **gallery-dl `1.32.0` → `1.32.15`.**
- ⚠️ **Don't feed the browser `sessionid` to Instagrapi** (`login_by_sessionid`): Instagram rejects web sessions on the app API and may **log the browser session out** too — the very session gallery-dl relies on.
- ✅ Validated: 413 tests (new: gallery-dl resolves the post after Instagrapi fails); real post downloaded through the bot's `_gallery_dl_run` with the Firefox session.

## v1.2.33 — YTDLP_YT_CLIENTS takes effect again + age-restricted via PO Token + process-wide proxy

**Root cause (age-restricted video, logged-in and age-verified account):** the bot replied "🔞 Age-restricted". Two stacked problems:

1. **`YTDLP_YT_CLIENTS` never reached yt-dlp.** `extractor_args` was built in command-line form (`{'youtube': ['player_client=...']}`), which yt-dlp's API **silently ignores** — it always ran `default`. Nobody noticed because `default` is the default.
2. **YouTube changed in Sep/2026:** with a regular account, age-restricted videos only come through the `mweb` client **with a PO Token**; the `web*` clients pass the age check but get no formats (SABR).

**Major changes:**

- 🐛 **`extractor_args` in API form** (`{'youtube': {'player_client': [...]}}`) — `YTDLP_YT_CLIENTS` now actually applies.
- 🔑 **PO Token support** — `bgutil-ytdlp-pot-provider==2.0.1` added to dependencies; with the `bgutil` server running and `YTDLP_YT_CLIENTS=default,mweb`, age-restricted videos download. Steps in [YouTube → Age-restricted](platforms/youtube.md#age-restricted-po-token-bgutil). Without the server nothing changes.
- 🌐 **Process-wide proxy** — `aiohttp` now honors `HTTPS_PROXY`/`NO_PROXY` (`trust_env`) and Playwright's Chromium launches with the proxy (it ignores the variable). yt-dlp, gallery-dl, instagrapi and curl_cffi already honored it. Without the variables, nothing changes.
- 🧹 **Playwright blocks service workers** — logged-in x.com's `sw.js` kept a ~300–500 MB renderer alive after `page.close()`.
- ⬆️ **instagrapi `2.16.0` → `3.0.20`** — 2.16 announced an app version Instagram started rejecting on fresh logins (*"Your version of Instagram is out of date"*).
- 📌 **yt-dlp pinned to nightly `2026.09.27.232945`.**
- ✅ Validated: 412 tests; age-restricted video downloaded through the bot's own functions (`default,mweb` + bgutil 2.0.1) and a regular video in 4K.

## v1.2.32 — Instagrapi downloads straight from the CDN (a 1s timeout was killing reels) + codebase trim

**Root cause (reel `/reel/Dc6NTWNhZKu/`):** the bot replied "Video requires login", but the Instagrapi account **did have access** — it resolved the reel through the private API and only broke while downloading the file from the CDN: `ReadTimeout (read timeout=1)`. instagrapi's `video_download`/`album_download` download with the library's `request_timeout`, **1s by default**, and that same value is also the **pause before every API call** — raising it to 15s would add 30–45s to every reel. Since Instagrapi is the fallback, the failure fell through to yt-dlp's reason (`sign_in_required`) and the message was misleading.

**Major changes:**

- 📥 **Instagrapi only resolves, the bot downloads** — `media_info` still comes from the authenticated private API; files are fetched straight from the URLs (`video_url` / `thumbnail_url` / album `resources`) via `requests`, with `DOWNLOAD_TIMEOUT_SECONDS` per read. Videos and albums **no longer fetch `media_info` twice**, and the API's anti-ban pause stays at 1s.
- 📦 `requests` becomes a direct dependency (it was already installed through instagrapi).
- ♻️ **Codebase trim (no behavior change):** 6 ffmpeg/ffprobe wrappers became one `_run_proc`; the 4 Telegram callbacks and 3 yes/no prompts became one handler and one function; 3 redirect resolvers became one; `lifecycle/chat_lock.py` and `lifecycle/metrics_log.py` moved into `services.py`; `requirements.txt` went from a `pip freeze` (76 pins) to the direct dependencies; dead code removed. −343 lines.
- ✅ Validated: 412 tests; a real CDN download (1080×1920 video) in 0.1s from the server that used to time out; tests cover photo, video, and album.

## v1.2.31 — Reddit: anonymous session bypasses the JSON API 403 + crosspost support

**Two causes (link `/r/riodejaneiro/.../s/WqKj4dUF3T`):**

1. **Reddit's JSON API started blocking (403 "Blocked") requests without a session cookie.** yt-dlp's `--print-traffic` revealed the trick: it **visits Reddit first** to earn an **anonymous** session (`token_v2`, `loid`, `session_tracker`) and only then requests the `.json` — which returns 200. The bot sent the `.json` with no cookies → 403 → fell back to yt-dlp, which hit the rate limit and retried for **7 minutes** before giving up.
2. **It was a crosspost** ("a post inside a post") — the media (a 4-image gallery) lives in `crosspost_parent_list`, which the extractor ignored.

**Major changes:**

- 🪪 **Reddit anonymous session bootstrap** — before the `.json`, the bot does a GET on Reddit to obtain guest cookies (`_ensure_reddit_session`), sends `over18=1`, and on 403/429 re-bootstraps and retries once. Restores the **native extraction** (Native API/Images), no yt-dlp delegation.
- 🔁 **Crosspost support** — when a post has `crosspost_parent_list`, media is pulled from the **original** post (gallery, single image, or preview). A video original still goes to yt-dlp.
- ✅ Validated end-to-end: the link downloaded all **4 gallery images** via the Native API.

## v1.2.30 — YouTube froze the bot: impersonation now required (TLS anti-bot) + `default` client

**Root cause (hang stack trace):** every YouTube link stopped downloading and **froze the bot**. The trace showed yt-dlp stuck in `networking/_requests.py:_send` while downloading the initial webpage — YouTube began **tarpitting connections whose TLS fingerprint isn't a browser's**. yt-dlp's `requests`/urllib3 backend hung forever (not even `socket_timeout` cut it), while plain `curl` and `curl_cffi` (impersonation) fetched the page in ~1s. It wasn't the yt-dlp version or deno — it was **TLS anti-bot**.

**Major changes:**

- 🕵️ **Impersonation (curl_cffi/chrome) now in `base_opts`** — covers all three YouTube paths (language detection, pre-extract, download), which previously used the `requests` backend and hung. The bot already used impersonation, but its platform list had **left YouTube out**.
- 📺 **YouTube client: `ios,mweb,web` → `default`** — YouTube's SABR experiment was capping the `ios`/`mweb` clients at **360p** (high-res DASH formats require a PO token). yt-dlp's `default` client set delivers **1080p H.264 + audio** without any PO token/bgutil. Validated end-to-end: Rick Astley downloaded at 1920×1080.
- ⬆️ **yt-dlp updated to nightly `2026.08.20`** (improves the `default` set).

## v1.2.29 — Photo+music: cap resolution at 1280 (1930px exceeded the phone's decoder)

**Root cause (probing the real video):** the merged video was **technically perfect** — H.264 Constrained Baseline, yuv420p, faststart, AAC — but at **1448×1930** (the IG photo's native resolution). The **1930px height exceeds most phones' hardware H.264 decoder limit (~1920)**, so the app couldn't decode it → **"unable to play, use external player"**. It wasn't the codec or metadata; it was **resolution**.

**Major changes:**

- 📉 **The photo+music merge now caps the longest side at 1280px** (`scale='min(1280,iw)':'min(1280,ih)':force_original_aspect_ratio=decrease`, no upscale, even dimensions). E.g. 1448×1930 → 960×1280 — decodes on any device. It's the same "inline" cap Telegram itself uses; for a photo+music clip the difference is imperceptible.

## v1.2.28 — Pass width/height/duration when sending video (local Bot API doesn't auto-detect)

**Research:** the bot uses the **local Bot API server** (`LOCAL_API_HOST`). Unlike the cloud API, the local server **doesn't auto-detect video metadata** — `width`, `height` and `duration` must be passed explicitly on `sendVideo`/`InputMediaVideo`. Without them, the Telegram client sometimes can't build the player and shows **"App was unable to play this video. Try external player?"** — even with the right codec (H.264/AAC/yuv420p/faststart). This hit the IG photo+music and other videos.

**Major changes:**

- 📐 **`send_video` and `InputMediaVideo` now get `width`, `height`, `duration` (via `ffprobe`) + `supports_streaming`.** Applies to every sent video — single and album. New `async_ffprobe_video_meta` helper in `utils.py`.

**Added:**

- `async_ffprobe_video_meta` in `utils.py`; `_video_meta_kwargs` in `telegram_io.py`

## v1.2.27 — Codec check now runs for ALL videos (closes the .mp4 gap)

v1.2.25's `async_ensure_telegram_video` started checking the codec, but the `_ensure_video` wrapper (in `telegram_io.py`) **returned early by extension** before calling it — so an `.mp4` with **AV1/VP9/HEVC** (common on TikTok/IG via instagrapi, scraper, etc.) still went out incompatible. v1.2.25's codec check was effectively ignored for `.mp4`.

**Major changes:**

- 🔧 **`_ensure_video` now delegates straight to `async_ensure_telegram_video`** (no extension short-circuit). Now **every** sent video — single or album, from any platform — goes through `ffprobe`: if it's already H.264+AAC, it's sent as-is; if it's AV1/VP9/HEVC, it's re-encoded to H.264/AAC with faststart. This closes the gap and makes the v1.2.25 fix actually apply.

**Added:**

- Updated test in `tests/test_telegram_io_timeouts.py` (`.mp4` also goes through the codec check)

## v1.2.26 — Fix regression: IG photo+music came back as just the photo

The `-framerate 30` from v1.2.25 made the ffmpeg merge **hit the 60s timeout** (30× more frames; on a large image + loaded machine it went over 60s), so the merge failed and the bot sent **just the photo**. Adjusted:

- 🎬 **Photo+music merge: 30 fps → 15 fps** (half the frames, ~20s on a 1440×1800 image; still a normal, Telegram-compatible framerate) and **timeout 60s → 180s** (headroom for a loaded machine). Keeps H.264 + AAC + faststart. Validated end-to-end on the reported post: back to "Video with Music" (h264 15fps + aac + faststart) in ~38s.

## v1.2.25 — "Incompatible / needs external player" videos on Telegram

Telegram only plays **H.264 + AAC** inline. Videos that didn't match came through marked as incompatible. Three fronts:

**Major changes:**

- 🎬 **Instagram photo+music (ffmpeg merge) is compatible now.** The merge used **`-framerate 1`** (a 1 fps video, which Telegram's player rejects) and **had no `-movflags +faststart`** (no inline streaming). Fixed to **30 fps + faststart** (`-tune stillimage` keeps the file the same size).
- 🔎 **`async_ensure_telegram_video` now checks the codec before deciding**, not just the extension. Previously any `.mp4` passed straight through — so an `.mp4` with **AV1/VP9/HEVC** (common on YouTube/TikTok/FB) went to chat incompatible. Now it runs `ffprobe`: if it's already H.264+AAC, it's sent as-is (no re-encode); otherwise it's re-encoded to H.264/AAC with faststart.
- 🎯 **yt-dlp now prefers H.264/AAC** (`format_sort: ['vcodec:h264', 'acodec:aac']`). So most downloads already come compatible, avoiding the re-encode (faster). Confirmed: YouTube that picked `av01 @ 1440p` now picks `avc1 @ 1080p` (compatible). When only AV1/HEVC exists, the re-encode above guarantees compatibility.

**Added:**

- 4 tests in `tests/test_video_convert.py` (`.mp4` H.264 passes through; `.mp4` AV1 and HEVC get re-encoded; merge uses 30 fps + faststart)

## v1.2.24 — YouTube downloads in high quality again (yt-dlp update)

**Major changes:**

- ✅ **YouTube high quality (1080p/1440p) back.** The root cause of the 403 was simply an **outdated yt-dlp**: the latest *stable* (`2026.7.4`, from July) was ~6 weeks behind YouTube's changes, and YouTube fixes land in the **nightlies** first. Updated to the nightly `2026.8.18.122307.dev0`. Confirmed on the full bot pipeline: downloads **1440p** and **1080p**, with no extra dependency or service.

**Added:**

- yt-dlp updated to `2026.8.18.122307.dev0` (nightly) in `requirements.txt`

**Note:** YouTube is a moving target — when it breaks again, the fix comes in a **new nightly** (`pip install -U --pre yt-dlp`), not in stable. Worth checking the nightly before any other investigation.

## v1.2.23 — Reddit: external embedded-video link (YouTube) is re-dispatched again

**Major changes:**

- 🔗 **A Reddit post linking to an external video (YouTube, etc.) is handled by its destination again.** `reddit_external_link` (v1.2.19) excluded posts with `post_hint == 'rich:video'`, assuming that meant a native video — but `rich:video` is exactly an **external embedded video** (YouTube/streamable/…); Reddit's native one is `hosted:video` (v.redd.it). Because of that, a YouTube link post fell into `download_reddit_json` → yt-dlp on the Reddit URL → scraper (page images), instead of re-dispatching to YouTube. Fixed: only `hosted:video`/`is_video` (native) are excluded; `rich:video` goes through the domain check and is re-dispatched as an external link. Confirmed on the reported post (`youtu.be/d0avNDsWslg`).

**Added:**

- Test in `tests/test_reddit_common.py` (external `rich:video` becomes an external link)

## v1.2.22 — YouTube: don't dump DASH fragments when yt-dlp fails

**Context:** when yt-dlp failed on a YouTube link, the dispatcher fell into the generic scraper, which downloaded the **chopped DASH fragments** (dozens of `.mp4`s) and sent them all to chat.

**Major changes:**

- 🚫 **When yt-dlp fails on a YouTube link, the generic scraper is skipped** (`_run_platform_fallbacks` returns early for `platform.youtube`). The scraper never yields a usable YouTube video — only fragments — so it now fails cleanly (with a retry button) instead of dumping 27–53 chopped files.

**Added:**

- Log key `dispatcher.youtube_skip_scraper` (PT/EN)
- Test in `tests/test_dispatcher_integration.py` (a YouTube yt-dlp failure does not call `scrape_fallback`)

## v1.2.21 — Optional proxy for TikTok (TIKTOK_PROXY)

**Major changes:**

- 🌐 **New `TIKTOK_PROXY` config** — routes **only** TikTok's yt-dlp requests through a proxy (TikTok blocks server/VPN IPs with a WAF). Applied in `_apply_format_selection` only when `platform.tiktok` and the env is set; impersonation (chrome) and logged-in cookies stay the same. Accepts `http://` and `socks5://`. Inert when empty — no behavior change without configuring. Typical use: a gluetun container with `HTTPPROXY=on` → `TIKTOK_PROXY=http://127.0.0.1:8888`.

**Added:**

- `TIKTOK_PROXY` constant in `config.py`; wiring in `downloaders/_ytdlp.py`
- Docs in `.env_example`/`.en`
- 3 tests in `tests/test_ytdlp_format_selection.py` (proxy set for TikTok only when configured; ignored when empty; ignored for other platforms)

**Note:** TikTok blocks many VPN IP ranges (ProtonVPN included). Setting the proxy doesn't guarantee a bypass — you may need to switch the VPN exit country until you find an accepted IP.

## v1.2.20 — A Reddit link post always re-dispatches the external link (news included)

**Major changes:**

- 🔗 **Adjusts the v1.2.19 behavior:** now **every** external link from a Reddit post is downloaded **as if the link itself had been sent** — not just "known targets". Previously a news link became a card with just thumbnail + title; now it re-dispatches `download_media` on the news link, which goes through the normal flow (yt-dlp → scraper/article extraction). Practical result: a link post to an article comes with the **article image + title + news body** (via Scraper Deep Search / trafilatura), same as sending the news link directly to the bot.
- 🖼️ **The thumbnail card (thumb + title + link) is now a fallback:** used only if the re-dispatch returns **nothing** (no files and no caption), so the user is never left without a reply.
- Removed `_is_known_media_target` (the known-target-vs-news distinction is no longer needed).

**Validated end-to-end:** post `r/Maromba/...fisiculturista...` → resolves to `folha.uol.com.br` → yt-dlp "Unsupported URL" → scraper returns the article image + the news body as caption.

## v1.2.19 — Reddit link posts: news card or re-dispatch of a known target

**Major changes:**

- 🔗 **A Reddit post that is just an external link is now handled by its destination, not by a stray thumbnail.** Previously a link post (e.g. a news article) fell into `download_reddit_json`, which downloaded the preview image and sent it with the Reddit title/link. Now the dispatcher, before downloading, resolves the post's external link (`resolve_reddit_external_link`, using the same Reddit JSON — reused so it isn't fetched twice) and decides:
  - **Known mediaraven target** (YouTube, Instagram, TikTok, X, Facebook, Threads, Kwai): **re-dispatches** `download_media` on the inner link — downloads the media as if that link had been sent directly (with a depth guard against loops).
  - **News / generic site link**: sends a **card** with the post's **thumbnail** + **title** + **link to the news** (not the Reddit link). The caption is included by default (treated as an article).
- Reddit-native media (images, galleries, videos, self-posts) follows exactly the previous flow — only external links change behavior.

**Added:**

- Pure helper `reddit_external_link(post_data)` in `downloaders/reddit_common.py` (classifies external link vs native media)
- `resolve_reddit_external_link(url)` in `downloaders/reddit_json.py` (returns `(link, post_data)`, reusing the fetch); `download_reddit_json` accepts pre-fetched `post_data`
- `_is_known_media_target(url)` and `_reddit_news_card(...)` in the dispatcher; `download_media` gained a `_depth` recursion guard
- `downloader_status.reddit_link_card` message (PT/EN) and 3 dispatcher log keys
- 10 tests (8 for `reddit_external_link` in `tests/test_reddit_common.py`, 2 integration: known-target re-dispatch and news card)

## v1.2.18 — TikTok: yt-dlp updated + logged-in cookies first with impersonation

**Context:** TikTok started blocking the server's IP with a WAF/captcha. yt-dlp 2026.6.9 didn't even attempt TikTok's new challenge (deterministic "Unexpected response from webpage request" failure), and the scraper fallback only grabbed a 2s preview (not the real video). An IP block can't be fully solved in code, but a logged-in session maximizes the odds.

**Major changes:**

- ⬆️ **yt-dlp `2026.6.9` → `2026.7.4`.** The new version solves TikTok's WAF challenge (native-Python proof-of-work) — 2026.6.9 lacked that support and always failed.
- 🍪 **TikTok is now a recognized platform and prioritizes the logged-in session.** Added `tiktok` to `Platform`/`_PLATFORM_HOSTS` (`tiktok.com`, `vt.tiktok.com`, `vm.tiktok.com`). For TikTok, `_attempt_order` tries **`with_cookie` first** (before `no_cookie`), and `_apply_format_selection` applies **impersonation (curl_cffi chrome)** — a logged-in session + browser fingerprint is the best combo to get past the WAF. Only 2 attempts (both impersonated, cookie-first) to avoid tripping rate limits.

**⚠️ Required action:** for this to work you must be **logged into TikTok in the Firefox profile** the bot uses (`FIREFOX_PROFILE_PATH`). The bot injects those cookies; without a valid logged-in session the WAF keeps blocking.

**Added:**

- 7 tests in `tests/test_ytdlp_format_selection.py` (TikTok host detection, cookie-first `_attempt_order`, impersonation applied)

## v1.2.17 — Threads `/share/` links download again

**Major changes:**

- 🧵 **Threads share links (`threads.com/share/XXXX`) download again.** The new share format doesn't expose the post code in the URL, so `_extract_post_code` (regex `/post/(...)`) failed and the bot bailed with "couldn't extract post code from URL" before even loading the page. The `/share/` link does no HTTP redirect (it returns 200 and redirects via JS), but Playwright — which Threads already uses — follows the redirect: after loading, `page.url` becomes the canonical URL (`/@user/post/CODE`). **Fix:** `_fetch_html` now also returns the final URL, and the new `_resolve_post_code` obtains the code in order url → final URL (post-redirect) → `og:url` from the HTML. Normal `/@user/post/CODE` links keep working the same. Validated end-to-end: a real `/share/` resolves to `Db0CFC1jJmq` and extracts the video.

**Added:**

- `_resolve_post_code` and `_OG_URL_RE` in `downloaders/threads.py`; `_fetch_html` returns `(html, final_url)`
- 4 `_resolve_post_code` tests in `tests/test_threads.py` (direct url, post-share final URL, `og:url` fallback, unresolvable)

## v1.2.16 — Detect ongoing live and cancel the download

**Major changes:**

- 🔴 **Ongoing live streams are now detected and the download is cancelled.** The bot already ran a pre-extract (`extract_info(download=False)`) before downloading; leveraging that, the new `_live_reason(info)` (`downloaders/_ytdlp.py`) reads yt-dlp's `live_status`/`is_live`: `is_live`/`live_status=="is_live"` → `live_in_progress` (cancel); `live_status=="is_upcoming"` → `live_not_started` (also blocks scheduled lives); `was_live`/`post_live`/`not_live` → proceeds normally (a finished live's VOD stays downloadable). As soon as the live is identified, `_run_ytdlp_with_cookie_fallback` returns the reason **before attempting the download** — the actual download never starts. The dispatcher already handles `unrecoverable_reason`, so it shows the message and skips fallbacks. Rationale: downloading an ongoing live hangs/wastes resources and never completes.
- 💬 New status message `🔴 Live in progress. Download cancelled.` (PT/EN) and log `🔴 Live detected (...); cancelling download.`

**Added:**

- 10 test cases for `_live_reason` + an async test proving the download (`_yt_dlp_extract`) is never called when a live is detected, in `tests/test_ytdlp_format_selection.py`

## v1.2.15 — Single-photo Instagram posts failed (Instagrapi re-fetched via the blocked public GraphQL)

**Major changes:**

- 📸 **Single-photo Instagram posts download again.** The bot already fetched `media_info` via the authenticated private API (`i.instagram.com/api/v1/media/{pk}/info/`, works), but for a single photo (`media_type == 1`) it called `photo_download(media_pk)`, which internally **re-fetches the metadata via the public GraphQL** (`media_info_gql`). Instagram locked that public endpoint down: it now returns `401 Unauthorized`, instagrapi returns `None`, and the download blew up with `AttributeError: 'NoneType' object has no attribute 'get'`. Practical result: the user sent a photo and got an error/"login required" or the embed cover, even while the account was logged in. Videos and albums were never affected because `video_download`/`album_download` use the private API (`media_info_v1`/`media_info`), not the public GraphQL — only the single-photo path used `media_info_gql`.
- 🔧 **Fix:** single photos now download via `photo_download_by_url(media_info.thumbnail_url)`, reusing the `media_info` we already have from the private API — the re-fetch via the blocked public GraphQL is eliminated. Validated live against the failing post: downloads the real image (1311×1452 JPEG) instead of an error.

**Added:**

- `tests/test_instagram_instagrapi.py` — regression test ensuring single photos use `photo_download_by_url` and never `photo_download(media_pk)`

## v1.2.14 — Instagram Reels came through as images (embed cover) + yt-dlp/instagrapi update

**Major changes:**

- 📸 **Instagram Reels come through as video again.** The embed endpoint (`/embed/captioned/`) started returning, for many reels, `is_video=true` but **no `video_url`** (only the cover in `display_url`/`display_resources`, `product_type=clips`). In `_media_from_node` (`downloaders/instagram_embed.py`), since `is_video` was true but `video_url` was empty, the code **fell through to the image branch and returned the cover** — the embed treated that as success and the dispatcher returned the image without ever trying yt-dlp/Instagrapi (which fetch the video). Fixed: a node marked as video never degrades to its cover — it returns empty, the embed fails, and the fallback takes over. Confirmed: reels that came as `IG Embed (Image/Album)` are now downloaded as video by yt-dlp.
- ⬆️ **yt-dlp `2026.3.17` → `2026.6.9` and instagrapi `2.3.0` → `2.16.0`.** The two libraries driving IG/FB extraction were stale (instagrapi 13 versions behind). Validated: clean `pip check`, yt-dlp extracts real reels, and every instagrapi method the bot uses (`media_pk_from_url`, `media_info`, `photo_download`, `video_download`, `album_download`, `login`, `dump_settings`, `load_settings`) exists in 2.16.0. Pillow `11.3.0` → `12.2.0` and requests `2.32.5` → `2.34.2` were bumped as transitive deps of instagrapi.

**Added:**

- Regression test in `tests/test_instagram_embed.py` (a video node without `video_url` does not fall back to the cover)

## v1.2.13 — Facebook Reels failed due to long filename (ENAMETOOLONG)

**Major changes:**

- 🐦 **Facebook Reels (and any long-title video) download correctly again.** yt-dlp's `outtmpl` used `%(title)s [%(id)s].%(ext)s`; FB Reels carry the entire caption (300+ chars) as the title, and even with `restrictfilenames` yt-dlp doesn't cap the length, so the filename blew past the filesystem's 255-byte limit and the download died with `[Errno 36] File name too long`. Since `base_opts` has `ignoreerrors=True`, the error was swallowed silently: no file, no exception — all 4 yt-dlp attempts "failed", it fell through to the generic scraper, which returned UI thumbnails (40x40/10x10) as `🕸️ Scraper Deep Search (Images)`. Practical result: user sent a Reel and got random images instead of the video. Fixed by truncating the title to `%(title).150B` (150 bytes) — the `[id].ext` suffix keeps the final name around 170 bytes, comfortably under 255. Applies to all platforms. yt-dlp extraction always worked (AV1 formats available); only the output filename broke.

**Added:**

- 2 tests in `tests/test_ytdlp_format_selection.py` (outtmpl contains the truncation; a 600-char title yields a name ≤ 255 bytes via `YoutubeDL.prepare_filename`, preserving `[id].ext`)

## v1.2.12 — Silently ignore domains (IGNORED_DOMAINS)

**Major changes:**

- 🔇 **New `IGNORED_DOMAINS` config to ignore domains with no chat feedback at all.** Links from listed domains are skipped: no reaction (emoji), no download prompt, no status message — they're only recorded in `bot.log` (`handlers.dominio_ignorado`). The filter runs in `_extract_urls_from_update` (in `handlers.py`), right after dedup and **before** the `MAX_URLS_PER_MESSAGE` limit, so ignored domains don't consume the URL quota. If every URL in the message is ignored, `handle_message` returns early and not even the reaction is set.
- ⚙️ **Configurable globally or per chat/user.** Globally via `.env` (`IGNORED_DOMAINS=twitch.tv,spotify.com`) or per chat/user via `customization.json` (`"IGNORED_DOMAINS": ["twitch.tv"]`), following the usual user > chat > default > .env precedence.
- 🌐 **Exact-domain and subdomain matching.** New pure function `is_ignored_domain` in `utils.py` compares via `hostname` (case-insensitive, port-agnostic): `example.com` also ignores `www.example.com`/`m.example.com`, while `example.com.evil.com` does not match.

**Added:**

- `IGNORED_DOMAINS` constant in `config.py` (CSV from `.env`)
- `is_ignored_domain` function in `utils.py`
- Log key `handlers.dominio_ignorado` (PT/EN)
- Docs for the `IGNORED_DOMAINS` field in `customization.example.json`/`.en.json` and `.env_example`/`.en`
- 6 `is_ignored_domain` tests in `tests/test_utils_helpers.py` and 4 filtering tests in `tests/test_url_extraction.py`

## v1.2.11 — X returned a reply's video on an image post + Instagram tries authenticated Instagrapi on login errors

**Major changes:**

- 🐦 **X: an image post returned a video from a reply in the same thread.** Triple root cause in `downloaders/x.py`: (1) `_tweet_ids` included `conversation_id_str`, which is shared by ALL replies in the conversation — so any reply "matched" the target tweet ID inside the GraphQL `TweetDetail` response; (2) `_extract_from_data` only read `tweet["extended_entities"]`, but in GraphQL the focal tweet's media lives under `tweet["legacy"]["extended_entities"]`, so it came up empty and fell into a fragile fallback; (3) `_walk_for_tweet_media` had a permissive guard `if not ids or tweet_id in ids` that grabbed media from the first matching object (a reply with a video) or any object with no IDs at all. Fix: identity is now only `id_str`/`rest_id`/`id` (no `conversation_id_str`), extraction also reads `legacy.extended_entities`, and the walk requires a strict ID match. Confirmed by logs: the reported link went empty guest → authenticated Playwright → reply video.
- 🔑 **Instagram: a yt-dlp login error no longer gives up without trying the authenticated session.** When yt-dlp reports `sign_in_required`/`age_restricted`/`unavailable` for Instagram (sensitive/age-restricted content), the dispatcher now tries `download_instagram_instagrapi` (logged-in session from `ig_session.json`) before giving up, instead of aborting on the `unrecoverable_reason` short-circuit. The generic scraper stays skipped in these cases (preserves the short-circuit's original purpose: not picking up the error-page logo). Genuinely unrecoverable reasons (`private`/`removed`/etc.) still abort immediately.

**Added:**

- `_IG_AUTH_RETRY_REASONS = {"sign_in_required", "age_restricted", "unavailable"}` constant in `downloaders/dispatcher.py`
- Log key `dispatcher.unrecoverable_try_instagrapi` (PT/EN)
- 2 regression tests in `tests/test_x.py` (focal photo + reply with video in the same conversation → extracts the photo; walk ignores a reply in the same conversation)
- 3 tests in `tests/test_dispatcher_integration.py` (IG `sign_in_required` → tries Instagrapi and succeeds; empty Instagrapi → gives up without scraper; IG `private` → does not try Instagrapi)

## v1.2.10 — Dedicated Facebook handler (carousels via gallery-dl) + yt-dlp uploader validation + unified attempt order + broader classifier coverage

**Major changes:**

- 📘 **New dedicated Facebook handler in `downloaders/facebook.py`**. For any FB link, the dispatcher now tries `gallery-dl` first (with Firefox cookies) — gallery-dl extracts image carousels correctly via SSR API, avoiding timeline scraping. If gallery-dl finds files → uses it directly with status `📘 Facebook Gallery [N files]`. Otherwise falls through to the normal flow (yt-dlp for video). Confirmed: a 20-image carousel post that returned the wrong video now comes complete (~250KB each).
- 🛡️ **`facebook_owner_mismatch` validation after yt-dlp success on FB.** Facebook extractor in yt-dlp has a bug: when the original post is image-only, it "finds" any embedded video on the page (sponsored/recommendation/comment) and returns it as "success". Practical result: user sends a carousel link and receives a random video from another user. Now: we compare `uploader_id` returned by yt-dlp against the numeric user_id from the URL (`facebook.com/<UID>/posts/...`). On mismatch, we discard the result and continue to fallbacks.
- 🍪 **`_gallery_dl_run` now injects Firefox cookies** (via `gdl_config.set(('extractor',), 'cookies', ('firefox', profile))`). Needed for FB; no side effects on other platforms (Pinterest/Imgur already worked without auth).
- 🖼️ **Facebook image carousels download even without login.** The `_drop_facebook_image_only` heuristic (introduced in v1.0.x to avoid 50+ UI thumbnails when user sent video links) was too aggressive: it discarded ANY FB post without `.mp4` as "UI junk", which included legit photo/carousel posts. **Function removed.** Replaced by expanding `is_junk_url` with known FB/Reddit UI hosts/paths (`static.xx.fbcdn.net`, `static.cdninstagram.com`, `styles.redditmedia.com`, `alb.reddit.com`, `id.rlcdn.com`, `/rsrc.php/`, `/safe_image.php`, `headshot`, `snoovatar`, `_profile`, `communityicon`, `profileicon`, `awardicon`) — UI is now filtered at the source (before download) and real post images pass through.
- 🔁 **`_expand_attempts_with_impersonate` now applies the "no_imp first, imp as fallback" pattern to Facebook/Instagram too** (previously Reddit-only). For FB/IG/Reddit: 4 attempts `[no_cookie+no_imp, with_cookie+no_imp, no_cookie+imp, with_cookie+imp]`. For YouTube/others (don't use impersonate): 2 attempts as before. Why: manual tests with Facebook showed that `impersonate=chrome` makes FB return a heavy SPA that yt-dlp can't parse (`"Cannot parse data"`), while without impersonate it returns a semantic error (`"No video formats found"`) that the classifier can recognize and respond to correctly.
- 🛑 **Facebook with "This video is only available for registered users" wasn't being classified by v1.2.9** — fell through to the scraper and the heuristic discarded everything. Added patterns: `only available for registered users`, `only available for registered`, `only available to registered`, `use --cookies`, `requires login`, `please log in`. Other new patterns: `this account is private` → `private`, `restricted to subscribers` → `members_only`, `this content isn't available`/`this tweet is unavailable`/`no video formats found`/`no media found`/`cannot parse data` → `unavailable`, `this video is no longer available` → `removed`, `too many requests` → `rate_limited`.

**Removed:**

- `_drop_facebook_image_only` function in `downloaders/fallback.py` (and 4 call sites)
- Log key `fallback.facebook_image_only_dropped` (PT/EN)

**Added:**

- New module `downloaders/facebook.py` with `download_facebook_gallery` and `facebook_owner_mismatch`
- UI message `downloader_status.facebook_gallery` (PT/EN) and 2 log keys `facebook.tentando_gallery_dl`, `facebook.gallery_dl_ok`, `dispatcher.facebook_owner_mismatch`
- 5 tests in `tests/test_facebook.py` (mismatch detection: no info / match / mismatch / share URL / no uploader_id)
- 4 tests in `tests/test_ytdlp_format_selection.py` (registered users / use --cookies / 429 / private account)
- `test_expand_attempts_facebook_and_instagram_also_try_no_imp_first` in `tests/test_ytdlp_format_selection.py`
- 3 tests in `tests/test_scrape_helpers.py` covering new junk patterns (FB static, Reddit UI, real FB post image)

## v1.2.9 — Detect unrecoverable yt-dlp errors (private/removed/geo/etc.) and skip fallbacks

**Major changes:**

- 🛑 **Private/removed/geo-blocked/etc. videos now return a clear message** instead of falling through to the generic scraper (which was picking up the YouTube/Google logo from the error page as if it were the media). Before: private video link → yt-dlp fails → scraper scrapes page → sends Google logo to chat. Now: yt-dlp captures the error, classifies it as `private`/`removed`/`geo_blocked`/`members_only`/`age_restricted`/`sign_in_required`/`live_not_started`/`unavailable`/`rate_limited`, and the dispatcher stops immediately with a specific message.
- 🪵 **yt-dlp error capture via `logger=` opts** instead of fiddling with `ignoreerrors`. Each extraction call now returns `(info, error_messages)` when `capture_errors=True`. The classifier matches against 21 known patterns (case-insensitive) and returns the category.

**Refactors:**

- `_yt_dlp_extract` takes `capture_errors: bool = False`; when True returns `(info, errors)` tuple instead of just `info`
- New helper `_classify_ytdlp_errors(error_messages) -> Optional[str]` in `downloaders/_ytdlp.py` with patterns for: `private`, `members_only`, `age_restricted`, `geo_blocked`, `removed`, `live_not_started`, `unavailable`, `sign_in_required`, `rate_limited`
- `_run_ytdlp_with_cookie_fallback` now returns `(files, info, unrecoverable_reason)`. Instead of just listing files, it accumulates errors from all attempts and classifies at the end
- `dispatcher.download_media` checks `unrecoverable_reason` before calling fallbacks; if set, returns `msg("downloader_status.ytdlp_{reason}")` directly

**Added:**

- 9 UI messages (PT/EN) under `downloader_status.ytdlp_{private,unavailable,removed,geo_blocked,members_only,age_restricted,sign_in_required,live_not_started,rate_limited}`
- 2 log keys: `_ytdlp.unrecoverable_reason`, `dispatcher.unrecoverable_skip_fallbacks`
- 9 tests in `tests/test_ytdlp_format_selection.py` (classifier per category + None fallback) + 1 integration test in `tests/test_dispatcher_integration.py`

## v1.2.8 — Threads: extract media from `linked_inline_media` (media_type=19 posts)

**Major changes:**

- 🧵 **Threads posts with `media_type=19` (audio-augmented / new format) had media in `text_post_app_info.linked_inline_media`**, a field `_extract_media` didn't cover. The post has `video_versions` at root level as falsy/empty and `image_versions2.candidates: []`, so the bot fell into the "no media, caption only" branch and replied with text. Now `_extract_media` recurses into `linked_inline_media` (same structure: `carousel_media`/`video_versions`/`image_versions2`) before the `share_info.quoted_post` fallback. Direct media still takes precedence.

**Added:**

- 3 tests in `tests/test_threads.py` (`linked_inline_media` with video, with image, direct-media precedence)

## v1.2.7 — AIORateLimiter actually retries now (max_retries=3)

**Major changes:**

- 🐛 **In v1.2.4 the `AIORateLimiter` was added, but with `max_retries=0` (default).** Result: on flood control (`Retry in N seconds`), the limiter only logged `Rate limit hit after maximum of 0 retries` and re-raised `RetryAfter`, making the original request fail and the handler blow up — exactly the symptom v1.2.4 tried to fix. The status_msg got stuck on "downloading" because `_safe_edit` to "internal_error" hit the same flood. Now `AIORateLimiter(max_retries=3)`: the limiter waits for `Retry-After` from Telegram and retries up to 3 times automatically.

## v1.2.6 — Reddit: try without impersonate first (fixes IP-block)

**Major changes:**

- 🐛 **Reddit was returning `Your IP address is unable to access the Reddit API` when yt-dlp was called with `impersonate=ImpersonateTarget('chrome')`** (enabled for Reddit in v1.0.x). Result: `bestvideo+bestaudio/best` failed on any video post, and the bot fell through to the generic scraper which grabbed avatars/community icons instead of the video. Now, for Reddit, attempts are expanded to `[no_cookie+no_imp, with_cookie+no_imp, no_cookie+imp, with_cookie+imp]` — impersonate becomes a fallback instead of default. Facebook/Instagram unchanged (always impersonate).
- 🧪 Manually verified: without impersonate, yt-dlp downloads Reddit video normally (~5 MB in 2s); with impersonate, returns IP-block.

**Refactors:**

- `_apply_format_selection` got `use_impersonate: bool = True` parameter in `downloaders/_ytdlp.py` — when False, does `opts.pop('impersonate', None)` (just gating the add isn't enough since the dispatcher injects impersonate into `base_opts` before the loop, and `current_opts.copy()` inherits it)
- New helper `_expand_attempts_with_impersonate(attempts, platform)` — for Reddit returns `[(m, False) for m in attempts] + [(m, True) for m in attempts]`; for others keeps `[(m, True) for m in attempts]`
- Main loop in `_run_ytdlp_with_cookie_fallback` now iterates `(mode, use_imp)`, calls `_apply_format_selection` on every iteration (not only when pre-extract info is present — otherwise the gating is skipped), and skips `_pre_extract` for Reddit (Reddit uses `format='bestvideo+bestaudio/best'` directly)
- Attempt log includes `_imp`/`_noimp` suffix in `mode` for diagnostics

**Added:**

- 6 tests in `tests/test_ytdlp_format_selection.py` (impersonate gating + pop when inherited + expand_attempts)

## v1.2.5 — Automatic video conversion to MP4 when needed

**Major changes:**

- 🎞️ **Videos in formats not supported by Telegram's native player are converted to MP4 before sending.** Telegram only guarantees a streaming player for MP4 H.264+AAC ([Bot API docs](https://core.telegram.org/bots/api#sendvideo): "other formats may be sent as Document"). Previously, `.webm`/`.mkv`/`.avi`/`.flv` would land as documents with no player; now they become MP4 before `send_video`.
- 🧠 **Smart strategy (probe + minimal remux/re-encode)**: `ffprobe` detects vcodec/acodec. If already H.264 → `-c:v copy` (instant, lossless). If AAC → `-c:a copy`. Otherwise, re-encode only the incompatible stream. If remux fails (codec doesn't fit MP4 container), auto-fallback to full re-encode.
- ✅ Compatible extensions (`.mp4`/`.m4v`/`.mov`) pass through with no ffprobe/ffmpeg call.

**Added:**

- `state.FFPROBE_PATH` + `init_ffmpeg` now discovers both `ffmpeg` and `ffprobe` in PATH in `lifecycle/startup.py`
- `is_telegram_compatible_video_ext`, `async_ffprobe_codecs`, `async_ensure_telegram_video` in `utils.py`
- `_ensure_video` helper in `telegram_io.py` (single-file and media_group)
- Config `VIDEO_CONVERT_TIMEOUT` (default 900s) in `config.py` + `customization.example.{json,en.json}`
- 13 new log keys (PT/EN): `startup.ffprobe_*`, `utils.ffprobe_*`, `utils.video_convert_*`
- 11 tests in `tests/test_video_convert.py` + 4 tests in `tests/test_telegram_io_timeouts.py`

## v1.2.4 — Rate limiter to prevent Flood control exceeded

**Major changes:**

- 🚦 **`AIORateLimiter` enabled** in `ApplicationBuilder`. Previously, when Telegram returned `RetryAfter: Flood control exceeded. Retry in N seconds` (on `edit_text`/`send_*`), the exception bubbled up without retry and the user's request failed. Now PTB respects `Retry-After` on all requests automatically — waits N+ε and retries, without propagating errors to the handler.

**Added:**

- `builder.rate_limiter(AIORateLimiter())` in `mediaraven.py`
- `python-telegram-bot[rate-limiter]==22.7` in `requirements.txt` (pulls `aiolimiter` as a transitive dependency)

## v1.2.3 — GIFs sent as animation (not buggy video)

**Major changes:**

- 🎞️ **GIFs now go through `send_animation`** instead of `send_video`. Telegram was treating GIFs as videos (no autoplay, no loop, ugly player). With `send_animation`, they become native animations.
- 🎞️ **GIFs are converted to MP4 (H.264) via ffmpeg before sending**. Telegram converts raw GIFs with quality loss and renders them small; silent MP4 is Telegram's native "animated GIF" format (the same one the official client uses) — much better quality and full size.
- 📐 Dimensions (`width`/`height`) extracted from the original GIF via PIL and passed to `send_animation` — ensures correct rendering even when ffmpeg is unavailable.

**Added:**

- `_ANIMATION_EXTS_DEFAULT = ('.gif',)` in `config.py` (extensible via env `ANIMATION_EXTS_EXTRA`); `.gif` removed from `VIDEO_EXTS_DEFAULT`
- `async_gif_to_mp4(input_path, output_path, timeout=60)` in `utils.py` (ffmpeg `-c:v libx264 -pix_fmt yuv420p -an -movflags +faststart`)
- Helper `_get_image_dims` + `send_animation` branch in `telegram_io.py` (with fallback to original `.gif` if ffmpeg fails)
- 6 log keys `utils.gif_to_mp4_*` in PT/EN
- 3 tests in `tests/test_telegram_io_timeouts.py` (gif→animation route, successful conversion, fallback on ffmpeg failure)

## v1.2.2 — Dynamic cap for HLS / finished YouTube lives

**Major changes:**

- 📺 **Finished YouTube live now fits**: ended lives (`live_status: post_live`) only expose HLS formats without `filesize_approx` declared. Previously the selector fell back to `best` and picked 1094p (~3.8 GB for 1h53min) → `File_parts_invalid` on upload. Now, **pre-extract** discovers `duration` + formats and:
    - Applies a **dynamic bitrate cap** `[tbr<=N]` computed as `(TELEGRAM_MAX_UPLOAD_MB × 8 × 1024) ÷ duration_s × 0.95`. For a 1h53min live with 2 GB cap → `tbr<=2289 kbps`.
    - Detects **HLS-only** (all video-bearing formats are `m3u8_native`/`http_dash_segments`) and applies a conservative height cap via the new config `YTDLP_HLS_MAX_HEIGHT` (default 720).
- 🎯 **Tiered format selector**: 1) DASH with filesize cap → 2) progressive with filesize cap → 3) progressive with tbr cap → 4) plain fallback. Ensures normal VODs still pick the best quality within the limit.

**Refactors:**

- Helpers extracted in `downloaders/_ytdlp.py`: `_calc_max_tbr_kbps`, `_is_hls_only`, `_build_format_selector`, `_pre_extract`.
- `_apply_format_selection` accepts `info: Optional[dict]` and adjusts the selector dynamically.
- `_run_ytdlp_with_cookie_fallback` accepts an optional `platform`; when passed, runs a pre-extract per attempt (cookie/no-cookie) and re-applies format selection with the real info.

**Added:**

- Config `YTDLP_HLS_MAX_HEIGHT` (default 720) in `customization.example.{json,en.json}`
- 3 new log keys: `_ytdlp.hls_only_height_cap`, `_ytdlp.tbr_cap`, `_ytdlp.pre_extract_falhou`
- 15 tests in `tests/test_ytdlp_format_selection.py`

## v1.2.1 — Upload size cap to prevent File_parts_invalid

**Major changes:**

- 📤 **Size cap in yt-dlp**: new config `TELEGRAM_MAX_UPLOAD_MB` (default 2000) applied as `[filesize_approx<...M]` in the format selector. Previously, long YouTube videos in 1440p60 could exceed 2 GB and fail with `BadRequest: File_parts_invalid` on upload (Telegram's hard limit for bots; **Premium does not affect bots** — [tdlib/telegram-bot-api#583](https://github.com/tdlib/telegram-bot-api/issues/583)). The selector now reserves ~100 MB for audio + container and falls back to 1080p when 1440p would exceed the cap.
- 📤 **PTB local_mode**: `telegram_io.send_downloaded_media` now passes the **path as a string** instead of a file handle. With `telegram-bot-api --local`, PTB sends a `file:///path` URI and the server reads from the filesystem directly, with no multipart upload — avoids timeouts on large but in-limit files. Confirmed by `parse_file_input` (telegram/_utils/files.py:145-149).
- 📚 **Doc corrected**: README/site/`.env_example` mentioned "4 GB with Premium" — false. Bots cannot be Premium; the limit is always 2 GB.

**Refactors:**

- `telegram_io.py` applies `TELEGRAM_UPLOAD_TIMEOUT` to `read_timeout`/`write_timeout`/`connect_timeout` in the single-file path (previously only media_group applied it).
- `_apply_format_selection` in `downloaders/_ytdlp.py` and `download_with_ytdlp_generic` in `downloaders/fallback.py` now build the selector with a filesize cap.

**Added:**

- Config `TELEGRAM_MAX_UPLOAD_MB` in `customization.example.json` + `.example.en.json` (default 2000, min 50, max 2000)
- 5 tests in `tests/test_telegram_io_timeouts.py`

## v1.2.0 — Pinterest, Kwai and chunked captions

**Major changes:**

- 📌 **Pinterest**: pin links (`pin.it/XXX`, `pinterest.com/pin/<id>`, regional like `br.pinterest.com`) now download only the pin media via `og:image`/`og:video`/JSON-LD filter with cap=1. Previously they pulled 60+ recommended images from the page.
- 🎬 **Kwai / SnackVideo**: shortlinks (`kwai-video.com/p/XXX`, `s.kw.ai`, `snackvideo.com/in`) resolved before yt-dlp; tracking query string stripped to avoid `File name too long` from the ID generated by the generic extractor. Hosts covered: `kwai-video.com`, `kwai.com`, `m.kwai.com`, `kw.ai`, `s.kw.ai`, `snackvideo.com`, `snackvideo.in`.
- ✂️ **Long captions in chunks**: captions over 1024 chars are no longer truncated. The media goes without caption and the full text is sent in chunks of up to 4096 chars (preferred separators: `\n\n` > `\n` > `". "` > `" "`). Captions that fit in 1024 are still attached to the media as before. No text duplication.
- 📰 **Article media filtering**: when an article is detected by trafilatura, only `og:image`/`og:video`/JSON-LD are considered (cap=1), instead of all scraped images. Previously banners, ads, related articles came along.

**Refactors:**

- `_build_caption` now returns a `(short, full)` tuple propagated through every downloader (Threads, X, Reddit, Instagram, Instagram Embed, fallback). `short` ≤ 1024, `full` not truncated.
- New helper `chunk_html_text(text, limit)` in `utils.py` splits text preserving semantic boundaries (paragraph > line > sentence > word).
- `_send_text_in_chunks` in `handlers.py` sends chunks sequentially with configurable delay.

**Added:**

- `_is_pinterest()` in `downloaders/fallback.py`
- `_is_kwai_host()` + `_resolve_kwai_url()` in `downloaders/_platform.py`
- 4 new log keys: `fallback.pinterest_media_filtered`, `_platform.resolvendo_kwai`, `_platform.kwai_resolvido`, `_platform.falha_ao_resolver_kwai`
- 16 new tests: `tests/test_fallback_pinterest.py` (7), `tests/test_kwai_resolver.py` (9)
- 6 new tests for `chunk_html_text` in `tests/test_utils_helpers.py`

## v1.1.0 — Granular customization + article extraction + paywall bypass

**Major changes:**

- 🎚️ **42 customizable configs per chat and per user** via `customization.json`. Precedence `user > chat > default > .env`. Includes timeouts, prompt defaults, quality, scraper, caption, platforms. Helper `cfg(key)` + ContextVar `request_context` allow transparent lookup without propagating IDs.
- 🌐 **180+ customizable log strings** via `log_messages.json` (separate from UI messages). Helper `lmsg(key, **kw)` with graceful fallback for missing keys.
- 🔒 **Soft paywall bypass** (Googlebot UA + archive.ph) toggleable via `SCRAPE_PAYWALL_BYPASS=yes`. Covers NYT, Folha, FT, Estadão, etc.
- 📰 **Article extraction via trafilatura** as caption. Auto-detects on any URL with >= 300 chars of text. Dedicated opt-in prompt (`ASK_ARTICLE_*`).
- 📝 **Text-only posts** (Threads, X) become formatted text messages (`📄 @user` + body + link), instead of "fail".
- 🌍 **Bilingual PT/EN documentation** + docs site with MkDocs Material.
- 🛡️ **`ALLOW_ALL`** env to run as public bot (whitelist ignored).

**Refactors:**

- `_build_caption` redesigned to have separate `uploader` + `title`. YT Shorts detected (no title duplication in body). Threads/X now use `@username` in header.
- Generic scraper parallelizes HTTP fast path + Playwright deep scrape (`asyncio.gather`).
- Logs with line numbers (`%(name)s:%(lineno)d`) + noisy libs silenced (httpx, urllib3, playwright, etc.).
- `exc_info=True` in ~10 fatal exception catches — stack traces preserved in log.
- Removed `MIN_CONTENT_LENGTH_BYTES` (20KB filter was nuking legit avatars).

**Added:**

- `version.py` (`__version__ = "1.1.0"`)
- `customization.example.json` + `.example.en.json` (PT/EN, with inline `_doc_KEY`)
- `log_messages.example.json` + `.example.en.json`
- `messages.example.en.json`
- `.env_example.en`
- `README.en.md`
- `gallery-dl` as scraper tier 3
- `trafilatura` as dependency (article extraction)
- 5 additional README badges (gallery-dl, trafilatura, instagrapi, curl-cffi, ffmpeg)

**Removed:**

- Envs `PROMPT_*_OFF_CHATS / ON_USERS / OFF_USERS` (replaced by `PROMPT_*_ENABLED` in `customization.json`)
- 25+ envs moved to `customization.json` (all ASK_*, SCRAPE_*, MEDIA_GROUP_*, etc.)

## v1.0.0 — Initial release

- Telegram bot with local Bot API
- Platforms: YouTube, Instagram, Reddit, Threads, X, Facebook
- Generic cascading scraper (HTTP + yt-dlp generic + gallery-dl + Playwright)
- 100% customizable messages via `messages.json`
- Per-chat and per-user whitelist
- ~80 tuning envs

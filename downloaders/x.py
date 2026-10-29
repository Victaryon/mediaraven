import asyncio
import html
import json
import logging
import os
import re
from typing import Any, Optional
from urllib.parse import urlparse

from curl_cffi import requests as curl_requests

import state
from config import cfg
from messages import lmsg, msg
from utils import async_download_file, normalize_image, safe_url

from ._caption import _build_caption as _build_std_caption

logger = logging.getLogger(__name__)


_TWEET_ID_RE = re.compile(r"/(?:i/status|status)/(\d+)")
_INITIAL_STATE_RE = re.compile(r"window\.__INITIAL_STATE__=(\{.*?\});window\.", re.DOTALL)
_X_HOST_REPLACE = ("fxtwitter.com", "vxtwitter.com", "twitter.com", "fixupx.com", "mobile.twitter.com")
_TCO_TRAIL_RE = re.compile(r"\s*https?://t\.co/\S+\s*$")
_SCREEN_NAME_URL_RE = re.compile(r"^https?://[^/]+/(?!i/)([A-Za-z0-9_]+)/status/")


def _normalize_x_url(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    bare = host[4:] if host.startswith("www.") else host
    if bare in _X_HOST_REPLACE:
        return url.replace(parsed.netloc, "x.com", 1)
    return url


def _extract_tweet_id(url: str) -> Optional[str]:
    m = _TWEET_ID_RE.search(url)
    return m.group(1) if m else None


def _media_from_extended_entities(media_list: list) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for m in media_list or []:
        kind = m.get("type")
        if kind == "photo":
            base = m.get("media_url_https")
            if base:
                base = html.unescape(base)
                sep = "&" if "?" in base else "?"
                out.append(("image", f"{base}{sep}name=orig"))
        elif kind in ("video", "animated_gif"):
            variants = ((m.get("video_info") or {}).get("variants")) or []
            mp4s = [v for v in variants if (v.get("content_type") or "").startswith("video/mp4")]
            if not mp4s:
                continue
            best = max(mp4s, key=lambda v: v.get("bitrate") or 0)
            url = best.get("url")
            if url:
                out.append(("video", html.unescape(url)))
    return out


def _tweet_ids(obj: dict) -> list[str]:
    ids: list[str] = []
    for k in ("id_str", "rest_id", "id"):
        v = obj.get(k)
        if v is not None:
            ids.append(str(v))
    legacy = obj.get("legacy")
    if isinstance(legacy, dict):
        v = legacy.get("id_str")
        if v is not None:
            ids.append(str(v))
    return ids


def _walk_dicts(obj):
    """Emite todo dict aninhado em obj, em pré-ordem."""
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk_dicts(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_dicts(v)


def _walk_for_tweet_media(obj, tweet_id: str):
    for node in _walk_dicts(obj):
        ext = node.get("extended_entities")
        if isinstance(ext, dict):
            media = ext.get("media")
            if isinstance(media, list) and media and tweet_id in _tweet_ids(node):
                yield media


def _walk_for_tweet_obj(obj, tweet_id: str):
    for node in _walk_dicts(obj):
        if tweet_id in _tweet_ids(node):
            yield node
        legacy = node.get("legacy")
        if isinstance(legacy, dict) and tweet_id in _tweet_ids(legacy):
            yield legacy


def _find_in_initial_state(data: dict, tweet_id: str) -> Optional[dict]:
    tweets = ((data.get("entities") or {}).get("tweets") or {}).get("entities") or {}
    return tweets.get(tweet_id)


def _resolve_user_dict(data: dict, tweet: dict) -> Optional[dict]:
    user_field = tweet.get("user")
    if isinstance(user_field, dict):
        return user_field
    if not isinstance(user_field, str):
        return None
    users = ((data.get("entities") or {}).get("users") or {}).get("entities") or {}
    found = users.get(user_field)
    return found if isinstance(found, dict) else None


def _extract_tweet_text(tweet: Optional[dict]) -> str:
    if not isinstance(tweet, dict):
        return ""
    legacy = tweet.get("legacy")
    src = legacy if isinstance(legacy, dict) and (legacy.get("full_text") or legacy.get("text")) else tweet
    text = src.get("full_text") or src.get("text") or ""
    if not text:
        return ""
    drange = src.get("display_text_range")
    if isinstance(drange, list) and len(drange) == 2:
        try:
            text = text[drange[0]:drange[1]]
        except Exception as e:
            logger.debug(lmsg("x.display_text_range", e=e))
    text = _TCO_TRAIL_RE.sub("", text).strip()
    text = html.unescape(text)
    return text


def _get_screen_name(tweet: Optional[dict], url: str) -> str:
    if isinstance(tweet, dict):
        user = tweet.get("user")
        if isinstance(user, dict):
            sn = user.get("screen_name") or ""
            if sn:
                return sn
        core = tweet.get("core")
        if isinstance(core, dict):
            ur = (((core.get("user_results") or {}).get("result") or {}).get("legacy") or {})
            sn = ur.get("screen_name") or ""
            if sn:
                return sn
    m = _SCREEN_NAME_URL_RE.match(url)
    return m.group(1) if m else ""


def _build_caption(tweet: Optional[dict], url: str) -> tuple[str, str]:
    text = _extract_tweet_text(tweet)
    sn = _get_screen_name(tweet, url)
    uploader = f"@{sn}" if sn else ""
    return _build_std_caption({'uploader': uploader, 'description': text}, url)


async def _fetch_guest_html(url: str) -> Optional[str]:
    loop = asyncio.get_running_loop()
    try:
        r = await loop.run_in_executor(
            state.IO_POOL,
            lambda: curl_requests.get(url, impersonate="chrome", timeout=15, allow_redirects=True),
        )
    except Exception as e:
        logger.warning(lmsg("x.curl_cffi_falhou", e=e))
        return None
    if r.status_code != 200:
        logger.debug(lmsg("x.x_guest_http", arg0=r.status_code, arg1=safe_url(url)))
        return None
    return r.text


def _parse_initial_state(html_text: str) -> Optional[dict]:
    m = _INITIAL_STATE_RE.search(html_text)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def _extract_from_data(data: dict, tweet_id: str) -> tuple[list[tuple[str, str]], Optional[dict]]:
    tweet = _find_in_initial_state(data, tweet_id)
    if not tweet:
        for t in _walk_for_tweet_obj(data, tweet_id):
            tweet = t
            break
    if tweet:
        user_dict = _resolve_user_dict(data, tweet)
        if user_dict and not isinstance(tweet.get("user"), dict):
            tweet = {**tweet, "user": user_dict}
    media_items: list[tuple[str, str]] = []
    if tweet:
        ext = tweet.get("extended_entities") or (tweet.get("legacy") or {}).get("extended_entities") or {}
        media_list = ext.get("media") or []
        media_items = _media_from_extended_entities(media_list)
    if not media_items:
        for media in _walk_for_tweet_media(data, tweet_id):
            media_items = _media_from_extended_entities(media)
            if media_items:
                break
    return media_items, tweet


async def _try_guest(url: str, tweet_id: str) -> tuple[list[tuple[str, str]], Optional[dict]]:
    html_text = await _fetch_guest_html(url)
    if not html_text:
        return [], None
    data = _parse_initial_state(html_text)
    if not data:
        return [], None
    return _extract_from_data(data, tweet_id)


async def _try_authenticated(url: str, tweet_id: str) -> tuple[list[tuple[str, str]], Optional[dict]]:
    if not state.PW_BROWSER or not state.PW_CONTEXT:
        return [], None
    captured: list[Any] = []

    async with state.PW_SEMAPHORE:
        page = await state.PW_CONTEXT.new_page()

        async def on_response(resp):
            try:
                if "/i/api/graphql/" not in resp.url:
                    return
                data = await resp.json()
                captured.append(data)
            except Exception as e:
                logger.debug(lmsg("x.x_graphql_parse", e=e))

        page.on("response", on_response)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=cfg("PW_GOTO_TIMEOUT_MS"))
            await page.wait_for_timeout(3500)
            content = await page.content()
        except Exception as e:
            logger.warning(lmsg("x.playwright_erro_carregando", arg0=safe_url(url), e=e))
            content = ""
        finally:
            try:
                await page.close()
            except Exception:
                pass

    tweet_obj: Optional[dict] = None
    for data in captured:
        items, tweet = _extract_from_data(data, tweet_id)
        if tweet and not tweet_obj:
            tweet_obj = tweet
        if items:
            return items, tweet_obj or tweet

    if content:
        data = _parse_initial_state(content)
        if data:
            items, tweet = _extract_from_data(data, tweet_id)
            if tweet and not tweet_obj:
                tweet_obj = tweet
            if items:
                return items, tweet_obj or tweet

    return [], tweet_obj


async def download_x(url: str, unique_folder: str) -> tuple[list[str], str, str, str]:
    logger.info(lmsg("x.iniciando_extra_o_para", arg0=safe_url(url)))

    os.makedirs(unique_folder, exist_ok=True)

    url = _normalize_x_url(url)
    tweet_id = _extract_tweet_id(url)
    if not tweet_id:
        logger.warning(lmsg("x.n_o_consegui_extrair", arg0=safe_url(url)))
        return [], msg("downloader_status.x_fail"), "", ""

    media_items, tweet_obj = await _try_guest(url, tweet_id)
    if not media_items:
        logger.info(lmsg("x.tweet_x_guest", tweet_id=tweet_id))
        auth_items, auth_tweet = await _try_authenticated(url, tweet_id)
        media_items = auth_items
        if auth_tweet:
            tweet_obj = auth_tweet

    if not media_items:
        if tweet_obj:
            text_short, text_full = _build_caption(tweet_obj, url)
        else:
            text_short, text_full = "", ""
        if text_short and _extract_tweet_text(tweet_obj):
            logger.info(lmsg("x.tweet_x_sem", tweet_id=tweet_id))
            return [], msg("downloader_status.x_text_only"), text_short, text_full
        logger.warning(lmsg("x.nenhuma_m_dia_encontrada", tweet_id=tweet_id))
        return [], msg("downloader_status.x_fail"), "", ""

    downloaded: list[str] = []
    for idx, (kind, m_url) in enumerate(media_items):
        ext = ".mp4" if kind == "video" else ".jpg"
        filepath = os.path.join(unique_folder, f"x_{idx}{ext}")
        try:
            ok = await async_download_file(m_url, filepath)
        except Exception as e:
            logger.error(lmsg("x.erro_ao_baixar", e=e))
            continue
        if not ok:
            continue
        if kind == "image":
            normalized = await asyncio.to_thread(normalize_image, filepath, min_size=100)
            if normalized is None:
                continue
            downloaded.append(normalized)
        else:
            downloaded.append(filepath)

    if not downloaded:
        logger.warning(lmsg(
            "x.downloads_all_failed",
            tweet_id=tweet_id, n=len(media_items),
        ))
        return [], msg("downloader_status.x_fail"), "", ""

    has_video = any(f.endswith(".mp4") for f in downloaded)
    label = msg("media_type_labels.x_video") if has_video else msg("media_type_labels.x_album")
    caption_short, caption_full = _build_caption(tweet_obj, url)
    return downloaded, msg("downloader_status.x", media_type=label, count=len(downloaded)), caption_short, caption_full

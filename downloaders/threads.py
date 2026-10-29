import asyncio
import json
import logging
import os
import re
from typing import Optional

import state
from config import cfg
from messages import lmsg, msg
from utils import async_download_file, normalize_image, safe_url

from ._caption import _build_caption

logger = logging.getLogger(__name__)


_POST_CODE_RE = re.compile(r"/post/([^/?#]+)")
_SCRIPT_RE = re.compile(r"<script[^>]*>(.*?)</script>", re.DOTALL)
_OG_URL_RE = re.compile(r'<meta[^>]+property="og:url"[^>]+content="([^"]+)"')


def _extract_post_code(url: str) -> Optional[str]:
    m = _POST_CODE_RE.search(url or "")
    return m.group(1) if m else None


def _resolve_post_code(url: str, final_url: Optional[str], html: Optional[str]) -> Optional[str]:
    code = _extract_post_code(url)
    if code:
        return code
    code = _extract_post_code(final_url or "")
    if code:
        return code
    m = _OG_URL_RE.search(html or "")
    return _extract_post_code(m.group(1)) if m else None


def _find_post_by_code(obj, code):
    if isinstance(obj, dict):
        if obj.get("code") == code and "media_type" in obj:
            return obj
        for v in obj.values():
            found = _find_post_by_code(v, code)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _find_post_by_code(v, code)
            if found is not None:
                return found
    return None


def _best_image_url(image_versions2: dict) -> Optional[str]:
    cands = image_versions2.get("candidates") or []
    if not cands:
        return None
    best = max(cands, key=lambda c: c.get("width") or 0)
    return best.get("url")


def _best_video_url(video_versions: list) -> Optional[str]:
    if not video_versions:
        return None
    best = max(video_versions, key=lambda v: v.get("width") or 0)
    return best.get("url")


def _build_threads_caption(post: dict, url: str) -> tuple[str, str]:
    if not isinstance(post, dict):
        return "", ""
    text = ((post.get("caption") or {}).get("text") or "").strip()
    if not text:
        return "", ""
    user = post.get("user") or {}
    username = (user.get("username") or "").strip()
    uploader = f"@{username}" if username else ""
    return _build_caption({'uploader': uploader, 'description': text}, url)


def _extract_media(post: dict) -> list[tuple[str, str]]:
    if not isinstance(post, dict):
        return []

    cm = post.get("carousel_media")
    if isinstance(cm, list) and cm:
        out: list[tuple[str, str]] = []
        for item in cm:
            out.extend(_extract_media(item))
        if out:
            return out

    vv = post.get("video_versions")
    if isinstance(vv, list) and vv:
        url = _best_video_url(vv)
        if url:
            return [("video", url)]

    iv = post.get("image_versions2")
    if isinstance(iv, dict):
        url = _best_image_url(iv)
        if url:
            return [("image", url)]

    tpai = post.get("text_post_app_info") or {}
    linked = tpai.get("linked_inline_media")
    if isinstance(linked, dict):
        linked_media = _extract_media(linked)
        if linked_media:
            return linked_media

    share_info = tpai.get("share_info") or {}
    quoted = share_info.get("quoted_attachment_post") or share_info.get("quoted_post")
    if isinstance(quoted, dict):
        return _extract_media(quoted)

    return []


def _parse_post_from_html(html: str, code: str) -> Optional[dict]:
    for match in _SCRIPT_RE.finditer(html):
        script = match.group(1)
        if code not in script:
            continue
        try:
            data = json.loads(script)
        except json.JSONDecodeError:
            continue
        post = _find_post_by_code(data, code)
        if post is not None:
            return post
    return None


async def _fetch_html(url: str) -> tuple[Optional[str], Optional[str]]:
    if not state.PW_CONTEXT:
        return None, None
    async with state.PW_SEMAPHORE:
        page = await state.PW_CONTEXT.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=cfg("PW_GOTO_TIMEOUT_MS"))
            await page.wait_for_timeout(2000)
            return await page.content(), page.url
        except Exception as e:
            logger.warning(lmsg("threads.playwright_erro_carregando", arg0=safe_url(url), e=e))
            return None, None
        finally:
            try:
                await page.close()
            except Exception:
                pass


async def download_threads(url: str, unique_folder: str) -> tuple[list[str], str, str, str]:
    logger.info(lmsg("threads.iniciando_extra_o_via", arg0=safe_url(url)))

    os.makedirs(unique_folder, exist_ok=True)

    if not state.PW_BROWSER or not state.PW_CONTEXT:
        return [], msg("downloader_status.playwright_not_running"), "", ""

    html, final_url = await _fetch_html(url)
    if not html:
        return [], msg("downloader_status.threads_playwright_fail"), "", ""

    code = _resolve_post_code(url, final_url, html)
    if not code:
        logger.warning(lmsg("threads.n_o_consegui_extrair", arg0=safe_url(url)))
        return [], msg("downloader_status.threads_playwright_fail"), "", ""

    post = _parse_post_from_html(html, code)
    if post is None:
        logger.warning(lmsg("threads.post_x_n_o", code=code))
        return [], msg("downloader_status.threads_playwright_fail"), "", ""

    caption_short, caption_full = _build_threads_caption(post, url)
    media_items = _extract_media(post)
    if not media_items:
        if caption_short:
            logger.info(lmsg("threads.post_x_sem", code=code))
            return [], msg("downloader_status.threads_text_only"), caption_short, caption_full
        logger.warning(lmsg(
            "threads.no_media_found",
            code=code, media_type=post.get('media_type'),
        ))
        return [], msg("downloader_status.threads_playwright_fail"), "", ""

    downloaded_files: list[str] = []
    for idx, (kind, m_url) in enumerate(media_items):
        ext = ".mp4" if kind == "video" else ".jpg"
        filepath = os.path.join(unique_folder, f"threads_{idx}{ext}")
        try:
            success = await async_download_file(m_url, filepath)
        except Exception as e:
            logger.error(lmsg("threads.erro_ao_baixar", e=e))
            continue
        if not success:
            continue
        if kind == "image":
            normalized = await asyncio.to_thread(normalize_image, filepath, min_size=cfg("THREADS_MIN_IMAGE_SIZE"))
            if normalized is None:
                continue
            downloaded_files.append(normalized)
        else:
            downloaded_files.append(filepath)

    if downloaded_files:
        has_video = any(f.endswith(".mp4") for f in downloaded_files)
        media_type = msg("media_type_labels.threads_video") if has_video else msg("media_type_labels.threads_album")
        return downloaded_files, msg("downloader_status.threads_playwright", media_type=media_type), caption_short, caption_full

    return [], msg("downloader_status.threads_playwright_fail"), caption_short, caption_full

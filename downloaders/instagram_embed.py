import asyncio
import json
import logging
import os
import re
from typing import Optional

from curl_cffi import requests as curl_requests

import state

from messages import lmsg, msg
from utils import async_download_file, normalize_image, safe_url

from ._caption import _build_caption
from config import cfg

logger = logging.getLogger(__name__)


_SHORTCODE_RE = re.compile(r"/(?:p|reel|tv|reels)/([^/?#]+)")


def _extract_shortcode(url: str) -> Optional[str]:
    m = _SHORTCODE_RE.search(url)
    return m.group(1) if m else None


def _parse_context_json(html_text: str) -> Optional[dict]:
    idx = html_text.find('"contextJSON":"')
    if idx < 0:
        return None
    start = idx + len('"contextJSON":"')
    end = start
    while end < len(html_text):
        if html_text[end] == "\\":
            end += 2
            continue
        if html_text[end] == '"':
            break
        end += 1
    raw = html_text[start:end]
    try:
        decoded = json.loads('"' + raw + '"')
        return json.loads(decoded)
    except (json.JSONDecodeError, ValueError) as e:
        logger.debug(lmsg("instagram_embed.contextjson_parse_falhou", e=e))
        return None


def _best_image_url(node: dict) -> Optional[str]:
    drs = node.get("display_resources") or []
    if drs:
        best = max(drs, key=lambda r: r.get("config_width") or 0)
        url = best.get("src")
        if url:
            return url
    return node.get("display_url") or None


def _media_from_node(node: dict) -> list[tuple[str, str]]:
    if not isinstance(node, dict):
        return []
    sidecar = node.get("edge_sidecar_to_children")
    if isinstance(sidecar, dict):
        edges = sidecar.get("edges") or []
        out: list[tuple[str, str]] = []
        for edge in edges:
            child = edge.get("node") or {}
            out.extend(_media_from_node(child))
        if out:
            return out
    if node.get("is_video"):
        url = node.get("video_url")
        return [("video", url)] if url else []
    img = _best_image_url(node)
    if img:
        return [("image", img)]
    return []


def _extract_caption(media: dict) -> str:
    edges = ((media.get("edge_media_to_caption") or {}).get("edges")) or []
    if edges:
        return edges[0].get("node", {}).get("text", "") or ""
    return ""


def _find_shortcode_media(data: dict) -> Optional[dict]:
    media = (data.get("gql_data") or {}).get("shortcode_media")
    if isinstance(media, dict):
        return media
    media = (data.get("context") or {}).get("media")
    if isinstance(media, dict):
        return media
    return None


def _has_unembedded_music(media: dict) -> bool:
    if not isinstance(media, dict):
        return False
    if media.get("is_video"):
        return False
    cmai = media.get("clips_music_attribution_info")
    return isinstance(cmai, dict) and bool(cmai)


async def _fetch_embed_html(shortcode: str) -> Optional[str]:
    url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"
    loop = asyncio.get_running_loop()
    try:
        r = await loop.run_in_executor(
            state.IO_POOL,
            lambda: curl_requests.get(url, impersonate="chrome", timeout=15, allow_redirects=True),
        )
    except Exception as e:
        logger.warning(lmsg("instagram_embed.curl_cffi_falhou", e=e))
        return None
    if r.status_code != 200:
        logger.debug(lmsg("instagram_embed.ig_embed_http", arg0=r.status_code))
        return None
    return r.text


async def download_instagram_embed(url: str, unique_folder: str) -> tuple[list[str], str, str, str]:
    logger.info(lmsg("instagram_embed.tentando_ig_embed", arg0=safe_url(url)))

    os.makedirs(unique_folder, exist_ok=True)

    shortcode = _extract_shortcode(url)
    if not shortcode:
        logger.debug(lmsg("instagram_embed.n_o_consegui_extrair", arg0=safe_url(url)))
        return [], msg("downloader_status.instagram_embed_fail"), "", ""

    html_text = await _fetch_embed_html(shortcode)
    if not html_text:
        return [], msg("downloader_status.instagram_embed_fail"), "", ""

    data = _parse_context_json(html_text)
    if not data:
        return [], msg("downloader_status.instagram_embed_fail"), "", ""

    media = _find_shortcode_media(data)
    if not media:
        logger.debug(lmsg("instagram_embed.ig_embed_sem", shortcode=shortcode))
        return [], msg("downloader_status.instagram_embed_fail"), "", ""

    if _has_unembedded_music(media):
        logger.info(lmsg("instagram_embed.ig_embed_post", shortcode=shortcode))
        return [], msg("downloader_status.instagram_embed_fail"), "", ""

    items = _media_from_node(media)
    if not items:
        logger.debug(lmsg("instagram_embed.ig_embed_sem_2", shortcode=shortcode))
        return [], msg("downloader_status.instagram_embed_fail"), "", ""

    downloaded: list[str] = []
    for idx, (kind, m_url) in enumerate(items):
        ext = ".mp4" if kind == "video" else ".jpg"
        filepath = os.path.join(unique_folder, f"ig_embed_{idx}{ext}")
        try:
            ok = await async_download_file(m_url, filepath)
        except Exception as e:
            logger.error(lmsg("instagram_embed.erro_ao_baixar", e=e))
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
            "instagram_embed.downloads_all_failed",
            n=len(items), shortcode=shortcode,
        ))
        return [], msg("downloader_status.instagram_embed_fail"), "", ""

    raw_caption = _extract_caption(media)
    if raw_caption and len(raw_caption) > cfg("IG_CAPTION_MAX"):
        raw_caption = raw_caption[:cfg("IG_CAPTION_MAX")] + "..."
    username = ((media.get("owner") or {}).get("username")) or ""
    info_for_caption = {
        "uploader": f"@{username}" if username else "",
        "description": raw_caption,
    }
    caption_short, caption_full = _build_caption(info_for_caption, url)

    has_video = any(f.endswith(".mp4") for f in downloaded)
    label = msg("media_type_labels.ig_video") if has_video else msg("media_type_labels.ig_album")
    return downloaded, msg("downloader_status.instagram_embed", media_type=label), caption_short, caption_full

import asyncio
import logging
import os
import re
from types import SimpleNamespace
from urllib.parse import urlparse

import aiofiles
import requests
from curl_cffi import requests as curl_requests

import state
from config import cfg
from cookies import get_aiohttp_cookies_for_url
from messages import lmsg, msg
from utils import async_merge_audio_image, safe_url

from .instagram_embed import _extract_shortcode

logger = logging.getLogger(__name__)

_WEB_APP_ID = "936619743392459"
_SHORTCODE_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
_STORY_RE = re.compile(r"/stories/[^/?#]+/(\d+)")


def _shortcode_to_pk(shortcode: str) -> str:
    # Base64 do Instagram; códigos de post privado são mais longos e só os 11 primeiros contam.
    pk = 0
    for ch in shortcode[:11]:
        pk = pk * 64 + _SHORTCODE_ALPHABET.index(ch)
    return str(pk)


def _media_pk_from_url(url: str):
    if m := _STORY_RE.search(url):
        return m.group(1), None
    if shortcode := _extract_shortcode(url):
        return _shortcode_to_pk(shortcode), shortcode
    return None, None


def _best_url(versions) -> str | None:
    versions = [v for v in versions or [] if v.get("url")]
    return max(versions, key=lambda v: (v.get("width") or 0) * (v.get("height") or 0))["url"] if versions else None


def _resource_from_v1(item: dict) -> SimpleNamespace:
    # Mesma escolha do instagrapi: maior resolução de vídeo e de imagem.
    return SimpleNamespace(
        media_type=item.get("media_type"),
        video_url=_best_url(item.get("video_versions")),
        thumbnail_url=_best_url((item.get("image_versions2") or {}).get("candidates")),
    )


def _media_from_v1(item: dict) -> SimpleNamespace:
    media = _resource_from_v1(item)
    media.resources = [_resource_from_v1(c) for c in item.get("carousel_media") or []]
    media.caption_text = (item.get("caption") or {}).get("text", "") or ""
    return media


def _web_media_info(url: str, timeout: float):
    """media/{pk}/info pela API web com a sessão do Firefox (FIREFOX_PROFILE_PATH).

    É o mesmo JSON que a API do app devolvia ao instagrapi, removido na v1.3.0 (o login
    por senha leva 429 desde out/2026); a sessão web é a mesma do yt-dlp e do gallery-dl."""
    media_pk, shortcode = _media_pk_from_url(url)
    cookies = get_aiohttp_cookies_for_url("https://www.instagram.com/")
    if not media_pk or "sessionid" not in cookies:
        return None
    r = curl_requests.get(
        f"https://www.instagram.com/api/v1/media/{media_pk}/info/",
        cookies=cookies, impersonate="chrome", timeout=timeout,
        headers={
            "X-IG-App-ID": _WEB_APP_ID,
            "X-CSRFToken": cookies.get("csrftoken", ""),
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"https://www.instagram.com/p/{shortcode}/" if shortcode else "https://www.instagram.com/",
        },
    )
    r.raise_for_status()
    items = (r.json() or {}).get("items") or []
    if not items:
        return None
    return _media_from_v1(items[0]), {"items": items}


async def download_instagram_api(url: str, unique_folder: str) -> tuple[list[str], str, str, str]:
    logger.info(lmsg("instagram.iniciando_instagrapi_para", arg0=safe_url(url)))
    os.makedirs(unique_folder, exist_ok=True)

    timeout = cfg("DOWNLOAD_TIMEOUT_SECONDS")

    def fetch(media_url: str, path: str) -> str:
        with requests.get(media_url, stream=True, timeout=timeout) as r:
            r.raise_for_status()
            with open(path, 'wb') as f:
                for chunk in r.iter_content(64 * 1024):
                    f.write(chunk)
        return path

    def perform_api():
        try:
            web = _web_media_info(url, timeout)
            if not web:
                logger.error(lmsg("instagram.cliente_instagrapi_n_o"))
                return None
            media_info, raw_data = web

            audio_url = None
            start_time_sec = None
            overlap_duration_sec = None
            track_duration_sec = None
            duration_sec = 15.0

            resource_count = len(getattr(media_info, 'resources', []) or [])
            is_single_photo = (
                media_info.media_type == 1
                or (media_info.media_type == 8 and resource_count <= 1)
            )
            if is_single_photo:
                try:
                    logger.info(lmsg("instagram.buscando_udio_e"))

                    def extract_audio_data(data):
                        nonlocal audio_url, start_time_sec, overlap_duration_sec, track_duration_sec
                        if isinstance(data, dict):
                            if data.get('progressive_download_url') and not audio_url:
                                audio_url = data['progressive_download_url']
                            if 'audio_asset_start_time_in_ms' in data and start_time_sec is None:
                                start_time_sec = data.get('audio_asset_start_time_in_ms', 0) / 1000.0
                            if 'overlap_duration_in_ms' in data and overlap_duration_sec is None:
                                overlap_duration_sec = data.get('overlap_duration_in_ms', 0) / 1000.0
                            if 'duration_in_ms' in data and track_duration_sec is None:
                                track_duration_sec = data.get('duration_in_ms', 0) / 1000.0
                            for k, v in data.items(): extract_audio_data(v)
                        elif isinstance(data, list):
                            for item in data: extract_audio_data(item)

                    extract_audio_data(raw_data)

                    if overlap_duration_sec and overlap_duration_sec > 0:
                        duration_sec = overlap_duration_sec
                    elif track_duration_sec and track_duration_sec > 0:
                        duration_sec = min(track_duration_sec, 90.0)
                    else:
                        duration_sec = 30.0

                except Exception as e:
                    logger.warning(lmsg("instagram.erro_ao_buscar", e=e))

            resources = media_info.resources if media_info.media_type == 8 else [media_info]
            paths = []
            for i, res in enumerate(resources):
                media_url = res.video_url if res.media_type == 2 else res.thumbnail_url
                if not media_url:
                    continue
                media_url = str(media_url)
                ext = os.path.splitext(urlparse(media_url).path)[1] or ('.mp4' if res.media_type == 2 else '.jpg')
                paths.append(fetch(media_url, os.path.join(unique_folder, f"ig_{i}{ext}")))

            caption_text = getattr(media_info, 'caption_text', "") or ""
            return paths, audio_url, duration_sec, start_time_sec, media_info.media_type, caption_text, is_single_photo
        except Exception as e:
            logger.error(lmsg("instagram.instagrapi_falhou_x", e=e), exc_info=True)
            return None

    queue_size = state.ig_pending_inc()
    if queue_size >= cfg("IG_QUEUE_WARN_THRESHOLD"):
        logger.warning(lmsg("instagram.fila_do_instagrapi", queue_size=queue_size, IG_QUEUE_WARN_THRESHOLD=cfg("IG_QUEUE_WARN_THRESHOLD")))

    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(state.IG_POOL, perform_api)
    finally:
        state.ig_pending_dec()

    if not result:
        return [], msg("downloader_status.instagrapi_fail"), "", ""

    paths, audio_url, duration_sec, start_time_sec, media_type, caption_text, is_single_photo = result

    audio_path = None
    if audio_url:
        try:
            logger.info(lmsg("instagram.baixando_udio_puro"))
            a_path = os.path.join(unique_folder, "temp_audio.m4a")
            headers_ig = {'User-Agent': cfg("IG_USER_AGENT")}
            async with state.AIOHTTP_SESSION.get(audio_url, headers=headers_ig, timeout=15) as r:
                if r.status == 200:
                    async with aiofiles.open(a_path, 'wb') as f:
                        async for chunk in r.content.iter_chunked(8192):
                            await f.write(chunk)
                    audio_path = a_path
        except Exception as e:
            logger.error(lmsg("instagram.erro_ao_baixar", e=e), exc_info=True)

    if is_single_photo and audio_path and os.path.exists(audio_path):
        logger.info(lmsg("instagram.transformando_foto_em"))
        merged_paths = []
        for img_path in paths:
            if img_path.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                video_output = img_path.rsplit('.', 1)[0] + '_video.mp4'

                if await async_merge_audio_image(img_path, audio_path, video_output, start_time_sec, duration_sec):
                    merged_paths.append(video_output)
                    try:
                        os.remove(img_path)
                    except OSError as e:
                        logger.debug(lmsg("instagram.falha_ao_remover", img_path=img_path, e=e))
                else:
                    merged_paths.append(img_path)
            else:
                merged_paths.append(img_path)

        paths = merged_paths
        try:
            os.remove(audio_path)
        except OSError as e:
            logger.debug(lmsg("instagram.falha_ao_remover_2", audio_path=audio_path, e=e))

    has_video = any(f.endswith('.mp4') for f in paths)
    if has_video and audio_path:
        m_type = msg("media_type_labels.ig_video_music")
    elif has_video:
        m_type = msg("media_type_labels.ig_video")
    else:
        m_type = msg("media_type_labels.ig_album")

    caption_full = caption_text
    if caption_text and len(caption_text) > cfg("IG_CAPTION_MAX"):
        caption_short = caption_text[:cfg("IG_CAPTION_MAX")] + "..."
    else:
        caption_short = caption_text

    return paths, msg("downloader_status.instagram_web", media_type=m_type), caption_short, caption_full

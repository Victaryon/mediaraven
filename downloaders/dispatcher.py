"""Orquestrador de download. Os helpers específicos vivem em submódulos
(_platform, _ytdlp, _languages, _caption).
"""
import asyncio
import logging
import os
import time
from typing import Optional

import metrics
import state
from config import FIREFOX_PROFILE_PATH
from utils import async_download_file, normalize_image, safe_url

from messages import lmsg, msg

from ._caption import _build_caption
from ._languages import _detect_youtube_languages
from ._platform import (
    Platform,
    _detect_platform,
    _normalize_youtube_url,
    _resolve_facebook_share_url,
    _resolve_kwai_url,
    _resolve_short_reddit_url,
)
from ._ytdlp import (
    _apply_format_selection,
    _build_ytdlp_base_opts,
    _run_ytdlp_with_cookie_fallback,
    _wipe_folder,
)

from .facebook import _FB_NUMERIC_USER_RE, download_facebook_gallery, facebook_owner_mismatch
from .fallback import _build_status, _gallery_dl_run, fetch_article_caption, gallery_dl_download, prefers_gallery_dl, scrape_fallback
from .instagram import download_instagram_api
from .instagram_embed import download_instagram_embed
from .reddit_json import download_reddit_json, resolve_reddit_external_link
from .reddit_playwright import download_reddit_playwright
from .threads import download_threads
from .x import download_x

logger = logging.getLogger(__name__)

_IG_AUTH_RETRY_REASONS = {"sign_in_required", "age_restricted", "unavailable"}


async def _run_platform_fallbacks(
    url: str,
    unique_folder: str,
    platform: Platform,
) -> Optional[tuple[list[str], str, str, str, bool]]:
    if platform.instagram:
        ig_files, ig_status, ig_short, ig_full = await download_instagram_api(url, unique_folder)
        if ig_files:
            return await _finalize_success(ig_files, ig_status, ig_short, ig_full, url)

    if platform.reddit:
        reddit_pw_files, reddit_pw_status, reddit_pw_short, reddit_pw_full = await download_reddit_playwright(url, unique_folder)
        if reddit_pw_files:
            return await _finalize_success(reddit_pw_files, reddit_pw_status, reddit_pw_short, reddit_pw_full, url)

    if platform.youtube:
        logger.info(lmsg("dispatcher.youtube_skip_scraper", url=safe_url(url)))
        return None

    scrape_files, scrape_status, scrape_short, scrape_full, scrape_is_article = await scrape_fallback(url, unique_folder)
    if scrape_files:
        return scrape_files, scrape_status, scrape_short, scrape_full, scrape_is_article

    return None


def _platform_label(platform: Platform) -> str:
    for name in ('youtube', 'instagram', 'threads', 'reddit', 'facebook', 'x', 'tiktok'):
        if getattr(platform, name):
            return name
    return 'other'


async def _reddit_news_card(
    link: dict, unique_folder: str, platform_label: str, started: float,
) -> tuple[list, str, str, str, bool]:
    news_url = link['external_url']
    files: list[str] = []
    thumb = link.get('thumbnail_url')
    if thumb:
        thumb_path = os.path.join(unique_folder, 'reddit_link_thumb.jpg')
        try:
            if await async_download_file(thumb, thumb_path):
                normalized = await asyncio.to_thread(normalize_image, thumb_path, min_size=1)
                if normalized:
                    files = [normalized]
        except Exception as e:
            logger.debug(lmsg("dispatcher.reddit_link_thumb_falhou", e=e))
    caption_short, caption_full = _build_caption({'title': link.get('title') or ''}, news_url)
    metrics.record_success(platform_label, time.monotonic() - started)
    logger.info(lmsg("dispatcher.reddit_link_card", url=safe_url(news_url)))
    return files, msg("downloader_status.reddit_link_card"), caption_short, caption_full, True


def _caption_is_weak(caption: str) -> bool:
    if not caption or not caption.strip():
        return True
    link_prefix = msg("caption.link_prefix")
    stripped = caption.strip()
    return stripped.startswith(link_prefix) and stripped.count('<a ') <= 1


async def _enrich_caption_with_article(
    url: str, caption_short: str, caption_full: str,
) -> tuple[str, str, bool]:
    if not _caption_is_weak(caption_short):
        return caption_short, caption_full, False
    article_short, article_full = await fetch_article_caption(url)
    if article_short:
        return article_short, article_full, True
    return caption_short, caption_full, False


async def _finalize_success(
    files: list,
    status: str,
    caption_short: str,
    caption_full: str,
    url: str,
    platform_label: Optional[str] = None,
    started: Optional[float] = None,
) -> tuple[list, str, str, str, bool]:
    caption_short, caption_full, is_article = await _enrich_caption_with_article(
        url, caption_short, caption_full,
    )
    if platform_label is not None and started is not None:
        metrics.record_success(platform_label, time.monotonic() - started)
    return files, status, caption_short, caption_full, is_article


async def download_media(
    url: str,
    unique_folder: str,
    target_lang: Optional[str] = None,
    detect_languages: bool = True,
    _depth: int = 0,
) -> tuple[list, str, str, str, bool]:
    started = time.monotonic()
    platform_label = 'other'
    try:
        os.makedirs(unique_folder, exist_ok=True)

        url = await _resolve_short_reddit_url(url)
        url = await _resolve_facebook_share_url(url)
        url = await _resolve_kwai_url(url)
        platform = _detect_platform(url)
        platform_label = _platform_label(platform)

        if platform.youtube:
            url = _normalize_youtube_url(url)

        if platform.threads:
            logger.info(lmsg("dispatcher.link_do_threads"))
            files, status_info, t_short, t_full = await download_threads(url, unique_folder)
            if files:
                return await _finalize_success(files, status_info, t_short, t_full, url, platform_label, started)
            if t_short:
                metrics.record_success(platform_label, time.monotonic() - started)
                return [], status_info, t_short, t_full, False
            metrics.record_failure(platform_label, time.monotonic() - started)
            return [], msg("downloader_status.threads_fail"), "", "", False

        if platform.x:
            logger.info(lmsg("dispatcher.link_do_x"))
            files, status_info, x_short, x_full = await download_x(url, unique_folder)
            if files:
                return await _finalize_success(files, status_info, x_short, x_full, url, platform_label, started)
            if x_short:
                metrics.record_success(platform_label, time.monotonic() - started)
                return [], status_info, x_short, x_full, False
            metrics.record_failure(platform_label, time.monotonic() - started)
            return [], msg("downloader_status.x_fail"), "", "", False

        if platform.instagram:
            embed_files, embed_status, embed_short, embed_full = await download_instagram_embed(url, unique_folder)
            if embed_files:
                return await _finalize_success(embed_files, embed_status, embed_short, embed_full, url, platform_label, started)

        reddit_post_data = None
        if platform.reddit:
            link, reddit_post_data = await resolve_reddit_external_link(url)
            if link and link.get('external_url') and _depth < 2:
                inner_url = link['external_url']
                logger.info(lmsg("dispatcher.reddit_link_redispatch", url=safe_url(inner_url)))
                r_files, r_status, r_short, r_full, r_art = await download_media(
                    inner_url, unique_folder, target_lang, detect_languages, _depth + 1,
                )
                if r_files or r_short or r_full:
                    return r_files, r_status, r_short, r_full, r_art
                logger.info(lmsg("dispatcher.reddit_link_card", url=safe_url(inner_url)))
                return await _reddit_news_card(link, unique_folder, platform_label, started)

            rj_files, rj_status, rj_short, rj_full = await download_reddit_json(
                url, unique_folder, post_data=reddit_post_data,
            )
            if rj_files:
                return await _finalize_success(rj_files, rj_status, rj_short, rj_full, url, platform_label, started)
            if rj_short:
                metrics.record_success(platform_label, time.monotonic() - started)
                return [], rj_status, rj_short, rj_full, False
            if rj_status == msg("downloader_status.reddit_media_removed"):
                # o yt-dlp só diria "exige login", que engana
                metrics.record_failure(platform_label, time.monotonic() - started)
                return [], rj_status, "", "", False

        if platform.facebook:
            fb_files, fb_status, fb_short, fb_full = await download_facebook_gallery(url, unique_folder)
            if fb_files:
                return await _finalize_success(fb_files, fb_status, fb_short, fb_full, url, platform_label, started)

        if platform_label == 'other' and prefers_gallery_dl(url):
            logger.info(lmsg("dispatcher.gallery_dl_first", url=safe_url(url)))
            gdl_files, missing = await gallery_dl_download(url, unique_folder)
            if gdl_files:
                if missing > 0:
                    state.download_notice.set(msg(
                        "downloader_status.gallery_incomplete", missing=missing, total=len(gdl_files) + missing,
                    ))
                elif missing < 0:
                    state.download_notice.set(msg("downloader_status.gallery_maybe_incomplete"))
                return await _finalize_success(
                    gdl_files, _build_status(gdl_files, "downloader_status.scraper_gallerydl"),
                    "", "", url, platform_label, started,
                )
            _wipe_folder(unique_folder)

        has_firefox_cookie = os.path.exists(os.path.join(FIREFOX_PROFILE_PATH, 'cookies.sqlite'))
        if platform.youtube and not state.DENO_PATH:
            logger.warning(lmsg("dispatcher.aten_o_deno_n_o"))
        elif platform.youtube and state.DENO_PATH:
            logger.info(lmsg("dispatcher.deno_js_engine", arg0=state.DENO_PATH))

        base_opts = _build_ytdlp_base_opts(unique_folder)
        _apply_format_selection(base_opts, platform, target_lang)

        if platform.youtube and not target_lang and detect_languages:
            lang_buttons = await _detect_youtube_languages(base_opts, url, has_firefox_cookie)
            if lang_buttons:
                metrics.record_multilang(platform_label)
                return lang_buttons, "MULTILANG", "", "", False

        # Reddit sem API JSON: o yt-dlp baixa direto o HLS achado na página.
        hls_url = (reddit_post_data or {}).get('_hls_url')
        downloaded_files, info_dict, unrecoverable_reason = await _run_ytdlp_with_cookie_fallback(
            base_opts, hls_url or url, unique_folder, has_firefox_cookie, target_lang,
            platform=platform,
        )

        if hls_url:
            caption_short, caption_full = _build_caption({'title': reddit_post_data.get('title') or ''}, url)
        else:
            caption_short, caption_full = _build_caption(info_dict, url)

        if downloaded_files and platform.facebook and facebook_owner_mismatch(url, info_dict):
            logger.warning(lmsg(
                "dispatcher.facebook_owner_mismatch",
                url_uid=_FB_NUMERIC_USER_RE.search(url).group(1) if _FB_NUMERIC_USER_RE.search(url) else '?',
                yt_uid=info_dict.get('uploader_id'),
                yt_uploader=info_dict.get('uploader'),
            ))
            _wipe_folder(unique_folder)
            downloaded_files = []

        if downloaded_files:
            return await _finalize_success(
                downloaded_files, msg("downloader_status.ytdlp_success"),
                caption_short, caption_full, url, platform_label, started,
            )

        if unrecoverable_reason:
            _wipe_folder(unique_folder)
            if platform.instagram and unrecoverable_reason in _IG_AUTH_RETRY_REASONS:
                logger.info(lmsg("dispatcher.unrecoverable_try_instagrapi", reason=unrecoverable_reason, url=safe_url(url)))
                ig_files, ig_status, ig_short, ig_full = await download_instagram_api(url, unique_folder)
                if ig_files:
                    return await _finalize_success(
                        ig_files, ig_status, ig_short, ig_full, url, platform_label, started,
                    )
                _wipe_folder(unique_folder)
                # gallery-dl: último recurso com a mesma sessão web, se a API web não resolveu.
                logger.info(lmsg("dispatcher.unrecoverable_try_gallery_dl", reason=unrecoverable_reason, url=safe_url(url)))
                gdl_files = await _gallery_dl_run(url, unique_folder)
                if gdl_files:
                    return await _finalize_success(
                        gdl_files, _build_status(gdl_files, "downloader_status.scraper_gallerydl"),
                        "", "", url, platform_label, started,
                    )
                _wipe_folder(unique_folder)
            logger.info(lmsg("dispatcher.unrecoverable_skip_fallbacks", reason=unrecoverable_reason, url=safe_url(url)))
            metrics.record_failure(platform_label, time.monotonic() - started)
            return [], msg(f"downloader_status.ytdlp_{unrecoverable_reason}"), "", "", False

        logger.warning(lmsg("dispatcher.falha_no_yt", arg0=safe_url(url)))
        _wipe_folder(unique_folder)

        fallback_result = await _run_platform_fallbacks(url, unique_folder, platform)
        if fallback_result:
            metrics.record_success(platform_label, time.monotonic() - started)
            return fallback_result

        metrics.record_failure(platform_label, time.monotonic() - started)
        return [], msg("downloader_status.generic_fail"), "", "", False
    except Exception:
        metrics.record_failure(platform_label, time.monotonic() - started)
        raise

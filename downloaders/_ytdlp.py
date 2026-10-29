import asyncio
import logging
import os
from typing import Any, Optional

import yt_dlp
from yt_dlp.networking.impersonate import ImpersonateTarget

import state
from utils import dedupe_identical_files
from config import (
    cfg,
    FIREFOX_PROFILE_PATH,
)
from messages import lmsg

from ._platform import Platform

logger = logging.getLogger(__name__)


def _build_ytdlp_base_opts(unique_folder: str) -> dict[str, Any]:
    opts: dict[str, Any] = {
        'outtmpl': os.path.join(unique_folder, '%(title).150B [%(id)s].%(ext)s'),
        'restrictfilenames': True,
        'writedescription': False,
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'geo_bypass': True,
        'socket_timeout': cfg("YTDLP_SOCKET_TIMEOUT"),
        'remote_components': ['ejs:github'],
        # Pela API o yt-dlp quer {chave: [valores]}; a forma "player_client=a,b" é só da linha de comando e aqui era ignorada.
        'extractor_args': {'youtube': {'player_client': [c.strip() for c in str(cfg("YTDLP_YT_CLIENTS")).split(',') if c.strip()]}},
        'format_sort': ['vcodec:h264', 'acodec:aac'],
        'impersonate': ImpersonateTarget('chrome'),
    }
    if state.DENO_PATH:
        opts['js_runtimes'] = {'deno': {'path': state.DENO_PATH}}
    return opts


def _calc_max_tbr_kbps(duration_s: Optional[int], cap_mb: int, margin: float = 0.95) -> Optional[int]:
    if not duration_s or duration_s <= 0:
        return None
    max_bytes = cap_mb * 1024 * 1024 * margin
    return max(50, int(max_bytes * 8 / duration_s / 1024))


def _is_hls_only(formats: list[dict]) -> bool:
    if not formats:
        return False
    has_video = False
    for f in formats:
        if (f.get('vcodec') or 'none') == 'none':
            continue
        has_video = True
        proto = (f.get('protocol') or '').lower()
        if 'm3u8' not in proto and 'http_dash' not in proto:
            return False
    return has_video


def _live_reason(info: Optional[dict]) -> Optional[str]:
    if not isinstance(info, dict):
        return None
    status = info.get('live_status')
    if status == 'is_live':
        return 'live_in_progress'
    if status == 'is_upcoming':
        return 'live_not_started'
    if info.get('is_live') and status not in ('was_live', 'post_live', 'not_live'):
        return 'live_in_progress'
    return None


def _build_format_selector(
    height: int,
    cap_mb: int,
    tbr_filter: str,
    target_lang: Optional[str],
    youtube: bool,
) -> str:
    vid_max_mb = max(50, cap_mb - 100)
    fs_video = f'[filesize_approx<{vid_max_mb}M]'
    fs_total = f'[filesize_approx<{cap_mb}M]'
    tiers: list[str] = []
    if youtube and target_lang and target_lang != 'original':
        tiers.append(f'best[height<={height}][language^={target_lang}]{fs_total}')
        if tbr_filter:
            tiers.append(f'best[height<={height}][language^={target_lang}]{tbr_filter}')
        tiers.append(f'bestvideo[height<={height}]{fs_video}+bestaudio[language^={target_lang}]')
    tiers.append(f'bestvideo[height<={height}]{fs_video}+bestaudio')
    tiers.append(f'best[height<={height}]{fs_total}')
    if tbr_filter:
        tiers.append(f'best[height<={height}]{tbr_filter}')
    tiers.append(f'best{fs_total}')
    if tbr_filter:
        tiers.append(f'best{tbr_filter}')
    tiers.append('best')
    return '/'.join(tiers)


def _apply_format_selection(
    opts: dict[str, Any],
    platform: Platform,
    target_lang: Optional[str],
    info: Optional[dict] = None,
    use_impersonate: bool = True,
) -> None:
    h = cfg("YTDLP_MAX_HEIGHT")
    cap_mb = cfg("TELEGRAM_MAX_UPLOAD_MB")

    height_eff = h
    tbr_filter = ""
    if info:
        formats = info.get('formats') or []
        if _is_hls_only(formats):
            hls_h = cfg("YTDLP_HLS_MAX_HEIGHT")
            height_eff = min(h, hls_h)
            logger.info(lmsg("_ytdlp.hls_only_height_cap", height=height_eff))
        max_tbr = _calc_max_tbr_kbps(info.get('duration'), cap_mb)
        if max_tbr:
            tbr_filter = f"[tbr<={max_tbr}]"
            logger.info(lmsg("_ytdlp.tbr_cap", max_tbr=max_tbr, duration=info.get('duration'), cap_mb=cap_mb))

    if platform.instagram:
        opts['noplaylist'] = False
        opts['format'] = 'best'
    elif platform.reddit:
        opts['noplaylist'] = False
        opts['format'] = 'bestvideo+bestaudio/best'
    else:
        opts['noplaylist'] = True
        opts['format'] = _build_format_selector(
            height_eff, cap_mb, tbr_filter,
            target_lang=target_lang, youtube=platform.youtube,
        )
        opts['merge_output_format'] = 'mp4'

    if not use_impersonate:
        opts.pop('impersonate', None)

    if platform.tiktok:
        tiktok_proxy = cfg("TIKTOK_PROXY")
        if tiktok_proxy:
            opts['proxy'] = tiktok_proxy


class _ErrorCapturingLogger:
    def __init__(self) -> None:
        self.errors: list[str] = []
    def debug(self, msg) -> None: pass
    def info(self, msg) -> None: pass
    def warning(self, msg) -> None: pass
    def error(self, msg) -> None:
        self.errors.append(str(msg))


_UNRECOVERABLE_PATTERNS: list[tuple[str, str]] = [
    ('private video', 'private'),
    ('this account is private', 'private'),
    ('members-only', 'members_only'),
    ('join this channel', 'members_only'),
    ('this video is available to this channel', 'members_only'),
    ('restricted to subscribers', 'members_only'),
    ('confirm your age', 'age_restricted'),
    ('age-restricted', 'age_restricted'),
    ('not available in your country', 'geo_blocked'),
    ('not available from your location', 'geo_blocked'),
    ('blocked it in your country', 'geo_blocked'),
    ('removed by the uploader', 'removed'),
    ('removed by the user', 'removed'),
    ('this video has been removed', 'removed'),
    ('this video is no longer available', 'removed'),
    ('account has been terminated', 'removed'),
    ('account has been suspended', 'removed'),
    ('premieres in', 'live_not_started'),
    ('this live event will begin', 'live_not_started'),
    ('video unavailable', 'unavailable'),
    ('this content isn\'t available', 'unavailable'),
    ('this tweet is unavailable', 'unavailable'),
    ('no video formats found', 'unavailable'),
    ('no media found', 'unavailable'),
    ('cannot parse data', 'unavailable'),
    ('only available for registered users', 'sign_in_required'),
    ('only available for registered', 'sign_in_required'),
    ('only available to registered', 'sign_in_required'),
    ('use --cookies', 'sign_in_required'),
    ('login required', 'sign_in_required'),
    ('sign in to confirm', 'sign_in_required'),
    ('requires login', 'sign_in_required'),
    ('please log in', 'sign_in_required'),
    ('rate-limit reached', 'rate_limited'),
    ('http error 429', 'rate_limited'),
    ('too many requests', 'rate_limited'),
]


def _classify_ytdlp_errors(error_messages: list[str]) -> Optional[str]:
    if not error_messages:
        return None
    blob = ' | '.join(error_messages).lower()
    for needle, key in _UNRECOVERABLE_PATTERNS:
        if needle in blob:
            return key
    return None


def _yt_dlp_extract(
    opts: dict[str, Any], url: str, download: bool = False,
    capture_errors: bool = False,
) -> Any:
    opts = dict(opts)
    err_logger: Optional[_ErrorCapturingLogger] = None
    if capture_errors:
        err_logger = _ErrorCapturingLogger()
        opts['logger'] = err_logger
    if not download:
        opts['extract_flat'] = False
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=download)
    if capture_errors:
        return info, err_logger.errors
    return info


def _list_downloaded_files(folder: str) -> list[str]:
    if not os.path.exists(folder):
        return []
    return [
        os.path.join(folder, f)
        for f in os.listdir(folder)
        if os.path.isfile(os.path.join(folder, f))
        and not f.endswith(('.part', '.ytdl', '.temp'))
    ]


def _wipe_folder(folder: str) -> None:
    if not os.path.exists(folder):
        return
    for f in os.listdir(folder):
        full_path = os.path.join(folder, f)
        if os.path.isfile(full_path):
            try:
                os.remove(full_path)
            except OSError as e:
                logger.debug(lmsg("_ytdlp.falha_ao_remover", full_path=full_path, e=e))


def _attempt_order(
    has_firefox_cookie: bool, target_lang: Optional[str], platform: Optional[Platform] = None,
) -> list[str]:
    attempts: list[str] = []
    # Reddit bloqueia IP de datacenter sem login: sem cookie é tentativa perdida.
    cookie_first = bool(target_lang and target_lang != 'original') or bool(platform and (platform.tiktok or platform.reddit))
    if cookie_first:
        if has_firefox_cookie:
            attempts.append("with_cookie")
        attempts.append("no_cookie")
    else:
        attempts.append("no_cookie")
        if has_firefox_cookie:
            attempts.append("with_cookie")
    return attempts


def _expand_attempts_with_impersonate(
    attempts: list[str], platform: Optional[Platform],
) -> list[tuple[str, bool]]:
    uses_impersonate = platform is not None and (
        platform.facebook or platform.instagram or platform.reddit
    )
    if uses_impersonate:
        return [(m, False) for m in attempts] + [(m, True) for m in attempts]
    return [(m, True) for m in attempts]


async def _pre_extract(base_opts: dict[str, Any], url: str, mode: str) -> Optional[dict]:
    extract_opts = base_opts.copy()
    extract_opts.pop('format', None)
    if mode == "with_cookie":
        extract_opts['cookiesfrombrowser'] = ('firefox', FIREFOX_PROFILE_PATH, None, None)
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(state.YTDLP_POOL, _yt_dlp_extract, extract_opts, url, False)
    except Exception as e:
        logger.debug(lmsg("_ytdlp.pre_extract_falhou", mode=mode, e=e))
        return None


async def _run_ytdlp_with_cookie_fallback(
    base_opts: dict[str, Any],
    url: str,
    unique_folder: str,
    has_firefox_cookie: bool,
    target_lang: Optional[str],
    platform: Optional[Platform] = None,
) -> tuple[list[str], dict[str, Any], Optional[str]]:
    loop = asyncio.get_running_loop()
    info_dict: dict[str, Any] = {}
    downloaded_files: list[str] = []
    all_errors: list[str] = []

    last_exc: Optional[BaseException] = None
    base_attempts = _attempt_order(has_firefox_cookie, target_lang, platform)
    expanded_attempts = _expand_attempts_with_impersonate(base_attempts, platform)
    for mode, use_imp in expanded_attempts:
        _wipe_folder(unique_folder)

        current_opts = base_opts.copy()
        if mode == "with_cookie":
            logger.info(lmsg("_ytdlp.usando_cookies_globais"))
            current_opts['cookiesfrombrowser'] = ('firefox', FIREFOX_PROFILE_PATH, None, None)

        if platform is not None:
            info_for_select = None if platform.reddit else await _pre_extract(base_opts, url, mode)
            live_reason = _live_reason(info_for_select)
            if live_reason:
                logger.info(lmsg("_ytdlp.live_detectada", reason=live_reason))
                return [], info_for_select or {}, live_reason
            _apply_format_selection(
                current_opts, platform, target_lang,
                info=info_for_select, use_impersonate=use_imp,
            )

        attempt_label = f"{mode}{'_imp' if use_imp else '_noimp'}"
        try:
            result = await loop.run_in_executor(
                state.YTDLP_POOL, _yt_dlp_extract, current_opts, url, True, True,
            )
            info, attempt_errors = result
            all_errors.extend(attempt_errors)

            if info:
                if 'entries' in info and info.get('entries'):
                    valid = [e for e in info['entries'] if e is not None]
                    info_dict = valid[0] if valid else info
                else:
                    info_dict = info
            if info_dict is None:
                info_dict = {}

            current_files = _list_downloaded_files(unique_folder)
            if current_files:
                downloaded_files = await asyncio.to_thread(dedupe_identical_files, sorted(current_files))
                logger.info(lmsg("_ytdlp.download_bem_sucedido", mode=attempt_label))
                break
            logger.warning(lmsg("_ytdlp.yt_dlp_falhou", mode=attempt_label))
        except Exception as e:
            last_exc = e
            logger.warning(lmsg("_ytdlp.yt_dlp_exce_o", mode=attempt_label, e=e))

    if not downloaded_files and last_exc is not None:
        logger.debug(lmsg("_ytdlp.stack_trace_last_exc"), exc_info=last_exc)

    reason = _classify_ytdlp_errors(all_errors) if not downloaded_files else None
    if reason:
        logger.info(lmsg("_ytdlp.unrecoverable_reason", reason=reason))
    return downloaded_files, info_dict, reason

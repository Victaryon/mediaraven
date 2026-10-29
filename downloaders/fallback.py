import asyncio
import logging
import os
from typing import Optional
from urllib.parse import quote, urlparse

import yt_dlp
from curl_cffi import requests as curl_requests

import state
from config import cfg, FIREFOX_PROFILE_PATH
from messages import lmsg, msg
from utils import (
    async_download_file,
    async_download_file_segmented,
    async_download_via_playwright,
    async_ffmpeg_remux,
    normalize_image,
    safe_url,
)

from ._caption import _build_caption
from ._platform import _bare_host, _host_matches
from ._ytdlp import _build_format_selector, _list_downloaded_files
from ._scrape_helpers import (
    MediaTuple,
    classify_media_url,
    dedupe_key,
    extract_article,
    extract_iframes,
    extract_jsonld_media,
    extract_meta_media,
    extract_player_configs,
    is_junk_url,
    merge_media_lists,
    rewrite_to_max_resolution,
)

logger = logging.getLogger(__name__)


_PINTEREST_HOSTS = ('pinterest.com', 'pin.it', 'pinterest.co.uk')
_PAYWALL_PATTERNS = (
    'sign in to continue', 'log in to continue', 'subscribe to read',
    'create a free account to read', 'this content is for subscribers',
    'faça login para continuar', 'assine para ler', 'conteúdo exclusivo para assinantes',
)


def _is_pinterest(url: str) -> bool:
    return _host_matches(_bare_host(url), _PINTEREST_HOSTS)


_GOOGLEBOT_UA = (
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
)


async def _fetch_html(
    url: str,
    timeout: int,
    user_agent: Optional[str] = None,
) -> Optional[str]:
    loop = asyncio.get_running_loop()
    headers = {'User-Agent': user_agent} if user_agent else None
    try:
        r = await loop.run_in_executor(
            state.IO_POOL,
            lambda: curl_requests.get(
                url, impersonate="chrome", timeout=timeout,
                allow_redirects=True, headers=headers,
            ),
        )
    except Exception as e:
        logger.debug(lmsg("fallback.curl_cffi_falhou", arg0=safe_url(url), e=e))
        return None
    if r.status_code != 200:
        logger.debug(lmsg("fallback.fast_path_http", arg0=r.status_code, arg1=safe_url(url)))
        return None
    return r.text


def _looks_like_paywall(html: str) -> bool:
    if not html:
        return False
    low = html.lower()
    return any(p in low for p in _PAYWALL_PATTERNS)


async def _try_archive_today(url: str, timeout: int) -> Optional[str]:
    archive_url = f"https://archive.ph/newest/{quote(url, safe=':/?&=')}"
    logger.info(lmsg("fallback.tentando_archive_ph", arg0=safe_url(url)))
    return await _fetch_html(archive_url, timeout=timeout)


async def _fetch_html_with_paywall_bypass(
    url: str, timeout: int,
) -> tuple[Optional[str], str]:
    html = await _fetch_html(url, timeout=timeout)
    if not _looks_like_paywall(html or ""):
        return html, ('normal' if html else '')

    if cfg("SCRAPE_PAYWALL_BYPASS") != "yes":
        return html, 'normal'

    logger.info(lmsg("fallback.paywall_detectado_em", arg0=safe_url(url)))
    gbot_html = await _fetch_html(url, timeout=timeout, user_agent=_GOOGLEBOT_UA)
    if gbot_html and not _looks_like_paywall(gbot_html):
        logger.info(lmsg("fallback.googlebot_ua_passou", arg0=safe_url(url)))
        return gbot_html, 'googlebot'

    arch_html = await _try_archive_today(url, timeout=cfg("SCRAPE_ARCHIVE_TIMEOUT_S"))
    if arch_html and not _looks_like_paywall(arch_html):
        logger.info(lmsg("fallback.archive_ph_retornou", arg0=safe_url(url)))
        return arch_html, 'archive'

    logger.warning(lmsg("fallback.paywall_n_o_vencido", arg0=safe_url(url)))
    return html, 'normal'


def _normalize_kind(kind: str, url: str) -> str:
    if kind in ('image', 'video', 'hls', 'dash'):
        return kind
    return classify_media_url(url) or 'image'


async def _gather_media_via_playwright(
    page_url: str,
) -> tuple[list[MediaTuple], list[str], str]:
    """Scrape via Playwright. Retorna (media_tuples, iframe_urls, page_text)."""
    if not state.PW_BROWSER or not state.PW_CONTEXT:
        return [], [], ""

    captured_responses: list[tuple[str, str]] = []
    page_html: str = ""

    async with state.PW_SEMAPHORE:
        page = None
        try:
            page = await state.PW_CONTEXT.new_page()

            async def handle_response(response):
                try:
                    rtype = response.request.resource_type
                    ct = (response.headers.get('content-type') or '').lower()
                    if rtype in ('image', 'media') or 'mpegurl' in ct or 'dash+xml' in ct:
                        u = response.url
                        if u.startswith('http'):
                            captured_responses.append((u, ct))
                except Exception as e:
                    logger.debug(lmsg("fallback.handle_response_x", e=e))

            page.on("response", handle_response)
            await page.goto(page_url, wait_until="load", timeout=cfg("PW_GOTO_TIMEOUT_MS"))

            prev_count = -1
            for _ in range(cfg("SCRAPE_SCROLL_MAX_ROUNDS")):
                try:
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                except Exception as e:
                    logger.debug(lmsg("fallback.scroll_falhou_x", e=e))
                    break
                await page.wait_for_timeout(cfg("SCRAPE_SCROLL_PAUSE_MS"))
                if len(captured_responses) == prev_count:
                    break
                prev_count = len(captured_responses)

            try:
                page_html = await page.content()
            except Exception as e:
                logger.debug(lmsg("fallback.page_content_falhou", e=e))

        except Exception as e:
            logger.warning(lmsg("fallback.erro_scraper_playwright", e=e), exc_info=True)
        finally:
            if page is not None:
                try:
                    await page.close()
                except Exception:
                    pass

    sniffed: list[MediaTuple] = []
    for u, ct in captured_responses:
        kind = classify_media_url(u, ct)
        if kind:
            sniffed.append((kind, u))

    meta = extract_meta_media(page_html, page_url) if page_html else []
    jsonld = extract_jsonld_media(page_html, page_url) if page_html else []
    players = extract_player_configs(page_html, page_url) if page_html else []
    iframes = extract_iframes(page_html, page_url) if page_html else []

    media = merge_media_lists(meta, jsonld, sniffed, players, cap=cfg("SCRAPE_MAX_MEDIA_URLS"))
    return media, iframes, page_html


def _gather_media_from_html(html: str, base_url: str) -> list[MediaTuple]:
    meta = extract_meta_media(html, base_url)
    jsonld = extract_jsonld_media(html, base_url)
    players = extract_player_configs(html, base_url)
    return merge_media_lists(meta, jsonld, players, cap=cfg("SCRAPE_MAX_MEDIA_URLS"))


def _prepare_for_download(
    media: list[MediaTuple],
) -> list[MediaTuple]:
    out: list[MediaTuple] = []
    seen_keys: set[str] = set()
    junked = 0
    deduped = 0
    for kind, url in media:
        if is_junk_url(url):
            junked += 1
            continue
        rewritten = rewrite_to_max_resolution(url)
        normalized_kind = _normalize_kind(kind, rewritten)
        key = dedupe_key(rewritten)
        if key in seen_keys:
            deduped += 1
            continue
        seen_keys.add(key)
        out.append((normalized_kind, rewritten))
    if junked or deduped:
        logger.info(lmsg(
            "fallback.prepare_stats",
            n_in=len(media), n_out=len(out), junked=junked, deduped=deduped,
        ))
    return out


async def _download_one(
    kind: str,
    media_url: str,
    page_url: str,
    folder: str,
    idx: int,
    failed_counter: list[int],
) -> Optional[str]:
    """Baixa uma mídia. Retorna o caminho final (já normalizado) ou None."""
    headers = {'Referer': page_url} if page_url else None

    if kind in ('hls', 'dash'):
        out_path = os.path.join(folder, f"scrape_media_{idx}.mp4")
        ok = await async_ffmpeg_remux(
            media_url, out_path, timeout=cfg("SCRAPE_HLS_TIMEOUT_S"), headers=headers,
        )
        if ok:
            return out_path
        return None

    ext = ".mp4" if kind == "video" else ".jpg"
    filepath = os.path.join(folder, f"scrape_media_{idx}{ext}")

    try:
        result = await async_download_file(
            media_url, filepath, headers=headers, return_content_type=True,
        )
    except Exception as e:
        logger.warning(lmsg("fallback.async_download_falhou", e=e))
        result = (False, '')

    success, ct = (result if isinstance(result, tuple) else (result, ''))

    if not success:
        ok = await async_download_via_playwright(media_url, filepath, referer=page_url)
        if not ok:
            failed_counter[0] += 1
            return None

    if kind == "image":
        normalized = await asyncio.to_thread(normalize_image, filepath, min_size=cfg("SCRAPE_MIN_IMAGE_SIZE"))
        return normalized
    return filepath


async def _download_all(
    media: list[MediaTuple],
    page_url: str,
    folder: str,
) -> tuple[list[str], int]:
    """Baixa em paralelo. Retorna (arquivos, contagem_de_403)."""
    semaphore = asyncio.Semaphore(cfg("SCRAPE_MAX_PARALLEL_DOWNLOADS"))
    failed_counter = [0]

    async def task(idx: int, kind: str, url: str) -> Optional[str]:
        async with semaphore:
            return await _download_one(kind, url, page_url, folder, idx, failed_counter)

    coros = [task(i, k, u) for i, (k, u) in enumerate(media)]
    results = await asyncio.gather(*coros, return_exceptions=True)

    files: list[str] = []
    seen_paths: set[str] = set()
    for r in results:
        if isinstance(r, Exception):
            logger.debug(lmsg("fallback.download_task_exception", r=r))
            continue
        if r and r not in seen_paths and os.path.exists(r):
            seen_paths.add(r)
            files.append(r)
    return files, failed_counter[0]


async def _ytdlp_generic(url: str, folder: str) -> list[str]:
    """yt-dlp em modo genérico forçado. Cobre iframe/JSON-LD/HLS de saída."""
    opts = {
        'outtmpl': os.path.join(folder, 'generic_%(autonumber)s.%(ext)s'),
        'restrictfilenames': True,
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'noplaylist': True,
        'force_generic_extractor': True,
        'socket_timeout': cfg("YTDLP_SOCKET_TIMEOUT"),
        'format': _build_format_selector(
            cfg("YTDLP_MAX_HEIGHT"), cfg("TELEGRAM_MAX_UPLOAD_MB"), "",
            target_lang=None, youtube=False,
        ),
        'merge_output_format': 'mp4',
    }

    loop = asyncio.get_running_loop()

    def _run():
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.extract_info(url, download=True)
        except Exception as e:
            logger.debug(lmsg("fallback.yt_dlp_generic", e=e))

    try:
        await loop.run_in_executor(state.YTDLP_POOL, _run)
    except Exception as e:
        logger.debug(lmsg("fallback.yt_dlp_generic_2", e=e))
        return []

    return sorted(_list_downloaded_files(folder))


_GALLERY_DL_LOCK = asyncio.Lock()
_GALLERY_DL_LOADED = False


def _can_handle_with_gallery_dl(url: str) -> bool:
    try:
        from gallery_dl import extractor
        return extractor.find(url) is not None
    except Exception as e:
        logger.debug(lmsg("fallback.gallery_dl_extractor", e=e))
        return False


def _ytdlp_has_specific_extractor(url: str) -> bool:
    from yt_dlp.extractor import gen_extractor_classes
    return any(ie.suitable(url) for ie in gen_extractor_classes() if ie.ie_key() != 'Generic')


def prefers_gallery_dl(url: str) -> bool:
    """gallery-dl primeiro quando ele tem extrator próprio pro site e o yt-dlp só
    teria o genérico (ex.: álbuns mistos de fotos e vídeos). O genérico do yt-dlp só enxerga
    <video>, ignora as fotos e pega cada vídeo duas vezes (<video> e <source>)."""
    if cfg("SCRAPE_GALLERY_DL_ENABLE") != "yes" or not _can_handle_with_gallery_dl(url):
        return False
    try:
        return not _ytdlp_has_specific_extractor(url)
    except Exception as e:
        logger.debug(lmsg("fallback.gallery_dl_extractor", e=e))
        return False


def _list_files_in(folder: str) -> list[str]:
    if not os.path.exists(folder):
        return []
    out: list[str] = []
    for root, _, files in os.walk(folder):
        for f in files:
            if f.endswith(('.part', '.json', '.txt')):
                continue
            out.append(os.path.join(root, f))
    return sorted(out)


def _load_gallery_dl_config() -> None:
    global _GALLERY_DL_LOADED
    from gallery_dl import config as gdl_config

    if not _GALLERY_DL_LOADED:
        try:
            gdl_config.load()
        except Exception as e:
            logger.debug(lmsg("fallback.gallery_dl_config", e=e))
        _GALLERY_DL_LOADED = True

    gdl_config.set((), 'output', {'mode': 'null'})
    if os.path.exists(os.path.join(FIREFOX_PROFILE_PATH, 'cookies.sqlite')):
        gdl_config.set(('extractor',), 'cookies', ('firefox', FIREFOX_PROFILE_PATH))


# Chaves _http_* que o download próprio sabe reproduzir; qualquer outra (método,
# corpo, validação, assinatura...) fica com o downloader do próprio gallery-dl.
_GDL_PLAIN_HTTP_KEYS = {"_http_headers", "_http_expected_status", "_http_adjust_extension"}
_GDL_SKIP_HEADERS = {"accept-encoding", "connection"}


def _collect_gallery_dl_items(url: str) -> Optional[list[tuple[str, str, dict]]]:
    """Só lista os arquivos (URL, extensão, headers), sem baixar. None quando
    algum item precisa de algo que só o downloader do gallery-dl faz."""
    import requests
    from gallery_dl import job as gdl_job

    items: list[tuple[str, str, dict]] = []
    unsupported = False

    class _CollectJob(gdl_job.Job):
        def handle_url(self, file_url, kwdict):
            nonlocal unsupported
            extra = {k for k in kwdict if k.startswith('_http_')} - _GDL_PLAIN_HTTP_KEYS
            if extra or not file_url.startswith(('http://', 'https://')):
                unsupported = True
                return
            items.append((file_url, kwdict.get('extension') or '', dict(kwdict.get('_http_headers') or {})))

        def handle_queue(self, queue_url, kwdict):
            nonlocal unsupported
            unsupported = True

    job = _CollectJob(url)
    job.run()
    if unsupported or not items:
        return None

    session = getattr(job.extractor, 'session', None)
    base = {k: v for k, v in (session.headers.items() if session else []) if k.lower() not in _GDL_SKIP_HEADERS}
    out = []
    for file_url, ext, extra in items:
        headers = {**base, **extra}
        if session is not None:
            req = requests.Request('GET', file_url).prepare()
            req.prepare_cookies(session.cookies)
            if req.headers.get('Cookie'):
                headers['Cookie'] = req.headers['Cookie']
        if not ext.isalnum():
            ext = os.path.splitext(urlparse(file_url).path)[1].lstrip('.')
        out.append((file_url, ext.lower()[:5] or 'bin', headers))
    return out


async def _run_locked_gallery_dl(fn, *args):
    """Roda fn no pool segurando o lock do config global do gallery-dl. No
    timeout a thread continua; o lock só sai quando ela terminar, senão a
    próxima chamada troca o config no meio. Timeout -> (None, True)."""
    await _GALLERY_DL_LOCK.acquire()
    release_now = True
    try:
        loop = asyncio.get_running_loop()
        job = loop.run_in_executor(state.YTDLP_POOL, fn, *args)
        try:
            return await asyncio.wait_for(asyncio.shield(job), timeout=cfg("SCRAPE_GALLERY_DL_TIMEOUT_S")), False
        except asyncio.TimeoutError:
            job.add_done_callback(lambda _: _GALLERY_DL_LOCK.release())
            release_now = False
            return None, True
        except asyncio.CancelledError:
            job.add_done_callback(lambda _: _GALLERY_DL_LOCK.release())
            release_now = False
            raise
    finally:
        if release_now:
            _GALLERY_DL_LOCK.release()


async def _download_collected(items: list[tuple[str, str, dict]], folder: str) -> tuple[list[str], int]:
    os.makedirs(folder, exist_ok=True)
    sem = asyncio.Semaphore(max(1, cfg("SCRAPE_GALLERY_DL_PARALLEL_FILES")))

    async def _one(num: int, file_url: str, ext: str, headers: dict) -> Optional[str]:
        path = os.path.join(folder, f"galdl_{num:03}.{ext}")
        async with sem:
            ok = await async_download_file_segmented(file_url, path, headers=headers)
        return path if ok else None

    results = await asyncio.gather(*(
        _one(i, u, ext, h) for i, (u, ext, h) in enumerate(items, start=1)
    ))
    files = [r for r in results if r]
    return files, len(items) - len(files)


def _gallery_dl_job_sync(url: str, folder: str) -> None:
    from gallery_dl import config as gdl_config, job as gdl_job

    _load_gallery_dl_config()
    gdl_config.set(('extractor',), 'base-directory', folder + os.sep)
    gdl_config.set(('extractor',), 'directory', [])
    gdl_config.set(('extractor',), 'filename', 'galdl_{num:>03}.{extension}')
    gdl_config.set(('extractor',), 'skip', True)
    try:
        gdl_job.DownloadJob(url).run()
    except Exception as e:
        logger.debug(lmsg("fallback.gallery_dl_job", e=e))


def _gallery_dl_collect_sync(url: str) -> Optional[list[tuple[str, str, dict]]]:
    _load_gallery_dl_config()
    try:
        return _collect_gallery_dl_items(url)
    except Exception as e:
        logger.debug(lmsg("fallback.gallery_dl_job", e=e))
        return None


async def gallery_dl_download(url: str, folder: str) -> tuple[list[str], int]:
    """gallery-dl lista os arquivos e o bot baixa vários ao mesmo tempo, cada um
    em faixas paralelas. Se não der pra listar, usa o download do gallery-dl.
    Retorna (arquivos, faltando); faltando == -1: cortado pelo timeout."""
    if cfg("SCRAPE_GALLERY_DL_ENABLE") != "yes" or not _can_handle_with_gallery_dl(url):
        return [], 0

    try:
        items, timed_out = await _run_locked_gallery_dl(_gallery_dl_collect_sync, url)
    except Exception as e:
        logger.debug(lmsg("fallback.gallery_dl_executor", e=e))
        items, timed_out = None, False
    if timed_out:
        logger.warning(lmsg(
            "fallback.gallery_dl_timeout",
            timeout=cfg("SCRAPE_GALLERY_DL_TIMEOUT_S"), url=safe_url(url),
        ))
        return [], 0
    if items:
        logger.info(lmsg("fallback.gallery_dl_parallel", count=len(items), url=safe_url(url)))
        files, missing = await _download_collected(items, folder)
        if files:
            if missing:
                logger.warning(lmsg("fallback.gallery_dl_incomplete", missing=missing, total=len(items), url=safe_url(url)))
            return files, missing

    files_before = set(_list_files_in(folder))
    try:
        _, timed_out = await _run_locked_gallery_dl(_gallery_dl_job_sync, url, folder)
    except Exception as e:
        logger.debug(lmsg("fallback.gallery_dl_executor", e=e))
        timed_out = False
    if timed_out:
        logger.warning(lmsg(
            "fallback.gallery_dl_timeout",
            timeout=cfg("SCRAPE_GALLERY_DL_TIMEOUT_S"), url=safe_url(url),
        ))
    new_files = sorted(set(_list_files_in(folder)) - files_before)
    return new_files, (-1 if timed_out and new_files else 0)


async def _gallery_dl_run(url: str, folder: str) -> list[str]:
    """Roda gallery-dl pra URL. Útil em galerias (Pinterest, Imgur, Tumblr, etc.)."""
    files, _ = await gallery_dl_download(url, folder)
    return files


async def _ytdlp_generic_iframes(iframes: list[str], folder: str) -> list[str]:
    for iframe_url in iframes:
        logger.info(lmsg("fallback.tentando_yt_dlp", arg0=safe_url(iframe_url)))
        files = await _ytdlp_generic(iframe_url, folder)
        if files:
            return files
    return []


async def take_page_screenshot(folder: str, url: str) -> Optional[str]:
    """Captura screenshot da fold da página. Retorna o path ou None se falhar."""
    if not state.PW_BROWSER or not state.PW_CONTEXT:
        return None
    os.makedirs(folder, exist_ok=True)
    out_path = os.path.join(folder, "screenshot.jpg")
    async with state.PW_SEMAPHORE:
        page = None
        try:
            page = await state.PW_CONTEXT.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=cfg("PW_GOTO_TIMEOUT_MS"))
            await page.wait_for_timeout(2000)
            await page.screenshot(path=out_path, full_page=False, type='jpeg', quality=85)
        except Exception as e:
            logger.warning(lmsg("fallback.falha_screenshot_x", e=e))
            return None
        finally:
            if page is not None:
                try:
                    await page.close()
                except Exception:
                    pass
    if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
        return out_path
    return None


def _build_status(files: list[str], status_key: str) -> str:
    has_video = any(f.endswith('.mp4') for f in files)
    if has_video and len(files) > 1:
        label = msg("media_type_labels.scraper_video_mixed")
    elif has_video:
        label = msg("media_type_labels.scraper_video")
    else:
        label = msg("media_type_labels.scraper_images")
    return msg(status_key, media_type=label, count=len(files))


async def fetch_article_caption(url: str, html: Optional[str] = None) -> tuple[str, str]:
    if cfg("SCRAPE_ARTICLE_EXTRACT") != "yes":
        return "", ""
    if html is None:
        html, _ = await _fetch_html_with_paywall_bypass(
            url, timeout=cfg("SCRAPE_FAST_PATH_TIMEOUT_S"),
        )
    if not html:
        return "", ""
    result = await asyncio.to_thread(extract_article, html, url=url, min_chars=cfg("SCRAPE_ARTICLE_MIN_CHARS"))
    if not result:
        return "", ""
    title, body = result
    short, full = _build_caption({'title': title, 'description': body}, url)
    logger.info(lmsg(
        "fallback.article_detected",
        body_len=len(body), caption_len=len(short), url=safe_url(url),
    ))
    return short, full


async def scrape_fallback(
    url: str, unique_folder: str,
) -> tuple[list[str], str, str, str, bool]:
    logger.info(lmsg("fallback.iniciando_scraping_multi", arg0=safe_url(url)))

    os.makedirs(unique_folder, exist_ok=True)

    pw_available = bool(state.PW_BROWSER and state.PW_CONTEXT)

    if pw_available:
        bypass_result, pw_result = await asyncio.gather(
            _fetch_html_with_paywall_bypass(url, timeout=cfg("SCRAPE_FAST_PATH_TIMEOUT_S")),
            _gather_media_via_playwright(url),
        )
        fast_html, html_source = bypass_result
        pw_media, iframes, page_html = pw_result
    else:
        fast_html, html_source = await _fetch_html_with_paywall_bypass(
            url, timeout=cfg("SCRAPE_FAST_PATH_TIMEOUT_S"),
        )
        pw_media, iframes, page_html = [], [], ""

    paywall_in_pw = _looks_like_paywall(page_html)

    article_short, article_full = await fetch_article_caption(url, html=fast_html or page_html)
    is_article = bool(article_short)
    is_pinterest = _is_pinterest(url)

    if is_article or is_pinterest:
        source_html = fast_html or page_html or ""
        meta_media = extract_meta_media(source_html, url)
        jsonld_media = extract_jsonld_media(source_html, url)
        combined = merge_media_lists(meta_media, jsonld_media, cap=1)
        log_key = "fallback.pinterest_media_filtered" if (is_pinterest and not is_article) else "fallback.article_media_filtered"
        logger.info(lmsg(log_key, n_combined=len(combined)))
    else:
        fast_media = _gather_media_from_html(fast_html, url) if fast_html else []
        combined = merge_media_lists(fast_media, pw_media, cap=cfg("SCRAPE_MAX_MEDIA_URLS"))
        logger.info(lmsg(
            "fallback.combined_stats",
            n_html=len(fast_media), source=html_source, n_pw=len(pw_media),
            n_combined=len(combined), n_iframes=len(iframes),
        ))

    prepared = _prepare_for_download(combined)
    files: list[str] = []
    failed = 0
    if prepared:
        files, failed = await _download_all(prepared, url, unique_folder)

    if files:
        return files, _build_status(files, "downloader_status.scraper"), article_short, article_full, is_article

    logger.info(lmsg("fallback.tentando_yt_dlp_2"))
    yt_files = await _ytdlp_generic(url, unique_folder)
    if yt_files:
        return yt_files, _build_status(yt_files, "downloader_status.scraper_generic_ytdlp"), article_short, article_full, is_article

    logger.info(lmsg("fallback.tentando_gallery_dl"))
    galdl_files = await _gallery_dl_run(url, unique_folder)
    if galdl_files:
        return galdl_files, _build_status(galdl_files, "downloader_status.scraper_gallerydl"), article_short, article_full, is_article

    if iframes:
        iframe_files = await _ytdlp_generic_iframes(iframes, unique_folder)
        if iframe_files:
            return iframe_files, _build_status(iframe_files, "downloader_status.scraper_generic_ytdlp"), article_short, article_full, is_article

    if not pw_available:
        return [], msg("downloader_status.playwright_not_running"), "", "", False

    if paywall_in_pw or (failed > 0 and failed == len(prepared) and prepared):
        return [], msg("downloader_status.scraper_paywall"), "", "", False

    return [], msg("downloader_status.scraper_fail"), "", "", False

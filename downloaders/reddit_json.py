import asyncio
import html
import logging
import os
import re
from urllib.parse import unquote, urljoin

import aiohttp
from curl_cffi import requests as curl_requests

import state
from config import cfg
from cookies import get_aiohttp_cookies_for_url
from messages import lmsg, msg
from utils import async_download_file, normalize_image, safe_url

from .reddit_common import (
    build_reddit_caption, clean_reddit_media_url, is_reddit_media_url, looks_like_image, reddit_external_link,
)

logger = logging.getLogger(__name__)

_REDDIT_GUEST_BOOTSTRAP_URL = "https://old.reddit.com/"
_reddit_session_ready = False

# Desafio JS do Reddit (out/2026): o script só dobra a semente e reenvia o form via GET.
_JSC_SEED_RE = re.compile(r'\(async e=>e\+e\)\("([0-9a-f]+)"\)')
_JSC_ACTION_RE = re.compile(r'<form[^>]*action="([^"]+)"')
_JSC_INPUT_RE = re.compile(r'<input type="hidden" name="(\w+)"(?: value="([^"]*)")?')
_POST_RE = re.compile(r'<shreddit-post\b([^>]*)>(.*?)</shreddit-post>', re.S)
_ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')
_PLAYER_RE = re.compile(r'<shreddit-player\b[^>]*\bsrc="([^"]+)"')
_IREDDIT_RE = re.compile(r'https://i\.redd\.it/[^"?&\s]+')
_TEXT_BODY_RE = re.compile(r'-post-rtjson-content"[^>]*>(.*?)</div>', re.S)
_BLOCK_END_RE = re.compile(r'</(?:p|li|h\d|blockquote|pre)>|<br\s*/?>')
_TAG_RE = re.compile(r'<[^>]+>')


def _reddit_json_headers() -> dict:
    return {
        'User-Agent': cfg("REDDIT_JSON_UA"),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'pt-BR,pt;q=0.8,en-US;q=0.5,en;q=0.3',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
    }


async def _ensure_reddit_session(force: bool = False) -> None:
    global _reddit_session_ready
    if _reddit_session_ready and not force:
        return
    try:
        async with state.AIOHTTP_SESSION.get(
            _REDDIT_GUEST_BOOTSTRAP_URL, headers=_reddit_json_headers(),
            allow_redirects=True, timeout=15,
        ) as resp:
            await resp.read()
        _reddit_session_ready = True
        logger.info(lmsg("reddit_json.sessao_anonima_ok"))
    except Exception as e:
        logger.debug(lmsg("reddit_json.sessao_anonima_falhou", e=e))


async def _fetch_reddit_post_data(url: str) -> dict:
    await _ensure_reddit_session()
    cookies_dict = dict(get_aiohttp_cookies_for_url(url) or {})
    cookies_dict.setdefault('over18', '1')
    if cookies_dict:
        logger.info(lmsg("reddit_json.usando_x_cookies", arg0=len(cookies_dict)))
    clean_url = url.split('?')[0].rstrip('/')
    json_url = f"{clean_url}.json?raw_json=1"

    async def _get() -> dict:
        async with state.AIOHTTP_SESSION.get(json_url, headers=_reddit_json_headers(), cookies=cookies_dict, timeout=15) as resp:
            resp.raise_for_status()
            data = await resp.json()
        return data[0]['data']['children'][0]['data']

    try:
        return await _get()
    except aiohttp.ClientResponseError as e:
        if e.status not in (403, 429):
            raise
        await _ensure_reddit_session(force=True)
    try:
        return await _get()
    except aiohttp.ClientResponseError as e:
        if e.status != 403:
            raise
    # Desde out/2026 a API JSON dá 403 pra anônimo; a página do post ainda abre.
    logger.info(lmsg("reddit_json.usando_pagina_html"))
    return _post_data_from_html(await _fetch_reddit_page(clean_url + '/'))


def _fetch_reddit_page_sync(url: str) -> str:
    # aiohttp leva 403 mesmo resolvendo o desafio; precisa da digital TLS de navegador.
    # O link /s/ do app redireciona com o slug codificado duas vezes (hist%25C3%25B3ria),
    # e a página não acha o post; a API JSON ia pelo ID e não ligava.
    if '%25' in url:
        url = unquote(url)
    with curl_requests.Session(impersonate="firefox", timeout=15) as s:
        r = s.get(url)
        seed = _JSC_SEED_RE.search(r.text)
        if seed:
            fields = {k: html.unescape(v) for k, v in _JSC_INPUT_RE.findall(r.text)}
            fields['solution'] = seed.group(1) * 2
            action = _JSC_ACTION_RE.search(r.text)
            r = s.get(urljoin(url, html.unescape(action.group(1))) if action else url, params=fields)
        r.raise_for_status()
        return r.text


async def _fetch_reddit_page(url: str) -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(state.IO_POOL, _fetch_reddit_page_sync, url)


def _text_body(body: str) -> str:
    """Texto do post (corpo em HTML) com um parágrafo por linha em branco."""
    m = _TEXT_BODY_RE.search(body)
    if not m:
        return ''
    text = html.unescape(_TAG_RE.sub('', _BLOCK_END_RE.sub('\n', m.group(1))))
    return '\n\n'.join(ln.strip() for ln in text.splitlines() if ln.strip())


def _post_data_from_html(page: str) -> dict:
    """Monta, a partir do <shreddit-post>, um dict com os campos do JSON que o
    resto do fluxo usa. `_media_urls` traz as imagens (i.redd.it) na ordem e
    `_hls_url` o stream do vídeo, que o dispatcher entrega pro yt-dlp."""
    m = _POST_RE.search(page)
    if not m:
        raise ValueError("shreddit-post não encontrado na página do Reddit")
    attrs = {k: html.unescape(v) for k, v in _ATTR_RE.findall(m.group(1))}
    body = m.group(2)
    post_type = attrs.get('post-type', '')
    player = _PLAYER_RE.search(body)
    data = {
        'title': attrs.get('post-title', ''),
        'selftext': _text_body(body),
        # crosspost traz o permalink do original, relativo
        'url': urljoin('https://www.reddit.com/', attrs.get('content-href', '')),
        'domain': attrs.get('domain', ''),
        'is_self': post_type == 'text',
        'is_video': post_type == 'video' or (post_type == 'crosspost' and bool(player)),
    }
    if player:
        data['_hls_url'] = html.unescape(player.group(1))
    if not player:
        # Alguns posts vêm sem post-type nem <img> no corpo; aí só sobra o content-href.
        urls = [u for u in _IREDDIT_RE.findall(body) if is_reddit_media_url(u)]
        if not urls and looks_like_image(data['url']):
            urls = [data['url']]
        if urls and post_type not in ('text', 'link'):
            data['_media_urls'] = list(dict.fromkeys(urls))
    return data


async def resolve_reddit_external_link(url: str) -> tuple["dict | None", "dict | None"]:
    """Retorna (link, post_data). `link` é o dict do link externo (ou None se o
    post for mídia nativa/texto); `post_data` é reaproveitado por
    download_reddit_json pra não buscar o JSON duas vezes."""
    try:
        post_data = await _fetch_reddit_post_data(url)
    except Exception as e:
        logger.debug(lmsg("reddit_json.erro_ao_ler", e=e))
        return None, None
    return reddit_external_link(post_data), post_data


async def _is_gone(media_url: str) -> bool:
    """i.redd.it responde 404 (com um PNG genérico) quando a mídia foi apagada."""
    try:
        async with state.AIOHTTP_SESSION.head(media_url, timeout=15) as resp:
            return resp.status == 404
    except Exception:
        return False


async def download_reddit_json(
    url: str, unique_folder: str, post_data: "dict | None" = None,
) -> tuple[list[str], str, str, str]:
    logger.info(lmsg("reddit_json.iniciando_extra_o_via", arg0=safe_url(url)))
    os.makedirs(unique_folder, exist_ok=True)

    media_urls = []
    downloaded_files = []
    title = ""
    selftext = ""

    try:
        if post_data is None:
            post_data = await _fetch_reddit_post_data(url)
        title = post_data.get('title', '') or ''
        selftext = post_data.get('selftext', '') or ''

        media_src = post_data
        crosspost_parents = post_data.get('crosspost_parent_list') or []
        if crosspost_parents:
            media_src = crosspost_parents[-1]
            logger.info(lmsg("reddit_json.crosspost_detectado"))
            if not selftext:
                selftext = media_src.get('selftext', '') or ''

        if media_src.get('is_video') or media_src.get('post_hint') in ('hosted:video', 'rich:video'):
            logger.info(lmsg("reddit_json.post_v_deo"))
            return [], msg("downloader_status.reddit_json_fail"), "", ""

        if media_src.get('_media_urls'):
            media_urls = [u for u in map(clean_reddit_media_url, media_src['_media_urls']) if u]

        elif 'media_metadata' in media_src:
            metadata = media_src['media_metadata']
            gallery_items = media_src.get('gallery_data', {}).get('items', [])
            if gallery_items:
                infos = [metadata.get(item['media_id'], {}) for item in gallery_items]
            else:
                infos = list(metadata.values())
            for media_info in infos:
                if media_info.get('status') != 'valid':
                    continue
                src = media_info.get('s', {})
                clean_u = clean_reddit_media_url(src.get('u') or src.get('gif'))
                if clean_u and clean_u not in media_urls:
                    media_urls.append(clean_u)

        elif 'url' in media_src and looks_like_image(media_src['url']):
            clean_u = clean_reddit_media_url(media_src['url'])
            if clean_u and clean_u not in media_urls: media_urls.append(clean_u)

        elif 'preview' in media_src and 'images' in media_src['preview']:
            img_url = media_src['preview']['images'][0]['source']['url']
            clean_u = clean_reddit_media_url(img_url)
            if clean_u and clean_u not in media_urls: media_urls.append(clean_u)

    except Exception as e:
        logger.error(lmsg("reddit_json.erro_ao_ler", e=e), exc_info=True)

    count = 0
    for m_url in media_urls:
        try:
            ext = ".jpg" if not m_url[-4:].startswith('.') else m_url[-4:]
            filepath = os.path.join(unique_folder, f"reddit_media_{count}{ext}")

            success = await async_download_file(m_url, filepath)

            if success:
                if not filepath.lower().endswith(('.mp4', '.gif', '.webm')):
                    normalized = await asyncio.to_thread(normalize_image, filepath, min_size=1)
                    if normalized is None:
                        continue
                    filepath = normalized

                downloaded_files.append(filepath)
                count += 1
        except Exception as e:
            logger.error(lmsg("reddit_json.erro_ao_processar", e=e))

    if downloaded_files:
        caption_short, caption_full = build_reddit_caption(title, selftext, url)
        return downloaded_files, msg("downloader_status.reddit_json"), caption_short, caption_full
    if (post_data or {}).get('is_self') and (title or selftext):
        caption_short, caption_full = build_reddit_caption(title, selftext, url)
        return [], msg("downloader_status.reddit_text_only"), caption_short, caption_full
    # só posts lidos da página (`_media_urls`); a API JSON já não responde
    if (post_data or {}).get('_media_urls') and media_urls and await _is_gone(media_urls[0]):
        return [], msg("downloader_status.reddit_media_removed"), "", ""
    return [], msg("downloader_status.reddit_json_fail"), "", ""

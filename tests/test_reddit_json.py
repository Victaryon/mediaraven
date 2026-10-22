"""Testes de integração do download_reddit_json com aiohttp mockado."""
import os
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest

import state
from downloaders import reddit_json


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    async def json(self):
        return self._payload

    async def read(self):
        return b""


@asynccontextmanager
async def _fake_get_ctx(payload):
    yield _FakeResponse(payload)


def _make_session_mock(payload):
    session = AsyncMock()
    # Emular session.get(...) retornando um async context manager
    session.get = lambda *a, **kw: _fake_get_ctx(payload)
    return session


@pytest.fixture(autouse=True)
def _reset_state():
    state.FIREFOX_COOKIES_CACHE = []
    reddit_json._reddit_session_ready = False
    yield
    state.FIREFOX_COOKIES_CACHE = []
    reddit_json._reddit_session_ready = False


@pytest.mark.asyncio
async def test_reddit_json_gallery_items(tmp_path):
    """Gallery com gallery_data.items: deve extrair cada media_id na ordem."""
    folder = str(tmp_path / "task")
    os.makedirs(folder)
    payload = [
        {'data': {'children': [{'data': {
            'gallery_data': {'items': [{'media_id': 'aaa'}, {'media_id': 'bbb'}]},
            'media_metadata': {
                'aaa': {'status': 'valid', 's': {'u': 'https://preview.redd.it/aaa.jpg?x=1'}},
                'bbb': {'status': 'valid', 's': {'u': 'https://preview.redd.it/bbb.jpg?y=2'}},
            },
        }}]}}
    ]
    state.AIOHTTP_SESSION = _make_session_mock(payload)
    with patch.object(reddit_json, 'async_download_file', new=AsyncMock(return_value=False)):
        files, status, _short, _full = await reddit_json.download_reddit_json("https://reddit.com/r/x/comments/z/", folder)

    # Como o download mockou False, files fica vazio; o que queremos validar é o fluxo sem explodir.
    assert files == []
    assert status


@pytest.mark.asyncio
async def test_reddit_json_single_image_url(tmp_path):
    folder = str(tmp_path / "task")
    os.makedirs(folder)
    payload = [
        {'data': {'children': [{'data': {
            'url': 'https://preview.redd.it/single.png?a=1',
        }}]}}
    ]
    state.AIOHTTP_SESSION = _make_session_mock(payload)

    captured_urls = []

    async def fake_download(url, filepath):
        captured_urls.append(url)
        with open(filepath, 'wb') as f:
            f.write(b"fakebytes")
        return True

    with patch.object(reddit_json, 'async_download_file', new=AsyncMock(side_effect=fake_download)), \
         patch.object(reddit_json, 'normalize_image', side_effect=lambda p, **kw: p):
        files, status, _short, _full = await reddit_json.download_reddit_json("https://reddit.com/r/x/comments/z/", folder)

    assert len(files) == 1
    assert captured_urls == ["https://i.redd.it/single.png"]


@pytest.mark.asyncio
async def test_reddit_json_preview_images_fallback(tmp_path):
    folder = str(tmp_path / "task")
    os.makedirs(folder)
    payload = [
        {'data': {'children': [{'data': {
            'preview': {'images': [{'source': {'url': 'https://preview.redd.it/prev.jpg?a=1'}}]},
        }}]}}
    ]
    state.AIOHTTP_SESSION = _make_session_mock(payload)

    captured = []

    async def fake_download(url, filepath):
        captured.append(url)
        return False

    with patch.object(reddit_json, 'async_download_file', new=AsyncMock(side_effect=fake_download)):
        files, status, _short, _full = await reddit_json.download_reddit_json("https://reddit.com/r/x/comments/z/", folder)

    assert captured == ["https://i.redd.it/prev.jpg"]
    assert files == []


@pytest.mark.asyncio
async def test_reddit_json_crosspost_extracts_from_parent(tmp_path):
    """Crosspost: a mídia está em crosspost_parent_list, não no nível de cima."""
    folder = str(tmp_path / "task")
    os.makedirs(folder)
    payload = [
        {'data': {'children': [{'data': {
            'title': 'olha isso',
            'url': 'https://www.reddit.com/r/orig/comments/pai/',
            'crosspost_parent_list': [{
                'url': 'https://preview.redd.it/xpost.jpg?a=1',
            }],
        }}]}}
    ]
    state.AIOHTTP_SESSION = _make_session_mock(payload)

    captured = []

    async def fake_download(url, filepath):
        captured.append(url)
        with open(filepath, 'wb') as f:
            f.write(b"fakebytes")
        return True

    with patch.object(reddit_json, 'async_download_file', new=AsyncMock(side_effect=fake_download)), \
         patch.object(reddit_json, 'normalize_image', side_effect=lambda p, **kw: p):
        files, status, _short, _full = await reddit_json.download_reddit_json("https://reddit.com/r/x/comments/z/", folder)

    assert captured == ["https://i.redd.it/xpost.jpg"]
    assert len(files) == 1


@pytest.mark.asyncio
async def test_reddit_json_crosspost_gallery_from_parent(tmp_path):
    """Crosspost de galeria: media_metadata/gallery_data no parent."""
    folder = str(tmp_path / "task")
    os.makedirs(folder)
    payload = [
        {'data': {'children': [{'data': {
            'title': 'xpost galeria',
            'crosspost_parent_list': [{
                'gallery_data': {'items': [{'media_id': 'aaa'}, {'media_id': 'bbb'}]},
                'media_metadata': {
                    'aaa': {'status': 'valid', 's': {'u': 'https://preview.redd.it/aaa.jpg?x=1'}},
                    'bbb': {'status': 'valid', 's': {'u': 'https://preview.redd.it/bbb.jpg?y=2'}},
                },
            }],
        }}]}}
    ]
    state.AIOHTTP_SESSION = _make_session_mock(payload)

    captured = []

    async def fake_download(url, filepath):
        captured.append(url)
        return False

    with patch.object(reddit_json, 'async_download_file', new=AsyncMock(side_effect=fake_download)):
        await reddit_json.download_reddit_json("https://reddit.com/r/x/comments/z/", folder)

    assert captured == ["https://i.redd.it/aaa.jpg", "https://i.redd.it/bbb.jpg"]


@pytest.mark.asyncio
async def test_reddit_json_crosspost_video_parent_delegates(tmp_path):
    """Crosspost de vídeo: detecta is_video no parent e delega pro yt-dlp."""
    folder = str(tmp_path / "task")
    os.makedirs(folder)
    payload = [
        {'data': {'children': [{'data': {
            'title': 'xpost video',
            'crosspost_parent_list': [{'is_video': True}],
        }}]}}
    ]
    state.AIOHTTP_SESSION = _make_session_mock(payload)
    files, status, _short, _full = await reddit_json.download_reddit_json("https://reddit.com/r/x/comments/z/", folder)
    assert files == []


@pytest.mark.asyncio
async def test_reddit_json_bootstraps_session_and_retries_on_403(tmp_path):
    """403 na primeira tentativa -> refaz bootstrap de sessão e tenta de novo."""
    folder = str(tmp_path / "task")
    os.makedirs(folder)
    payload = [
        {'data': {'children': [{'data': {
            'url': 'https://preview.redd.it/ok.png?a=1',
        }}]}}
    ]

    calls = {'json': 0, 'bootstrap': 0}

    @asynccontextmanager
    async def _get_ctx(u, *a, **kw):
        if u == reddit_json._REDDIT_GUEST_BOOTSTRAP_URL:
            calls['bootstrap'] += 1
            yield _FakeResponse(None)
            return
        calls['json'] += 1
        if calls['json'] == 1:
            raise aiohttp.ClientResponseError(None, None, status=403, message='Blocked')
        yield _FakeResponse(payload)

    session = AsyncMock()
    session.get = lambda u, *a, **kw: _get_ctx(u, *a, **kw)
    state.AIOHTTP_SESSION = session

    async def fake_download(url, filepath):
        with open(filepath, 'wb') as f:
            f.write(b"x")
        return True

    with patch.object(reddit_json, 'async_download_file', new=AsyncMock(side_effect=fake_download)), \
         patch.object(reddit_json, 'normalize_image', side_effect=lambda p, **kw: p):
        files, status, _short, _full = await reddit_json.download_reddit_json("https://reddit.com/r/x/comments/z/", folder)

    assert calls['json'] == 2
    assert calls['bootstrap'] == 2  # bootstrap inicial + re-bootstrap após 403
    assert len(files) == 1


@pytest.mark.asyncio
async def test_reddit_json_handles_malformed(tmp_path):
    """JSON quebrado não deve derrubar o bot — retorna lista vazia."""
    folder = str(tmp_path / "task")
    os.makedirs(folder)
    state.AIOHTTP_SESSION = _make_session_mock([])
    files, status, _short, _full = await reddit_json.download_reddit_json("https://reddit.com/r/x/comments/z/", folder)
    assert files == []
    assert status


def test_post_data_from_html_gallery_e_video():
    """Página do shreddit (API JSON bloqueada): galeria em ordem, sem junk; vídeo traz o HLS do post."""
    gallery = (
        '<shreddit-post post-type="gallery" post-title="Tit &#39;x&#39;" '
        'content-href="https://www.reddit.com/gallery/abc" domain="reddit.com">'
        '<img src="https://i.redd.it/um.jpeg"><img data-lazy-src="https://preview.redd.it/x-v0-um.jpeg?width=640">'
        '<img src="https://i.redd.it/dois.png"><img src="https://i.redd.it/um.jpeg">'
        '<img src="https://i.redd.it/snoovatar/avatars/a.png"></shreddit-post>'
        '<img src="https://i.redd.it/fora_do_post.png">'
    )
    d = reddit_json._post_data_from_html(gallery)
    assert d['title'] == "Tit 'x'"
    assert d['_media_urls'] == ['https://i.redd.it/um.jpeg', 'https://i.redd.it/dois.png']
    assert reddit_json.reddit_external_link(d) is None

    video = (
        '<shreddit-post post-type="video" post-title="V" content-href="https://v.redd.it/abc" domain="v.redd.it">'
        '<shreddit-player src="https://v.redd.it/abc/HLSPlaylist.m3u8?f=sd&amp;a=1"></shreddit-post>'
        '<shreddit-player src="https://v.redd.it/anuncio/HLSPlaylist.m3u8">'
    )
    d = reddit_json._post_data_from_html(video)
    assert d['is_video'] and d['_hls_url'] == 'https://v.redd.it/abc/HLSPlaylist.m3u8?f=sd&a=1'
    assert '_media_urls' not in d

    sem_tipo = '<shreddit-post post-title="S" content-href="https://i.redd.it/so.jpeg" domain="i.redd.it"></shreddit-post>'
    assert reddit_json._post_data_from_html(sem_tipo)['_media_urls'] == ['https://i.redd.it/so.jpeg']

    crosspost = video.replace('post-type="video"', 'post-type="crosspost"').replace(
        'content-href="https://v.redd.it/abc"', 'content-href="/r/orig/comments/q/t/"')
    d = reddit_json._post_data_from_html(crosspost)
    assert d['is_video'] and d['url'] == 'https://www.reddit.com/r/orig/comments/q/t/'
    assert reddit_json.reddit_external_link(d) is None


def test_fetch_reddit_page_resolve_desafio_js():
    desafio = (
        '<form hidden method="GET" action="/r/x/comments/z/t/"><input type="hidden" name="solution" />'
        '<input type="hidden" name="js_challenge" value="1"/><input type="hidden" name="jsc_token" value="tok"/>'
        '</form><script>await(async e=>e+e)("ab12")</script>'
    )
    calls = []

    class _Resp:
        def __init__(self, text):
            self.text = text

        def raise_for_status(self):
            pass

    class _Session:
        def __init__(self, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def get(self, url, params=None):
            calls.append((url, params))
            return _Resp(desafio if params is None else "<shreddit-post></shreddit-post>")

    with patch.object(reddit_json.curl_requests, 'Session', _Session):
        page = reddit_json._fetch_reddit_page_sync("https://www.reddit.com/r/x/comments/z/t%25C3%25A9/")
    assert page == "<shreddit-post></shreddit-post>"
    assert calls[0][0] == "https://www.reddit.com/r/x/comments/z/t%C3%A9/"
    assert calls[1] == ("https://www.reddit.com/r/x/comments/z/t/",
                        {'solution': 'ab12ab12', 'js_challenge': '1', 'jsc_token': 'tok'})


@pytest.mark.asyncio
async def test_reddit_midia_removida(tmp_path):
    """Imagem que dá 404 no i.redd.it vira status de mídia removida, não falha genérica."""
    @asynccontextmanager
    async def fake_head(url, **kw):
        yield type("R", (), {"status": 404})()

    session = AsyncMock()
    session.head = fake_head
    state.AIOHTTP_SESSION = session
    post = {'title': 'T', '_media_urls': ['https://i.redd.it/apagada.jpeg']}
    with patch.object(reddit_json, 'async_download_file', new=AsyncMock(return_value=False)):
        files, status, _s, _f = await reddit_json.download_reddit_json(
            "https://reddit.com/r/x/comments/z/", str(tmp_path), post_data=post)
    assert files == []
    assert status == reddit_json.msg("downloader_status.reddit_media_removed")


@pytest.mark.asyncio
async def test_post_de_texto_vem_so_com_legenda(tmp_path):
    page = (
        '<shreddit-post post-type="text" post-title="T" content-href="https://www.reddit.com/r/x/comments/z/t/" '
        'domain="self.x"><div id="t3_z-post-rtjson-content" class="md">'
        '<p>\n  Um &quot;a&quot;\n</p><p><a href="u">dois</a><br>tr&ecirc;s</p></div></shreddit-post>'
    )
    d = reddit_json._post_data_from_html(page)
    assert d['selftext'] == 'Um "a"\n\ndois\n\ntrês'
    assert '_media_urls' not in d
    files, status, short, full = await reddit_json.download_reddit_json(
        'https://www.reddit.com/r/x/comments/z/t/', str(tmp_path), post_data=d)
    assert files == [] and "Um &quot;a&quot;" in full and status == reddit_json.msg("downloader_status.reddit_text_only")

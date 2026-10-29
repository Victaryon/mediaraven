"""Download em faixas paralelas (Range) e o caminho listar-e-baixar do gallery-dl."""
import os
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest
from aiohttp import web

import state
import utils
from downloaders import fallback
from utils import async_download_file_segmented

PAYLOAD = os.urandom(utils.SEGMENT_MIN_BYTES + 12345)


async def _serve(handler):
    app = web.Application()
    app.router.add_get("/f", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    return runner, f"http://127.0.0.1:{port}/f"


def _range_handler(ranges_seen, fail_once=None):
    async def handler(request):
        rng = request.headers.get("Range")
        ranges_seen.append(rng)
        start, end = (int(x) for x in rng.split("=")[1].split("-"))
        body = PAYLOAD[start:end + 1]
        if fail_once is not None and start == fail_once and end > start and not fail_once_done:
            fail_once_done.append(True)
            body = body[: len(body) // 2]  # corta a conexão no meio da faixa
            resp = web.StreamResponse(status=206, headers={
                "Content-Range": f"bytes {start}-{end}/{len(PAYLOAD)}",
                "Content-Length": str(end - start + 1),
            })
            await resp.prepare(request)
            await resp.write(body)
            request.transport.close()
            return resp
        return web.Response(status=206, body=body, headers={
            "Content-Range": f"bytes {start}-{end}/{len(PAYLOAD)}",
            "Content-Type": "video/mp4",
        })
    fail_once_done: list = []
    return handler


@pytest.mark.asyncio
async def test_segmented_download_reassembles_file(tmp_path):
    seen: list = []
    runner, url = await _serve(_range_handler(seen))
    state.AIOHTTP_SESSION = aiohttp.ClientSession()
    try:
        out = tmp_path / "v.mp4"
        assert await async_download_file_segmented(url, str(out), segments=4) is True
        assert out.read_bytes() == PAYLOAD
        assert len(seen) == 1 + 4  # sonda + 4 faixas
    finally:
        await state.AIOHTTP_SESSION.close()
        await runner.cleanup()


@pytest.mark.asyncio
async def test_segmented_download_resumes_cut_range(tmp_path):
    seen: list = []
    runner, url = await _serve(_range_handler(seen, fail_once=0))
    state.AIOHTTP_SESSION = aiohttp.ClientSession()
    try:
        out = tmp_path / "v.mp4"
        assert await async_download_file_segmented(url, str(out), segments=2) is True
        assert out.read_bytes() == PAYLOAD
        # a faixa cortada é retomada do meio, não do zero
        size = -(-len(PAYLOAD) // 2)
        starts = {int(r.split("=")[1].split("-")[0]) for r in seen[1:]}
        assert starts - {0, size}
    finally:
        await state.AIOHTTP_SESSION.close()
        await runner.cleanup()


@pytest.mark.asyncio
async def test_segmented_download_without_range_uses_plain_download(tmp_path):
    async def handler(request):
        return web.Response(body=PAYLOAD, content_type="video/mp4")

    runner, url = await _serve(handler)
    state.AIOHTTP_SESSION = aiohttp.ClientSession()
    try:
        out = tmp_path / "v.mp4"
        assert await async_download_file_segmented(url, str(out), segments=4) is True
        assert out.read_bytes() == PAYLOAD
    finally:
        await state.AIOHTTP_SESSION.close()
        await runner.cleanup()


@pytest.mark.asyncio
async def test_gallery_dl_download_reports_missing_files(tmp_path):
    items = [("https://x/a.jpg", "jpg", {}), ("https://x/b.mp4", "mp4", {})]

    async def fake_dl(url, path, headers=None):
        if url.endswith(".mp4"):
            return False
        open(path, "wb").write(b"x")
        return True

    with patch.object(fallback, "_can_handle_with_gallery_dl", return_value=True), \
         patch.object(fallback, "_run_locked_gallery_dl", AsyncMock(return_value=(items, False))), \
         patch.object(fallback, "async_download_file_segmented", side_effect=fake_dl):
        files, missing = await fallback.gallery_dl_download("https://www.artstation.com/artwork/x", str(tmp_path))
    assert [os.path.basename(f) for f in files] == ["galdl_001.jpg"]
    assert missing == 1


@pytest.mark.asyncio
async def test_gallery_dl_download_falls_back_to_job_when_not_listable(tmp_path):
    calls = []

    async def fake_locked(fn, *args):
        calls.append(fn)
        if fn is fallback._gallery_dl_collect_sync:
            return None, False
        open(os.path.join(str(tmp_path), "galdl_001.jpg"), "wb").write(b"x")
        return None, False

    with patch.object(fallback, "_can_handle_with_gallery_dl", return_value=True), \
         patch.object(fallback, "_run_locked_gallery_dl", side_effect=fake_locked):
        files, missing = await fallback.gallery_dl_download("https://example.com/g", str(tmp_path))
    assert calls == [fallback._gallery_dl_collect_sync, fallback._gallery_dl_job_sync]
    assert len(files) == 1 and missing == 0

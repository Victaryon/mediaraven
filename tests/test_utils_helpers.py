"""Testes dos helpers puros de utils: safe_url, normalize_image e chunk_html_text."""
import asyncio
import os
from unittest.mock import patch

import pytest

from PIL import Image

from config import cfg
from utils import chunk_html_text, is_ignored_domain, normalize_image, safe_url


def test_is_ignored_domain_exact_match():
    assert is_ignored_domain("https://twitch.tv/foo", ["twitch.tv"]) is True


def test_is_ignored_domain_matches_subdomain():
    assert is_ignored_domain("https://www.twitch.tv/foo", ["twitch.tv"]) is True
    assert is_ignored_domain("https://m.example.com/x?y=1", ["example.com"]) is True


def test_is_ignored_domain_does_not_match_sibling_or_suffix():
    assert is_ignored_domain("https://nottwitch.tv/foo", ["twitch.tv"]) is False
    assert is_ignored_domain("https://example.com.evil.com/", ["example.com"]) is False


def test_is_ignored_domain_case_insensitive_and_port():
    assert is_ignored_domain("https://WWW.Example.COM:8080/p", ["example.com"]) is True


def test_is_ignored_domain_handles_leading_dot_and_whitespace_entries():
    assert is_ignored_domain("https://example.com/", [" .example.com "]) is True


def test_is_ignored_domain_empty_or_invalid_inputs():
    assert is_ignored_domain("https://example.com", []) is False
    assert is_ignored_domain("https://example.com", None) is False
    assert is_ignored_domain("https://example.com", "example.com") is False
    assert is_ignored_domain("not a url", ["example.com"]) is False


def test_chunk_html_text_returns_single_when_below_limit():
    assert chunk_html_text("oi", 100) == ["oi"]


def test_chunk_html_text_empty():
    assert chunk_html_text("", 100) == []


def test_chunk_html_text_prefers_paragraph_break():
    text = "primeiro\n\nsegundo\n\nterceiro"
    out = chunk_html_text(text, 12)
    assert out[0] == "primeiro"
    assert "segundo" in out[1] or out[1].startswith("segundo")


def test_chunk_html_text_chunks_under_limit():
    text = "abc\n\n" + "x" * 50 + "\n\n" + "y" * 50
    out = chunk_html_text(text, 60)
    for chunk in out:
        assert len(chunk) <= 60


def test_chunk_html_text_preserves_full_content():
    text = ("palavra " * 200).strip()
    out = chunk_html_text(text, 80)
    rejoined = " ".join(out)
    assert "palavra" * 1 in rejoined
    assert rejoined.count("palavra") == 200


def test_chunk_html_text_preserves_html_tags_when_in_separate_lines():
    """tag <b> no header e <a> no rodapé separados por \\n\\n: chunks ficam balanceados."""
    text = "<b>Header</b>\n\n" + "x" * 1000 + "\n\n<a href='u'>link</a>"
    out = chunk_html_text(text, 400)
    for chunk in out:
        assert chunk.count("<b>") == chunk.count("</b>")
        assert chunk.count("<a ") == chunk.count("</a>")


def test_safe_url_strips_query():
    assert safe_url("https://example.com/path?token=secret") == "https://example.com/path"


def test_safe_url_strips_fragment():
    assert safe_url("https://example.com/page#section") == "https://example.com/page"


def test_safe_url_truncates_long_url():
    long_url = "https://example.com/" + "a" * 500
    out = safe_url(long_url)
    assert len(out) <= cfg("SAFE_URL_MAX_LENGTH") + len("...(truncated)")
    assert out.endswith("...(truncated)")


def test_safe_url_invalid_input():
    assert safe_url(None) == "<invalid-url>"  # type: ignore[arg-type]


def test_safe_url_respects_custom_max_length():
    out = safe_url("https://x.com/" + "a" * 100, max_length=30)
    assert "...(truncated)" in out


def _make_png(path, size=(100, 100), mode="RGB", color=(255, 0, 0)):
    img = Image.new(mode, size, color)
    img.save(path, "PNG")


def test_normalize_image_passes_through_rgb(tmp_path):
    p = str(tmp_path / "ok.jpg")
    Image.new("RGB", (800, 600), (0, 255, 0)).save(p, "JPEG")
    out = normalize_image(p, min_size=100)
    assert out == p
    assert os.path.exists(p)


def test_normalize_image_converts_rgba_to_jpg(tmp_path):
    p = str(tmp_path / "alpha.png")
    Image.new("RGBA", (400, 400), (0, 0, 0, 128)).save(p, "PNG")
    out = normalize_image(p, min_size=100)
    assert out is not None
    assert out.endswith(".jpg")
    assert os.path.exists(out)
    # Original com extensão diferente é apagado.
    assert not os.path.exists(p)


def test_normalize_image_rejects_tiny(tmp_path):
    p = str(tmp_path / "tiny.jpg")
    Image.new("RGB", (10, 10), (0, 0, 0)).save(p, "JPEG")
    assert normalize_image(p, min_size=50) is None
    assert not os.path.exists(p)


def test_normalize_image_rejects_garbage(tmp_path):
    p = str(tmp_path / "not_image.jpg")
    with open(p, "wb") as f:
        f.write(b"definitely not a PNG")
    assert normalize_image(p) is None
    assert not os.path.exists(p)


class _FakeContent:
    def __init__(self, chunks, fail_after):
        self._chunks = chunks
        self._fail_after = fail_after

    async def iter_chunked(self, _size):
        for i, chunk in enumerate(self._chunks):
            if i == self._fail_after:
                raise asyncio.TimeoutError()
            yield chunk


class _FakeResponse:
    def __init__(self, content):
        self.status = 200
        self.headers = {'Content-Type': 'video/mp4'}
        self.content = content

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    def __init__(self, response):
        self.response = response
        self.kwargs = None

    def get(self, url, **kwargs):
        self.kwargs = kwargs
        return self.response


@pytest.mark.asyncio
async def test_async_download_file_removes_partial_file(tmp_path):
    import state
    from utils import async_download_file

    target = tmp_path / "video.mp4"
    session = _FakeSession(_FakeResponse(_FakeContent([b'a' * 10, b'b' * 10], fail_after=1)))
    with patch.object(state, 'AIOHTTP_SESSION', session):
        ok = await async_download_file("https://cdn.example/v.mp4", str(target))

    assert ok is False
    assert not target.exists()


@pytest.mark.asyncio
async def test_async_download_file_timeout_is_per_read(tmp_path):
    import state
    from utils import async_download_file

    session = _FakeSession(_FakeResponse(_FakeContent([b'x' * 10], fail_after=-1)))
    with patch.object(state, 'AIOHTTP_SESSION', session):
        ok = await async_download_file("https://cdn.example/v.mp4", str(tmp_path / "v.mp4"))

    assert ok is True
    timeout = session.kwargs['timeout']
    assert timeout.total is None
    assert timeout.sock_read == cfg("DOWNLOAD_TIMEOUT_SECONDS")


def test_dedupe_identical_files_drops_copies(tmp_path):
    from utils import dedupe_identical_files

    a = tmp_path / "x-1.mp4"
    b = tmp_path / "x-2.mp4"
    c = tmp_path / "y-3.mp4"
    a.write_bytes(b"same")
    b.write_bytes(b"same")
    c.write_bytes(b"diff")

    kept = dedupe_identical_files([str(a), str(b), str(c)])

    assert kept == [str(a), str(c)]
    assert not b.exists()


def test_prefers_gallery_dl_only_when_ytdlp_is_generic():
    from downloaders.fallback import prefers_gallery_dl

    assert prefers_gallery_dl("https://www.artstation.com/artwork/AbCd12") is True
    assert prefers_gallery_dl("https://vimeo.com/76979871") is False
    assert prefers_gallery_dl("https://example.com/qualquer") is False

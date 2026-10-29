import asyncio
import hashlib
import logging
import os
import shutil
import time
from typing import Any, Optional
from urllib.parse import urlparse, urlunparse

import aiofiles
import aiohttp
from PIL import Image
from telegram.error import RetryAfter

import state
from config import cfg
from messages import lmsg, msg_list

logger = logging.getLogger(__name__)


def chunk_html_text(text: str, limit: int) -> list[str]:
    """Quebra texto em pedaços ≤ limit, preferindo \\n\\n > \\n > '. ' > espaço.

    Assume que tags HTML do input ficam em linhas próprias (caso do
    _build_caption: <b>...</b> no header, <a>...</a> no rodapé). Quebrar em
    \\n\\n ou \\n preserva tags balanceadas.
    """
    if not text:
        return []
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text
    min_split = max(1, limit // 3)
    while len(remaining) > limit:
        split_at = -1
        for sep in ("\n\n", "\n", ". ", " "):
            pos = remaining.rfind(sep, 0, limit)
            if pos >= min_split:
                split_at = pos + (1 if sep == ". " else 0)
                break
        if split_at <= 0:
            split_at = limit
        chunk = remaining[:split_at].rstrip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[split_at:].lstrip()

    if remaining:
        chunks.append(remaining)
    return chunks


def safe_url(url: str, max_length: Optional[int] = None) -> str:
    if max_length is None:
        max_length = cfg("SAFE_URL_MAX_LENGTH")
    if not isinstance(url, str) or not url:
        return "<invalid-url>"
    try:
        parsed = urlparse(url)
        cleaned = urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', ''))
    except Exception:
        return "<invalid-url>"
    if len(cleaned) > max_length:
        return cleaned[:max_length] + "...(truncated)"
    return cleaned


def is_ignored_domain(url: str, ignored: Any) -> bool:
    if not ignored or not isinstance(ignored, (list, tuple)):
        return False
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    if not host:
        return False
    for entry in ignored:
        dom = str(entry).strip().lower().lstrip(".")
        if dom and (host == dom or host.endswith("." + dom)):
            return True
    return False


def normalize_image(filepath: str, min_size: int = 50, quality: int = 95) -> Optional[str]:
    try:
        with Image.open(filepath) as img:
            width, height = img.size
            if width < min_size or height < min_size:
                logger.warning(lmsg(
                    "utils.skip_image_too_small",
                    width=width, height=height, min_size=min_size, filepath=filepath,
                ))
                try:
                    os.remove(filepath)
                except OSError:
                    pass
                return None

            needs_convert = img.format in ('WEBP', 'TIFF') or img.mode in ('RGBA', 'P', 'LA', 'CMYK')
            if not needs_convert:
                return filepath

            rgb_im = img.convert('RGB')

        new_filepath = filepath.rsplit('.', 1)[0] + '.jpg'
        rgb_im.save(new_filepath, 'JPEG', quality=quality)
        if filepath != new_filepath:
            try:
                os.remove(filepath)
            except OSError:
                pass
        return new_filepath
    except Exception as e:
        logger.debug(lmsg("utils.normalize_image_falhou", filepath=filepath, e=e))
        try:
            os.remove(filepath)
        except OSError:
            pass
        return None


def dedupe_identical_files(files: list[str]) -> list[str]:
    """Remove (do disco e da lista) arquivos com conteúdo idêntico, mantendo o
    primeiro. O extrator genérico do yt-dlp baixa o mesmo vídeo uma vez por tag
    (<video> e <source>), com nomes diferentes."""
    kept: list[str] = []
    seen: dict[tuple[int, str], str] = {}
    for path in files:
        try:
            size = os.path.getsize(path)
            h = hashlib.sha1()
            with open(path, 'rb') as f:
                for block in iter(lambda: f.read(1 << 20), b''):
                    h.update(block)
            key = (size, h.hexdigest())
        except OSError:
            kept.append(path)
            continue
        if key in seen:
            logger.info(lmsg("utils.duplicate_file_removed", path=os.path.basename(path), original=os.path.basename(seen[key])))
            try:
                os.remove(path)
            except OSError:
                pass
            continue
        seen[key] = path
        kept.append(path)
    return kept


async def safe_cleanup(folder: str) -> None:
    def _cleanup():
        if not os.path.exists(folder):
            return
        for attempt in range(3):
            try:
                shutil.rmtree(folder)
                break
            except Exception as e:
                if attempt == 2:
                    logger.warning(lmsg("utils.falha_final_ao", folder=folder, e=e), exc_info=True)
                else:
                    time.sleep(1)

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(state.IO_POOL, _cleanup)


DOWNLOAD_CHUNK_SIZE = 8192


async def async_download_file(
    url: str,
    filepath: str,
    headers: Optional[dict] = None,
    return_content_type: bool = False,
):
    """Baixa via aiohttp. Se return_content_type=True, retorna (ok, content_type)."""
    ct = ''
    # Timeout por leitura, não pelo arquivo inteiro: um número puro vira
    # ClientTimeout(total=...) e corta vídeos grandes no meio do download.
    per_read = cfg("DOWNLOAD_TIMEOUT_SECONDS")
    timeout = aiohttp.ClientTimeout(total=None, connect=per_read, sock_read=per_read)
    try:
        async with state.AIOHTTP_SESSION.get(url, timeout=timeout, headers=headers) as response:
            ct = (response.headers.get('Content-Type') or '').lower()
            if response.status == 200:
                if ct.startswith(('text/html', 'application/json')):
                    logger.warning(lmsg("utils.skip_content_type", ct=ct, url=url))
                    return (False, ct) if return_content_type else False

                async with aiofiles.open(filepath, 'wb') as f:
                    async for chunk in response.content.iter_chunked(DOWNLOAD_CHUNK_SIZE):
                        await f.write(chunk)

                try:
                    if os.path.getsize(filepath) == 0:
                        logger.debug(lmsg("utils.download_produziu_arquivo", filepath=filepath))
                        os.remove(filepath)
                        return (False, ct) if return_content_type else False
                except OSError:
                    return (False, ct) if return_content_type else False
                return (True, ct) if return_content_type else True
            logger.warning(lmsg("utils.skip_http_x", arg0=response.status, url=url))
            return (False, ct) if return_content_type else False
    except Exception as e:
        logger.warning(lmsg("utils.erro_no_aiohttp", url=url, e=e))
        # Não deixa arquivo parcial pra trás: quem lista a pasta depois
        # (fallback genérico) o trataria como mídia baixada.
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except OSError:
            pass
    return (False, ct) if return_content_type else False


SEGMENT_MIN_BYTES = 4 * 1024 * 1024
_SEGMENT_ATTEMPTS = 3


def _parse_content_range_total(value: str) -> Optional[int]:
    # "bytes 0-0/28186548"
    try:
        total = value.rsplit('/', 1)[1].strip()
        return int(total) if total != '*' else None
    except (IndexError, ValueError):
        return None


async def async_download_file_segmented(
    url: str,
    filepath: str,
    headers: Optional[dict] = None,
    segments: Optional[int] = None,
) -> bool:
    """Baixa em N faixas (Range) em paralelo. Algumas CDNs limitam a
    velocidade por conexão (~650 KB/s), então 4 conexões ≈ 4× mais rápido.
    Sem suporte a Range ou arquivo pequeno, cai no download simples."""
    segments = segments or cfg("DOWNLOAD_SEGMENTS")
    headers = dict(headers or {})
    per_read = cfg("DOWNLOAD_TIMEOUT_SECONDS")
    timeout = aiohttp.ClientTimeout(total=None, connect=per_read, sock_read=per_read)

    total = None
    if segments > 1:
        try:
            async with state.AIOHTTP_SESSION.get(
                url, timeout=timeout, headers={**headers, 'Range': 'bytes=0-0'},
            ) as response:
                ct = (response.headers.get('Content-Type') or '').lower()
                if response.status == 206 and not ct.startswith(('text/html', 'application/json')):
                    total = _parse_content_range_total(response.headers.get('Content-Range', ''))
        except Exception as e:
            logger.debug(lmsg("utils.segment_probe_failed", url=url, e=e))
    if not total or total < SEGMENT_MIN_BYTES:
        return await async_download_file(url, filepath, headers=headers)

    size = -(-total // segments)
    ranges = [(start, min(start + size, total) - 1) for start in range(0, total, size)]
    with open(filepath, 'wb') as f:
        f.truncate(total)

    async def _fetch(start: int, end: int) -> None:
        pos = start
        for attempt in range(_SEGMENT_ATTEMPTS):
            try:
                async with state.AIOHTTP_SESSION.get(
                    url, timeout=timeout, headers={**headers, 'Range': f'bytes={pos}-{end}'},
                ) as response:
                    if response.status != 206:
                        raise aiohttp.ClientResponseError(
                            response.request_info, (), status=response.status,
                        )
                    async with aiofiles.open(filepath, 'r+b') as f:
                        await f.seek(pos)
                        async for chunk in response.content.iter_chunked(64 * 1024):
                            await f.write(chunk[:end + 1 - pos])
                            pos += len(chunk)
                            if pos > end:
                                break
                if pos > end:
                    return
            except Exception as e:
                # Retoma do byte onde parou em vez de reiniciar a faixa.
                if attempt == _SEGMENT_ATTEMPTS - 1:
                    raise
                logger.debug(lmsg("utils.segment_retry", url=url, start=pos, end=end, e=e))
        raise IOError(f"faixa {start}-{end} incompleta")

    tasks = [asyncio.create_task(_fetch(s, e)) for s, e in ranges]
    try:
        await asyncio.gather(*tasks)
        return True
    except (Exception, asyncio.CancelledError) as e:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        try:
            os.remove(filepath)
        except OSError:
            pass
        if isinstance(e, asyncio.CancelledError):
            raise
        logger.warning(lmsg("utils.erro_no_aiohttp", url=url, e=e))
        return False


async def async_download_via_playwright(
    url: str,
    filepath: str,
    referer: Optional[str] = None,
) -> bool:
    """Fallback de download usando o contexto do Playwright (herda cookies + UA).

    Útil quando o aiohttp leva 403 por falta de Referer/cookie de sessão.
    """
    if not state.PW_CONTEXT:
        return False
    headers = {'Referer': referer} if referer else None
    try:
        resp = await state.PW_CONTEXT.request.get(url, headers=headers)
    except Exception as e:
        logger.warning(lmsg("utils.erro_pw_request", e=e))
        return False
    try:
        if resp.status != 200:
            logger.warning(lmsg("utils.skip_pw_http", arg0=resp.status, url=url))
            return False
        body = await resp.body()
        if not body:
            logger.warning(lmsg("utils.skip_pw_corpo", url=url))
            return False
        async with aiofiles.open(filepath, 'wb') as f:
            await f.write(body)
        return os.path.getsize(filepath) > 0
    except Exception as e:
        logger.warning(lmsg("utils.erro_escrevendo_pw", e=e))
        return False
    finally:
        try:
            await resp.dispose()
        except Exception:
            pass


async def _run_proc(
    cmd: list[str], timeout: int, capture_stdout: bool = False,
) -> tuple[str, bytes, Any]:
    """Roda cmd e espera. Retorna (status, stdout, detalhe) com status em
    ok | fail (returncode != 0) | timeout | error. detalhe é o stderr decodificado,
    ou a exceção no caso 'error'."""
    process = None
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE if capture_stdout else asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        detail = (stderr or b'').decode('utf-8', errors='ignore')
        return ('ok' if process.returncode == 0 else 'fail'), (stdout or b''), detail
    except asyncio.TimeoutError:
        if process:
            try:
                process.kill()
                await process.wait()
            except Exception:
                pass
        return 'timeout', b'', ''
    except asyncio.CancelledError:
        # Shutdown cancela a task: sem isso o ffmpeg fica órfão rodando.
        if process and process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
        raise
    except Exception as e:
        return 'error', b'', e


def _nonempty(path: str) -> bool:
    return os.path.exists(path) and os.path.getsize(path) > 0


async def async_gif_to_mp4(input_path: str, output_path: str, timeout: int = 60) -> bool:
    cmd = [
        state.FFMPEG_PATH or 'ffmpeg', '-y', '-i', input_path,
        '-movflags', '+faststart',
        '-pix_fmt', 'yuv420p',
        '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2',
        '-an', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23',
        output_path,
    ]
    status, _, detail = await _run_proc(cmd, timeout)
    if status == 'timeout':
        logger.warning(lmsg("utils.gif_to_mp4_timeout", timeout=timeout, input_path=input_path))
        return False
    if status == 'error':
        logger.warning(lmsg("utils.gif_to_mp4_erro", e=detail), exc_info=detail)
        return False
    if status == 'fail':
        logger.warning(lmsg("utils.gif_to_mp4_falhou", arg0=detail[-400:]))
        return False
    return _nonempty(output_path)


_TG_COMPATIBLE_VIDEO_EXTS = ('.mp4', '.m4v', '.mov')
_TG_COMPATIBLE_VCODECS = ('h264', 'avc1', 'avc')
_TG_COMPATIBLE_ACODECS = ('aac',)


def is_telegram_compatible_video_ext(filepath: str) -> bool:
    return filepath.lower().endswith(_TG_COMPATIBLE_VIDEO_EXTS)


def _ffprobe_fields(stdout: bytes) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for line in stdout.decode('utf-8', errors='ignore').splitlines():
        if '=' in line:
            k, v = line.split('=', 1)
            out.append((k.strip(), v.strip()))
    return out


async def async_ffprobe_codecs(filepath: str, timeout: int = 30) -> tuple[Optional[str], Optional[str]]:
    if not state.FFPROBE_PATH:
        return None, None
    cmd = [
        state.FFPROBE_PATH, '-v', 'error',
        '-show_entries', 'stream=codec_type,codec_name',
        '-of', 'default=nw=1',
        filepath,
    ]
    status, stdout, detail = await _run_proc(cmd, timeout, capture_stdout=True)
    if status == 'timeout':
        logger.warning(lmsg("utils.ffprobe_timeout", timeout=timeout, filepath=filepath))
        return None, None
    if status == 'error':
        logger.warning(lmsg("utils.ffprobe_erro", e=detail))
        return None, None
    if status == 'fail':
        logger.warning(lmsg("utils.ffprobe_falhou", arg0=detail[-200:]))
        return None, None

    vcodec: Optional[str] = None
    acodec: str = ''
    cur_type: Optional[str] = None
    cur_name: Optional[str] = None
    for k, v in _ffprobe_fields(stdout):
        v = v.lower()
        if k == 'codec_type':
            cur_type = v
        elif k == 'codec_name':
            cur_name = v
        if cur_type and cur_name:
            if cur_type == 'video' and vcodec is None:
                vcodec = cur_name
            elif cur_type == 'audio' and not acodec:
                acodec = cur_name
            cur_type = cur_name = None
    return vcodec, acodec


async def async_ffprobe_video_meta(filepath: str, timeout: int = 30) -> tuple[Optional[int], Optional[int], Optional[int]]:
    """Retorna (width, height, duration_seg) do 1º stream de vídeo — o Bot API local
    NÃO auto-detecta esses metadados, e sem eles o cliente do Telegram às vezes não
    monta o player ('não foi possível reproduzir, use player externo')."""
    if not state.FFPROBE_PATH:
        return None, None, None
    cmd = [
        state.FFPROBE_PATH, '-v', 'error',
        '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height:format=duration',
        '-of', 'default=nw=1',
        filepath,
    ]
    status, stdout, detail = await _run_proc(cmd, timeout, capture_stdout=True)
    if status == 'error':
        logger.warning(lmsg("utils.ffprobe_erro", e=detail))
    if status != 'ok':
        return None, None, None

    meta: dict[str, int] = {}
    for k, v in _ffprobe_fields(stdout):
        if k in ('width', 'height', 'duration') and v and v != 'N/A':
            try:
                meta[k] = int(float(v))
            except ValueError:
                continue
    return meta.get('width'), meta.get('height'), meta.get('duration')


async def async_ensure_telegram_video(filepath: str, timeout: int = 600) -> Optional[str]:
    ext_ok = is_telegram_compatible_video_ext(filepath)

    if not state.FFMPEG_PATH:
        if ext_ok:
            return filepath
        logger.warning(lmsg("utils.video_convert_no_ffmpeg", filepath=filepath))
        return None

    vcodec, acodec = await async_ffprobe_codecs(filepath)
    if vcodec is None:
        return filepath if ext_ok else None

    v_ok = vcodec in _TG_COMPATIBLE_VCODECS
    a_ok = (acodec == '') or (acodec in _TG_COMPATIBLE_ACODECS)
    if ext_ok and v_ok and a_ok:
        return filepath

    out_path = os.path.splitext(filepath)[0] + '.tg.mp4'
    reencode = ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23', '-pix_fmt', 'yuv420p']

    if acodec == '':
        a_args = ['-an']
    elif a_ok:
        a_args = ['-c:a', 'copy']
    else:
        a_args = ['-c:a', 'aac', '-b:a', '192k']

    # copy do vídeo primeiro; se falhar, re-encoda
    for attempt, v_args in enumerate([['-c:v', 'copy'], reencode] if v_ok else [reencode]):
        if attempt:
            logger.info(lmsg("utils.video_convert_retry_reencode", filepath=filepath))
        else:
            logger.info(lmsg(
                "utils.video_convert_iniciando",
                filepath=filepath, vcodec=vcodec or 'unknown', acodec=acodec or 'none',
                v_args=' '.join(v_args), a_args=' '.join(a_args),
            ))
        cmd = [state.FFMPEG_PATH, '-y', '-i', filepath, *v_args, *a_args, '-movflags', '+faststart', out_path]
        status, _, detail = await _run_proc(cmd, timeout)
        if status == 'ok' and _nonempty(out_path):
            logger.info(lmsg("utils.video_convert_ok", out_path=out_path))
            return out_path
        if status == 'timeout':
            logger.warning(lmsg("utils.video_convert_timeout", timeout=timeout, filepath=filepath))
        elif status == 'error':
            logger.warning(lmsg("utils.video_convert_erro", e=detail))
        else:
            logger.warning(lmsg("utils.video_convert_falhou", arg0=detail[-400:]))

    return None


async def async_ffmpeg_remux(
    input_url: str,
    output_path: str,
    timeout: int = 180,
    headers: Optional[dict] = None,
) -> bool:
    """Mux HLS/DASH/qualquer URL stream pra mp4 via ffmpeg copy (sem re-encode)."""
    cmd = [state.FFMPEG_PATH or 'ffmpeg', '-y']
    if headers:
        cmd.extend(['-headers', ''.join(f"{k}: {v}\r\n" for k, v in headers.items())])
    cmd.extend([
        '-i', input_url,
        '-c', 'copy',
        '-bsf:a', 'aac_adtstoasc',
        '-movflags', '+faststart',
        output_path,
    ])
    status, _, detail = await _run_proc(cmd, timeout)
    if status == 'timeout':
        logger.warning(lmsg("utils.ffmpeg_remux_timeout", timeout=timeout, input_url=input_url))
        return False
    if status == 'error':
        logger.warning(lmsg("utils.erro_fatal_no", e=detail), exc_info=detail)
        return False
    if status == 'fail':
        logger.warning(lmsg("utils.ffmpeg_remux_falhou", arg0=detail[-400:]))
        return False
    return _nonempty(output_path)


async def async_merge_audio_image(
    image_path: str,
    audio_path: str,
    output_path: str,
    start_time: Optional[float] = None,
    duration: Optional[float] = None,
) -> bool:
    cmd = [state.FFMPEG_PATH or 'ffmpeg', '-y', '-loop', '1', '-framerate', '15', '-i', image_path]
    if start_time is not None:
        cmd.extend(['-ss', str(start_time)])
    cmd.extend(['-i', audio_path, '-map', '0:v:0', '-map', '1:a:0'])
    if duration is not None:
        cmd.extend(['-t', str(duration)])
    cmd.extend([
        '-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'stillimage',
        '-r', '15',
        '-c:a', 'aac', '-b:a', '192k',
        '-vf', "scale='min(1280,iw)':'min(1280,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2",
        '-pix_fmt', 'yuv420p', '-shortest',
        '-movflags', '+faststart',
        output_path,
    ])

    status, _, detail = await _run_proc(cmd, 180)
    if status == 'timeout':
        logger.error(lmsg("utils.ffmpeg_travou_e"))
        return False
    if status == 'error':
        logger.error(lmsg("utils.erro_fatal_no_2", e=detail), exc_info=detail)
        return False
    if status == 'fail':
        logger.error(lmsg("utils.erro_ffmpeg_x", err_msg=detail))
        return False
    return True


async def cycle_status_message(status_msg: Any, suffix: str = "") -> None:
    messages = [m.format(suffix=suffix) for m in msg_list("status_cycle")]
    idx = 1 % len(messages)
    try:
        while True:
            try:
                await status_msg.edit_text(messages[idx])
            except RetryAfter as e:
                await asyncio.sleep(e.retry_after)
                continue
            except Exception as str_err:
                err_msg = str(str_err).lower()
                if "not found" in err_msg or "deleted" in err_msg or "message to edit not found" in err_msg:
                    break
            await asyncio.sleep(cfg("STATUS_CYCLE_INTERVAL"))
            idx = (idx + 1) % len(messages)
    except asyncio.CancelledError:
        pass

import asyncio
import logging
import os
from typing import Any, Optional

from PIL import Image
from telegram import InputMediaPhoto, InputMediaVideo
from telegram.error import BadRequest, RetryAfter, TimedOut

from config import (
    cfg,
    ANIMATION_EXTS,
    IMAGE_EXTS,
    VIDEO_EXTS,
)
from messages import lmsg
from utils import async_ensure_telegram_video, async_ffprobe_video_meta, async_gif_to_mp4

logger = logging.getLogger(__name__)


def _get_image_dims(filepath: str) -> tuple[Optional[int], Optional[int]]:
    try:
        with Image.open(filepath) as img:
            return img.size
    except Exception:
        return None, None


async def _gif_to_mp4(gif_path: str) -> Optional[str]:
    mp4_path = os.path.splitext(gif_path)[0] + '.gif.mp4'
    if await async_gif_to_mp4(gif_path, mp4_path):
        return mp4_path
    return None


async def _ensure_video(f_path: str) -> str:
    converted = await async_ensure_telegram_video(f_path, timeout=cfg("VIDEO_CONVERT_TIMEOUT"))
    return converted or f_path


async def _video_meta_kwargs(video_path: str) -> dict:
    width, height, duration = await async_ffprobe_video_meta(video_path)
    meta: dict = {}
    if width:
        meta['width'] = width
    if height:
        meta['height'] = height
    if duration:
        meta['duration'] = duration
    return meta


def _is_image_process_failed(e: Exception) -> bool:
    return isinstance(e, BadRequest) and 'image_process_failed' in str(e).lower()


async def _send_with_retry(send, attempts: int, flood_key: str, timeout_key: str, error_key: str) -> None:
    """Chama send() com retry em flood control e timeout. Esgotadas as tentativas,
    relança o último erro: sair calado deixava o usuário sem a mídia e sem aviso."""
    last_exc: Optional[Exception] = None
    for _ in range(attempts):
        try:
            await send()
            return
        except RetryAfter as e:
            logger.warning(lmsg(f"telegram_io.{flood_key}", arg0=e.retry_after))
            last_exc = e
            await asyncio.sleep(e.retry_after + 1)
        except TimedOut as e:
            logger.warning(lmsg(f"telegram_io.{timeout_key}"))
            last_exc = e
            await asyncio.sleep(5)
        except Exception as e:
            if not _is_image_process_failed(e):
                logger.error(lmsg(f"telegram_io.{error_key}", e=e), exc_info=True)
            raise
    logger.error(lmsg("telegram_io.retries_exhausted", n=attempts))
    raise last_exc


async def _send_single(
    context: Any,
    chat_id: int,
    f_path: str,
    upload_kwargs: dict[str, Any],
) -> None:
    timeout = cfg("TELEGRAM_UPLOAD_TIMEOUT")
    upload_kwargs.setdefault('read_timeout', timeout)
    upload_kwargs.setdefault('write_timeout', timeout)
    upload_kwargs.setdefault('connect_timeout', timeout)

    # Conversões rodam uma vez só, fora do loop de retry.
    filename_lower = f_path.lower()
    if filename_lower.endswith(IMAGE_EXTS):
        async def send():
            await context.bot.send_photo(chat_id=chat_id, photo=f_path, **upload_kwargs)
    elif filename_lower.endswith(ANIMATION_EXTS):
        anim_kwargs = dict(upload_kwargs)
        width, height = _get_image_dims(f_path)
        if width and height:
            anim_kwargs.setdefault('width', width)
            anim_kwargs.setdefault('height', height)
        anim_path = await _gif_to_mp4(f_path) or f_path

        async def send():
            await context.bot.send_animation(chat_id=chat_id, animation=anim_path, **anim_kwargs)
    elif filename_lower.endswith(VIDEO_EXTS):
        video_path = await _ensure_video(f_path)
        vid_kwargs = dict(upload_kwargs)
        for k, v in (await _video_meta_kwargs(video_path)).items():
            vid_kwargs.setdefault(k, v)

        async def send():
            await context.bot.send_video(chat_id=chat_id, video=video_path, supports_streaming=True, **vid_kwargs)
    else:
        async def send():
            await context.bot.send_document(chat_id=chat_id, document=f_path, **upload_kwargs)

    try:
        await _send_with_retry(send, 4, "flood_control_telegram", "timeout_no_envio", "erro_fatal_ao")
    except BadRequest as e:
        if not (_is_image_process_failed(e) and filename_lower.endswith(IMAGE_EXTS)):
            raise
        # Imagem que o Telegram não consegue processar como foto ainda vai como arquivo.
        logger.warning(lmsg("telegram_io.image_as_document", path=os.path.basename(f_path)))

        async def send_doc():
            await context.bot.send_document(chat_id=chat_id, document=f_path, **upload_kwargs)

        await _send_with_retry(send_doc, 4, "flood_control_telegram", "timeout_no_envio", "erro_fatal_ao")


async def send_downloaded_media(
    context: Any,
    chat_id: int,
    files: list[str],
    original_msg_id: int,
    upload_kwargs: dict[str, Any],
    caption: Optional[str] = None,
) -> None:
    if len(files) == 1:
        if caption:
            upload_kwargs['caption'] = caption
        await _send_single(context, chat_id, files[0], upload_kwargs)
    else:
        chunk_size = cfg("MEDIA_GROUP_CHUNK_SIZE")
        for i in range(0, len(files), chunk_size):
            chunk_files = files[i:i + chunk_size]
            media_group = []
            chunk_caption = caption if i == 0 else None

            for f_path in chunk_files:
                filename_lower = f_path.lower()
                item_caption = chunk_caption if len(media_group) == 0 else None

                if filename_lower.endswith(IMAGE_EXTS):
                    media_group.append(InputMediaPhoto(media=f_path, parse_mode='HTML', caption=item_caption))
                elif filename_lower.endswith(VIDEO_EXTS) or filename_lower.endswith(ANIMATION_EXTS):
                    is_video = filename_lower.endswith(VIDEO_EXTS)
                    video_path = await _ensure_video(f_path) if is_video else f_path
                    vid_meta = await _video_meta_kwargs(video_path) if is_video else {}
                    media_group.append(InputMediaVideo(
                        media=video_path, parse_mode='HTML', caption=item_caption,
                        supports_streaming=True, **vid_meta,
                    ))

            if media_group:
                timeout = cfg("TELEGRAM_UPLOAD_TIMEOUT")

                async def send_group():
                    await context.bot.send_media_group(
                        chat_id=chat_id,
                        media=media_group,
                        reply_to_message_id=original_msg_id,
                        read_timeout=timeout,
                        write_timeout=timeout,
                        connect_timeout=timeout,
                    )

                try:
                    await _send_with_retry(send_group, 5, "flood_control_de", "timeout_no_envio_2", "erro_desconhecido_ao")
                except BadRequest as e:
                    if not _is_image_process_failed(e):
                        raise
                    # Uma imagem ruim derruba o álbum inteiro; manda um a um,
                    # e a problemática sai como documento.
                    logger.warning(lmsg("telegram_io.media_group_fallback", e=e))
                    for idx, f_path in enumerate(chunk_files):
                        single_kwargs = {k: v for k, v in upload_kwargs.items() if k != 'caption'}
                        if idx == 0 and chunk_caption:
                            single_kwargs['caption'] = chunk_caption
                        await _send_single(context, chat_id, f_path, single_kwargs)
                        if idx < len(chunk_files) - 1:
                            await asyncio.sleep(cfg("MEDIA_GROUP_DELAY"))

                if i + chunk_size < len(files):
                    await asyncio.sleep(cfg("MEDIA_GROUP_DELAY"))

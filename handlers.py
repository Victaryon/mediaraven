import asyncio
import html
import logging
import os
import random
import time
from typing import Any, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import NetworkError
from telegram.ext import ContextTypes

import state
from config import (
    cfg,
    ALLOW_ALL,
    ALLOWED_CHAT_ID,
    ALLOWED_USER_ID,
    BASE_DOWNLOAD_DIR,
    request_context,
    should_show_prompt,
)
from downloaders.dispatcher import download_media
from downloaders.fallback import take_page_screenshot
from lifecycle import get_chat_lock
from messages import lmsg, msg, msg_list
from downloaders._caption import CAPTION_MAX, TEXT_MAX
from telegram_io import send_downloaded_media
from utils import chunk_html_text, cycle_status_message, is_ignored_domain, safe_cleanup, safe_url

logger = logging.getLogger(__name__)


_ERROR_NOTICE_INTERVAL_S = 300
_last_error_notice = 0.0


async def notify_error(context: ContextTypes.DEFAULT_TYPE, err: BaseException, where: str) -> None:
    """Avisa ERROR_NOTIFY_CHAT_ID do erro, no máximo 1 aviso a cada 5 min."""
    global _last_error_notice
    target = cfg("ERROR_NOTIFY_CHAT_ID")
    now = time.monotonic()
    if not target or now - _last_error_notice < _ERROR_NOTICE_INTERVAL_S:
        return
    _last_error_notice = now
    detail = html.escape(f"{type(err).__name__}: {err}")[:500]
    try:
        await context.bot.send_message(
            target, msg("status.error_notice", where=html.escape(where), error=detail), parse_mode='HTML',
        )
    except Exception as e:
        logger.debug(lmsg("handlers.falha_aviso_erro", e=e))


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Erros que escapam dos handlers (callbacks, polling...)."""
    err = context.error
    if isinstance(err, NetworkError):
        # oscilação de rede/servidor do Telegram; o polling se recupera sozinho
        logger.warning(lmsg("handlers.erro_rede", e=err))
        return
    logger.error(lmsg("handlers.erro_nao_tratado", e=err), exc_info=err)
    await notify_error(context, err, "handler")


# prefixo do callback_data: (store_key, nome nos alerts, nome nos buttons, chave do prompt)
_PROMPT_KINDS = {
    'dl': ('dl_futures', 'dl', 'download', 'link_detected'),
    'lang': ('lang_futures', 'lang', '', 'language_detected'),
    'cap': ('caption_futures', 'caption', 'caption', 'caption_found'),
    'scrn': ('screenshot_futures', 'screenshot', 'screenshot', 'screenshot_offer'),
}


async def future_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    prefix, req_key, value = query.data.split('|')
    store_key, alert = _PROMPT_KINDS[prefix][:2]

    # message_id só é único dentro do chat: a chave guardada leva o chat junto.
    data = context.bot_data.get(store_key, {}).get((query.message.chat_id, req_key))
    if not data:
        await query.answer(msg(f"callback_alerts.{alert}_expired"), show_alert=True)
        return

    if query.from_user.id != data['user_id']:
        await query.answer(msg(f"callback_alerts.{alert}_wrong_user"), show_alert=True)
        return

    future = data['future']
    if not future.done():
        future.set_result(value)
    await query.answer()


async def retry_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    retry_id = (query.message.chat_id, query.data)

    if retry_id not in context.bot_data.get('retries', {}):
        await query.answer(msg("callback_alerts.retry_expired"), show_alert=True)
        await query.edit_message_text(msg("callback_alerts.retry_expired"))
        return

    retry_data = context.bot_data['retries'][retry_id]

    if query.from_user.id != retry_data.get('user_id'):
        await query.answer(msg("callback_alerts.retry_wrong_user"), show_alert=True)
        return

    context.bot_data['retries'].pop(retry_id)
    await query.answer()
    await query.message.delete()
    request_context.set((query.message.chat_id, retry_data['user_id']))
    await process_media_request(
        context, query.message.chat_id, retry_data['msg_id'], retry_data['url'],
        target_lang=retry_data.get('target_lang'),
        user_id=retry_data['user_id'], is_retry=True,
    )


async def _ask_via_future(
    context: ContextTypes.DEFAULT_TYPE,
    store_key: str,
    chat_id: int,
    req_key: str,
    user_id: Optional[int],
    timeout: float,
    default: str,
) -> str:
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    key = (chat_id, req_key)
    context.bot_data.setdefault(store_key, {})[key] = {'future': future, 'user_id': user_id}
    try:
        return await asyncio.wait_for(future, timeout=timeout)
    except asyncio.TimeoutError:
        return default
    finally:
        context.bot_data[store_key].pop(key, None)


def _yes_no_markup(prefix: str, req_key: str, yes_label: str, no_label: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(yes_label, callback_data=f"{prefix}|{req_key}|yes"),
        InlineKeyboardButton(no_label, callback_data=f"{prefix}|{req_key}|no"),
    ]])


async def _ask_yes_no(
    context: ContextTypes.DEFAULT_TYPE,
    prefix: str,
    message_id: int,
    idx: int,
    suffix: str,
    user_id: Optional[int],
    timeout: float,
    default: str,
    status_msg: Any = None,
    chat_id: Optional[int] = None,
) -> tuple[str, Any]:
    """Pergunta sim/não. Sem status_msg, envia mensagem nova em chat_id."""
    store_key, _, labels, prompt_key = _PROMPT_KINDS[prefix]
    req_key = f"{prefix}_{message_id}_{idx}"
    markup = _yes_no_markup(
        prefix, req_key, msg(f"buttons.{labels}_yes"), msg(f"buttons.{labels}_no"),
    )
    text = msg(f"prompts.{prompt_key}", suffix=suffix)
    if status_msg is None:
        status_msg = await context.bot.send_message(
            chat_id, text, parse_mode='HTML', reply_markup=markup,
            reply_to_message_id=message_id, disable_web_page_preview=True,
        )
    else:
        await status_msg.edit_text(text, parse_mode='HTML', reply_markup=markup)
    choice = await _ask_via_future(
        context, store_key, status_msg.chat_id, req_key, user_id, timeout=timeout, default=default,
    )
    return choice, status_msg


async def _ask_language_choice(
    context: ContextTypes.DEFAULT_TYPE,
    status_msg: Any,
    message_id: int,
    lang_buttons: list,
    suffix: str,
    user_id: Optional[int],
    idx: int,
) -> str:
    req_key = f"{message_id}_{idx}"
    buttons = [
        InlineKeyboardButton(label, callback_data=f"lang|{req_key}|{code}")
        for code, label in lang_buttons
    ]
    keyboard = [buttons[i:i + 3] for i in range(0, len(buttons), 3)]
    markup = InlineKeyboardMarkup(keyboard)
    await status_msg.edit_text(
        msg("prompts.language_detected", suffix=suffix),
        parse_mode='HTML',
        reply_markup=markup,
    )
    return await _ask_via_future(
        context, 'lang_futures', status_msg.chat_id, req_key, user_id,
        timeout=cfg("ASK_LANG_TIMEOUT"), default='original',
    )


async def _try_screenshot_offer(
    context: ContextTypes.DEFAULT_TYPE,
    status_msg: Any,
    message_id: int,
    suffix: str,
    user_id: Optional[int],
    idx: int,
    unique_folder: Optional[str],
    url: str,
    is_retry: bool,
) -> list:
    if is_retry or cfg("SCRAPE_SCREENSHOT_FALLBACK") != "yes" or unique_folder is None:
        return []
    try:
        choice, _ = await _ask_yes_no(
            context, 'scrn', message_id, idx, suffix, user_id,
            timeout=cfg("ASK_SCREENSHOT_TIMEOUT"), default=cfg("ASK_SCREENSHOT_DEFAULT"),
            status_msg=status_msg,
        )
        wants = choice == 'yes'
    except Exception as e:
        logger.debug(lmsg("handlers.falha_no_prompt", e=e))
        return []
    if not wants:
        return []
    await _safe_edit(status_msg, msg("status.screenshot_taking", suffix=suffix), parse_mode='HTML')
    shot = await take_page_screenshot(os.path.join(unique_folder, "content"), url)
    if shot:
        return [shot]
    logger.warning(lmsg("handlers.screenshot_falhou_para", url=url))
    return []


async def _acquire_chat_lock(status_msg: Any, chat_id: int, suffix: str) -> asyncio.Lock:
    lock = get_chat_lock(chat_id)
    if lock.locked():
        try:
            await status_msg.edit_text(msg("status.queue_busy", suffix=suffix))
        except Exception as e:
            logger.debug(lmsg("handlers.falha_ao_atualizar", e=e))
    await lock.acquire()
    return lock


async def _safe_edit(status_msg: Any, text: str, **kwargs) -> None:
    try:
        await status_msg.edit_text(text, **kwargs)
    except Exception as e:
        logger.debug(lmsg("handlers.falha_silenciosa_em", e=e))


async def _safe_react(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int, emoji: str) -> bool:
    try:
        await context.bot.set_message_reaction(chat_id, message_id, reaction=emoji)
        return True
    except Exception as e:
        logger.debug(lmsg("handlers.falha_ao_setar", e=e))
        return False


async def _safe_delete(status_msg: Any) -> None:
    try:
        await status_msg.delete()
    except Exception as e:
        logger.debug(lmsg("handlers.falha_silenciosa_em_2", e=e))


def _build_suffix(idx: int, total: int, target_lang: Optional[str]) -> str:
    suffix = f" (Link {idx}/{total})" if total > 1 else ""
    if target_lang:
        suffix += f" [Idioma: {target_lang.upper()}]"
    return suffix


async def _initial_status_message(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    message_id: int,
    suffix: str,
    user_id: Optional[int],
    idx: int,
    skip_confirm: bool,
    total: int = 1,
) -> Optional[Any]:
    prompt_enabled = should_show_prompt("download", chat_id, user_id or 0)
    if skip_confirm or not prompt_enabled:
        return await context.bot.send_message(
            chat_id,
            msg("status.queue_busy", suffix=suffix),
            reply_to_message_id=message_id,
        )

    choice, status_msg = await _ask_yes_no(
        context, 'dl', message_id, idx, suffix, user_id,
        timeout=cfg("ASK_DL_TIMEOUT"), default=cfg("ASK_DL_DEFAULT"),
        chat_id=chat_id,
    )
    if choice == 'no':
        # Link único: a pergunta some e só a reação da mensagem muda. Com vários links
        # a reação valeria pra todos — e se o chat recusar a reação, o texto avisa.
        if total == 1 and await _safe_react(context, chat_id, message_id, msg("reaction_ignored")):
            await _safe_delete(status_msg)
        else:
            await _safe_edit(status_msg, msg("status.download_ignored", suffix=suffix))
        return None
    await _safe_edit(status_msg, msg("status.queue_busy", suffix=suffix))
    return status_msg


async def _register_retry_and_prompt(
    context: ContextTypes.DEFAULT_TYPE,
    status_msg: Any,
    message_id: int,
    idx: int,
    url: str,
    user_id: Optional[int],
    target_lang: Optional[str],
    suffix: str,
) -> None:
    retry_id = f"retry_{message_id}_{idx}"
    context.bot_data['retries'][(status_msg.chat_id, retry_id)] = {
        'url': url, 'msg_id': message_id, 'user_id': user_id,
        'target_lang': target_lang,
    }
    markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton(msg("buttons.retry"), callback_data=retry_id)]]
    )
    text = f"{msg('downloader_status.generic_fail')}{suffix}"
    await _safe_edit(status_msg, text, parse_mode='HTML', reply_markup=markup)


async def _send_text_in_chunks(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    message_id: int,
    full_text: str,
    *,
    show_preview: bool,
    reply_to_first: bool = True,
) -> None:
    chunks = chunk_html_text(full_text, TEXT_MAX)
    if not chunks:
        return
    delay = cfg("MEDIA_GROUP_DELAY")
    last_idx = len(chunks) - 1
    for i, chunk in enumerate(chunks):
        await context.bot.send_message(
            chat_id=chat_id,
            text=chunk,
            parse_mode='HTML',
            reply_to_message_id=message_id if (reply_to_first and i == 0) else None,
            disable_web_page_preview=not (show_preview and i == last_idx),
        )
        if i < last_idx:
            await asyncio.sleep(delay)


async def _send_files_and_cleanup_status(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    message_id: int,
    status_msg: Any,
    files: list,
    desc_short: str,
    desc_full: str,
    suffix: str,
    user_id: Optional[int],
    idx: int,
    is_article: bool = False,
) -> None:
    include_text = False
    if desc_short:
        timeout = cfg("ASK_ARTICLE_TIMEOUT") if is_article else cfg("ASK_CAPTION_TIMEOUT")
        default = cfg("ASK_ARTICLE_DEFAULT") if is_article else cfg("ASK_CAPTION_DEFAULT")
        if should_show_prompt("caption", chat_id, user_id or 0):
            choice, _ = await _ask_yes_no(
                context, 'cap', message_id, idx, suffix, user_id,
                timeout=timeout, default=default, status_msg=status_msg,
            )
            include_text = choice == 'yes'
        elif default == 'yes':
            include_text = True

    await _safe_edit(status_msg, msg("status.sending", count=len(files), suffix=suffix))

    upload_kwargs = {
        'read_timeout': cfg("TELEGRAM_UPLOAD_TIMEOUT"),
        'write_timeout': cfg("TELEGRAM_UPLOAD_TIMEOUT"),
        'parse_mode': 'HTML',
        'reply_to_message_id': message_id,
    }

    text_in_chunks = include_text and desc_full and len(desc_full) > CAPTION_MAX
    caption_on_media = desc_short if (include_text and not text_in_chunks) else None

    await send_downloaded_media(
        context, chat_id, files, message_id, upload_kwargs, caption=caption_on_media
    )

    if text_in_chunks:
        await _send_text_in_chunks(
            context, chat_id, message_id, desc_full,
            show_preview=False, reply_to_first=False,
        )

    await _safe_delete(status_msg)


async def process_media_request(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    message_id: int,
    url: str,
    target_lang: Optional[str] = None,
    idx: int = 1,
    total: int = 1,
    user_id: Optional[int] = None,
    is_retry: bool = False,
) -> None:
    request_context.set((chat_id, user_id))
    suffix = _build_suffix(idx, total, target_lang)

    skip_confirm = is_retry or bool(target_lang)
    status_msg = await _initial_status_message(
        context, chat_id, message_id, suffix, user_id, idx, skip_confirm, total,
    )
    if status_msg is None:
        return

    status_task: Optional[asyncio.Task] = None
    unique_folder: Optional[str] = None
    lock = await _acquire_chat_lock(status_msg, chat_id, suffix)
    lock_acquired = True

    try:
        await _safe_edit(status_msg, msg("status.downloading", suffix=suffix), parse_mode='HTML')
        status_task = asyncio.create_task(cycle_status_message(status_msg, suffix))

        unique_folder = os.path.join(BASE_DOWNLOAD_DIR, f"task_{chat_id}_{message_id}_{idx}")
        link_folder = os.path.join(unique_folder, "content")

        detect_lang = should_show_prompt("lang", chat_id, user_id or 0)
        state.download_notice.set("")
        files, status_or_error, desc_short, desc_full, is_article = await download_media(
            url, link_folder, target_lang, detect_languages=detect_lang,
        )

        if status_task is not None:
            status_task.cancel()
            status_task = None

        if status_or_error == "MULTILANG":
            lock.release()
            lock_acquired = False

            chosen_lang = await _ask_language_choice(
                context, status_msg, message_id, files, suffix, user_id, idx
            )
            await _safe_delete(status_msg)

            return await process_media_request(
                context, chat_id, message_id, url,
                target_lang=chosen_lang,
                idx=idx, total=total,
                user_id=user_id, is_retry=is_retry,
            )

        if status_or_error:
            outcome = "✅" if files else "❌"
            logger.info(lmsg("handlers.x_x_x", outcome=outcome, status_or_error=status_or_error, arg0=safe_url(url)))

        if not files and (desc_full or desc_short):
            await _send_text_in_chunks(
                context, chat_id, message_id, desc_full or desc_short,
                show_preview=True, reply_to_first=True,
            )
            await _safe_delete(status_msg)
            return

        if not files:
            shot_files = await _try_screenshot_offer(
                context, status_msg, message_id, suffix, user_id, idx,
                unique_folder, url, is_retry,
            )
            if shot_files:
                files = shot_files
            else:
                if is_retry:
                    await _safe_edit(
                        status_msg,
                        msg("status.retry_failed", suffix=suffix),
                        parse_mode='HTML',
                    )
                else:
                    await _register_retry_and_prompt(
                        context, status_msg, message_id, idx, url, user_id, target_lang,
                        suffix,
                    )
                return

        await _send_files_and_cleanup_status(
            context, chat_id, message_id, status_msg, files, desc_short, desc_full,
            suffix, user_id, idx, is_article=is_article,
        )
        if notice := state.download_notice.get():
            await _send_text_in_chunks(context, chat_id, message_id, notice, show_preview=False)

    except Exception as e:
        logger.exception("⚠️ Erro ao processar link")
        await _safe_edit(status_msg, msg("status.internal_error", suffix=suffix))
        await notify_error(context, e, safe_url(url))

    finally:
        if status_task is not None:
            status_task.cancel()
        if unique_folder is not None:
            await safe_cleanup(unique_folder)
        if lock_acquired:
            lock.release()


def _extract_urls_from_update(update: Update) -> list[str]:
    if not update.message:
        return []

    if update.message.text:
        entities = update.message.parse_entities(types=['url', 'text_link'])
    elif update.message.caption:
        entities = update.message.parse_caption_entities(types=['url', 'text_link'])
    else:
        entities = {}

    urls: list[str] = []
    for entity, extracted_text in entities.items():
        if entity.type == 'text_link':
            candidate = entity.url
        elif entity.type == 'url':
            if extracted_text.startswith('@'):
                continue
            candidate = extracted_text
            if not candidate.startswith(('http://', 'https://')):
                candidate = f"https://{candidate}"
        else:
            continue

        if not candidate or not candidate.lower().startswith(('http://', 'https://')):
            continue
        urls.append(candidate)

    deduped = list(dict.fromkeys(urls))

    ignored = cfg("IGNORED_DOMAINS")
    if ignored:
        kept: list[str] = []
        for candidate in deduped:
            if is_ignored_domain(candidate, ignored):
                logger.info(lmsg("handlers.dominio_ignorado", url=safe_url(candidate)))
            else:
                kept.append(candidate)
        deduped = kept

    if len(deduped) > cfg("MAX_URLS_PER_MESSAGE"):
        logger.warning(lmsg(
            "handlers.urls_exceed_limit",
            n=len(deduped), max=cfg("MAX_URLS_PER_MESSAGE"),
        ))
        return deduped[:cfg("MAX_URLS_PER_MESSAGE")]
    return deduped


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id if update.effective_user else 0
    request_context.set((chat_id, user_id))

    is_allowed_user = user_id in ALLOWED_USER_ID
    is_whitelisted_chat = chat_id in ALLOWED_CHAT_ID
    if not (ALLOW_ALL == "yes" or is_allowed_user or is_whitelisted_chat):
        return

    urls = _extract_urls_from_update(update)
    if not urls:
        return

    if is_allowed_user and not is_whitelisted_chat:
        logger.info(lmsg(
            "handlers.allowed_user_outside_whitelist",
            user_id=user_id, chat_id=chat_id, n=len(urls),
        ))

    try:
        reactions = msg_list("reactions")
        if reactions:
            await update.message.set_reaction(reaction=random.choice(reactions))
    except Exception as e:
        logger.debug(lmsg("handlers.falha_ao_setar", e=e))

    total_urls = len(urls)
    for idx, url in enumerate(urls, start=1):
        task = asyncio.create_task(
            process_media_request(
                context, chat_id, update.message.id, url,
                user_id=user_id, idx=idx, total=total_urls,
            )
        )
        state.background_tasks.add(task)
        task.add_done_callback(state.background_tasks.discard)

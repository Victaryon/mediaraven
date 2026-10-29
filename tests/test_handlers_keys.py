"""Prompts e retry são guardados por (chat_id, chave): message_id só é único dentro
do chat, então o mesmo id em outro chat não pode responder a pergunta alheia."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

import handlers


def _query(chat_id, data, user_id=7):
    query = MagicMock()
    query.data = data
    query.from_user.id = user_id
    query.message.chat_id = chat_id
    query.answer = AsyncMock()
    update = MagicMock()
    update.callback_query = query
    return update, query


@pytest.mark.asyncio
async def test_callback_de_outro_chat_nao_resolve_a_pergunta():
    ctx = MagicMock()
    ctx.bot_data = {}
    ask = asyncio.create_task(handlers._ask_via_future(
        ctx, 'dl_futures', 100, 'dl_5_1', user_id=7, timeout=1, default='timeout',
    ))
    await asyncio.sleep(0)

    update, query = _query(chat_id=200, data='dl|dl_5_1|yes')
    await handlers.future_callback(update, ctx)
    query.answer.assert_awaited_once()
    assert query.answer.await_args.kwargs.get('show_alert') is True
    assert not ask.done()

    update, _ = _query(chat_id=100, data='dl|dl_5_1|yes')
    await handlers.future_callback(update, ctx)
    assert await ask == 'yes'


@pytest.mark.asyncio
async def test_retry_de_outro_chat_expira():
    ctx = MagicMock()
    ctx.bot_data = {'retries': {(100, 'retry_5_1'): {'url': 'u', 'msg_id': 5, 'user_id': 7}}}
    update, query = _query(chat_id=200, data='retry_5_1')
    query.edit_message_text = AsyncMock()

    await handlers.retry_callback(update, ctx)

    query.edit_message_text.assert_awaited_once()
    assert (100, 'retry_5_1') in ctx.bot_data['retries']

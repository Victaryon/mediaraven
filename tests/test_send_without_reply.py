"""Mensagem com o link apagada durante o download: a mídia sai sem o reply."""
from unittest.mock import AsyncMock, patch

import pytest
from telegram import InputMediaPhoto
from telegram.ext import Defaults, ExtBot


@pytest.mark.asyncio
async def test_defaults_allow_sending_without_reply_reach_media_calls():
    bot = ExtBot("1:A", defaults=Defaults(allow_sending_without_reply=True))
    with patch.object(ExtBot, "_do_post", AsyncMock(return_value=[])) as post:
        try:
            await bot.send_photo(1, photo="AgAD", reply_to_message_id=10)
        except Exception:
            pass
        try:
            await bot.send_media_group(1, [InputMediaPhoto("AgAD"), InputMediaPhoto("AgAE")], reply_to_message_id=10)
        except Exception:
            pass
    assert post.await_count == 2
    for call in post.await_args_list:
        params = call.kwargs.get("data") or call.args[1]
        assert params["reply_parameters"].allow_sending_without_reply is True

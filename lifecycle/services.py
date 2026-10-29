import asyncio
import logging
import os

import aiohttp
from cachetools import TTLCache
from playwright.async_api import async_playwright

import metrics
import state
from config import (
    AIOHTTP_CONN_LIMIT,
    AIOHTTP_CONNECT_TIMEOUT,
    AIOHTTP_READ_TIMEOUT,
    AIOHTTP_TOTAL_TIMEOUT,
    METRICS_LOG_INTERVAL_MIN,
    SHUTDOWN_TASKS_TIMEOUT,
    TTL_FUTURES_SECONDS,
    TTL_RETRIES_SECONDS,
)
from messages import lmsg

from .playwright_refresh import new_context_with_cookies, periodic_playwright_refresh
from .startup import startup_cleanup_async

logger = logging.getLogger(__name__)


def get_chat_lock(chat_id: int) -> asyncio.Lock:
    """Retorna o Lock do chat, criando dentro do event loop ativo.

    Armazenado em state.chat_locks (WeakValueDictionary) para que seja coletado
    pelo GC quando nenhum download estiver segurando o lock — evita leak em
    bots que conversam com muitos chats distintos.
    """
    lock = state.chat_locks.get(chat_id)
    if lock is None:
        lock = asyncio.Lock()
        state.chat_locks[chat_id] = lock
    return lock


async def periodic_metrics_log() -> None:
    while True:
        await asyncio.sleep(METRICS_LOG_INTERVAL_MIN * 60)
        try:
            logger.info(metrics.format_summary())
        except Exception as e:
            logger.debug(lmsg("metrics_log.falha_ao_logar", e=e))


async def init_globals(app) -> None:
    await startup_cleanup_async()

    connector = aiohttp.TCPConnector(limit=AIOHTTP_CONN_LIMIT)
    default_timeout = aiohttp.ClientTimeout(
        total=AIOHTTP_TOTAL_TIMEOUT,
        connect=AIOHTTP_CONNECT_TIMEOUT,
        sock_read=AIOHTTP_READ_TIMEOUT,
    )
    state.AIOHTTP_SESSION = aiohttp.ClientSession(
        connector=connector, timeout=default_timeout,
        # HTTPS_PROXY/NO_PROXY do ambiente; sem eles nada muda.
        trust_env=True,
    )
    logger.info(lmsg("services.sess_o_aiohttp_global", AIOHTTP_TOTAL_TIMEOUT=AIOHTTP_TOTAL_TIMEOUT))

    logger.info(lmsg("services.iniciando_playwright_navegador"))
    state.PW_MANAGER = await async_playwright().start()
    # O Chromium ignora HTTPS_PROXY do ambiente; precisa vir no launch.
    proxy = os.environ.get("HTTPS_PROXY")
    state.PW_BROWSER = await state.PW_MANAGER.chromium.launch(
        headless=True,
        proxy={"server": proxy, "bypass": os.environ.get("NO_PROXY", "")} if proxy else None,
    )
    state.PW_CONTEXT = await new_context_with_cookies()

    logger.info(lmsg("services.contexto_playwright_pronto"))

    app.bot_data['lang_requests'] = TTLCache(maxsize=1000, ttl=TTL_RETRIES_SECONDS)
    app.bot_data['retries'] = TTLCache(maxsize=1000, ttl=TTL_RETRIES_SECONDS)
    app.bot_data['dl_futures'] = TTLCache(maxsize=1000, ttl=TTL_FUTURES_SECONDS)
    app.bot_data['lang_futures'] = TTLCache(maxsize=1000, ttl=TTL_FUTURES_SECONDS)
    app.bot_data['caption_futures'] = TTLCache(maxsize=1000, ttl=TTL_FUTURES_SECONDS)
    app.bot_data['screenshot_futures'] = TTLCache(maxsize=1000, ttl=TTL_FUTURES_SECONDS)
    logger.info(lmsg("services.todos_os_servi_os"))

    state.periodic_tasks.add(asyncio.create_task(periodic_playwright_refresh()))
    logger.info(lmsg("services.tarefa_de_limpeza"))

    state.periodic_tasks.add(asyncio.create_task(periodic_metrics_log()))
    logger.info(lmsg("services.log_peri_dico_de"))


async def stop_globals(app) -> None:
    logger.info(lmsg("services.desligando_servi_os_globais"))

    for t in state.periodic_tasks:
        t.cancel()
    await asyncio.gather(*state.periodic_tasks, return_exceptions=True)
    state.periodic_tasks.clear()

    pending = [t for t in state.background_tasks if not t.done()]
    if pending:
        logger.info(lmsg("services.aguardando_x_download", arg0=len(pending), SHUTDOWN_TASKS_TIMEOUT=SHUTDOWN_TASKS_TIMEOUT))
        try:
            await asyncio.wait_for(
                asyncio.gather(*pending, return_exceptions=True),
                timeout=SHUTDOWN_TASKS_TIMEOUT,
            )
            logger.info(lmsg("services.downloads_pendentes_finalizados"))
        except asyncio.TimeoutError:
            still_pending = [t for t in pending if not t.done()]
            logger.warning(lmsg("services.x_task_s", arg0=len(still_pending)))
            for t in still_pending:
                t.cancel()
            await asyncio.gather(*still_pending, return_exceptions=True)

    # Cada um separado: se o Chromium já morreu (SIGTERM do systemd pro grupo
    # todo), o close() do contexto falha e não pode impedir o stop() do manager.
    for name, closer in (
        ('AIOHTTP_SESSION', lambda o: o.close()),
        ('PW_CONTEXT', lambda o: o.close()),
        ('PW_BROWSER', lambda o: o.close()),
        ('PW_MANAGER', lambda o: o.stop()),
    ):
        obj = getattr(state, name, None)
        if obj is None:
            continue
        try:
            await closer(obj)
        except Exception as e:
            logger.debug(lmsg("services.falha_ao_desligar", pool_name=name, e=e))

    for pool_name in ('YTDLP_POOL', 'IG_POOL', 'IO_POOL'):
        pool = getattr(state, pool_name, None)
        if pool is not None:
            try:
                pool.shutdown(wait=False, cancel_futures=True)
            except Exception as e:
                logger.debug(lmsg("services.falha_ao_desligar", pool_name=pool_name, e=e))

    logger.info(lmsg("services.shutdown_completo"))

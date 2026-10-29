"""Estado global mutável compartilhado entre módulos.

Use `import state` + `state.NOME`. NÃO use `from state import NOME`:
variáveis reatribuídas em init_globals/periodic_playwright_refresh ficam
dessincronizadas no namespace do importador.
"""
import asyncio
import contextvars
import threading
import weakref
from concurrent.futures import ThreadPoolExecutor

from config import IG_WORKERS, IO_WORKERS, PW_CONCURRENCY, YTDLP_WORKERS

FIREFOX_COOKIES_CACHE = []

chat_locks: "weakref.WeakValueDictionary[int, asyncio.Lock]" = weakref.WeakValueDictionary()

YTDLP_POOL = ThreadPoolExecutor(max_workers=YTDLP_WORKERS, thread_name_prefix='ytdlp_pool')
IG_POOL = ThreadPoolExecutor(max_workers=IG_WORKERS, thread_name_prefix='ig_pool')
IO_POOL = ThreadPoolExecutor(max_workers=IO_WORKERS, thread_name_prefix='io_pool')

ig_pending_lock = threading.Lock()
ig_pending_count = 0


def ig_pending_inc() -> int:
    global ig_pending_count
    with ig_pending_lock:
        ig_pending_count += 1
        return ig_pending_count


def ig_pending_dec() -> int:
    global ig_pending_count
    with ig_pending_lock:
        ig_pending_count = max(0, ig_pending_count - 1)
        return ig_pending_count



background_tasks = set()
# Loops de manutenção (refresh do Playwright, métricas); cancelados no shutdown.
periodic_tasks = set()

# Aviso extra pro usuário sobre o download atual (ex.: álbum incompleto).
# O dispatcher grava; o handler envia depois da mídia.
download_notice: contextvars.ContextVar[str] = contextvars.ContextVar("download_notice", default="")

DENO_PATH = None
FFMPEG_PATH = None
FFPROBE_PATH = None

PW_MANAGER = None
PW_BROWSER = None
PW_CONTEXT = None

AIOHTTP_SESSION = None
PW_SEMAPHORE = asyncio.Semaphore(PW_CONCURRENCY)

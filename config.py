import contextvars
import json
import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Any, Optional

from dotenv import load_dotenv

load_dotenv()

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

_boot_logger = logging.getLogger("config")


def _csv_ints(raw: str, var_name: str = "") -> list[int]:
    out: list[int] = []
    for piece in raw.split(","):
        piece = piece.strip()
        if not piece:
            continue
        try:
            out.append(int(piece))
        except ValueError:
            _boot_logger.warning(
                f"⚠️ {var_name or 'CSV int'}: valor inválido {piece!r} ignorado."
            )
    return out


def _csv_strings(raw: str) -> list[str]:
    return [p.strip() for p in raw.split(",") if p.strip()]


def _env_num(name: str, default, cast):
    raw = os.getenv(name, "")
    if not raw:
        return default
    try:
        return cast(raw)
    except ValueError:
        _boot_logger.warning(
            f"⚠️ Env var {name}={raw!r} não é {cast.__name__}; usando default {default}."
        )
        return default


def _env_int(name: str, default: int) -> int:
    return _env_num(name, default, int)


def _env_float(name: str, default: float) -> float:
    return _env_num(name, default, float)


def _env_str(name: str, default: str) -> str:
    val = os.getenv(name)
    return val if val else default


def _env_yesno(name: str, default: str) -> str:
    raw = (os.getenv(name, "") or default).strip().lower()
    return "yes" if raw in ("yes", "y", "true", "1", "on") else "no"


TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

ALLOWED_CHAT_ID: list[int] = _csv_ints(os.getenv("ALLOWED_CHAT_ID", ""), "ALLOWED_CHAT_ID")
ALLOWED_USER_ID: list[int] = _csv_ints(os.getenv("ALLOWED_USER_IDS", ""), "ALLOWED_USER_IDS")
ALLOW_ALL = _env_yesno("ALLOW_ALL", "no")

LOCAL_API_HOST = os.getenv("LOCAL_API_HOST", "")
LOCAL_API_URL = f"http://{LOCAL_API_HOST}/bot"
LOCAL_FILE_URL = f"http://{LOCAL_API_HOST}/file/bot"

BASE_DOWNLOAD_DIR = os.getenv("BASE_DOWNLOAD_DIR", "")
FIREFOX_PROFILE_PATH = os.getenv("FIREFOX_PROFILE_PATH", "")

_IMAGE_EXTS_DEFAULT = ('.jpg', '.jpeg', '.png', '.webp', '.heic', '.bmp', '.tiff', '.jfif', '.avif', '.ico', '.svg')
_VIDEO_EXTS_DEFAULT = ('.mp4', '.mkv', '.webm', '.avi', '.mov', '.flv', '.m4v')
_ANIMATION_EXTS_DEFAULT = ('.gif',)
_image_extra = tuple(e if e.startswith('.') else f'.{e}' for e in _csv_strings(os.getenv("IMAGE_EXTS_EXTRA", "")))
_video_extra = tuple(e if e.startswith('.') else f'.{e}' for e in _csv_strings(os.getenv("VIDEO_EXTS_EXTRA", "")))
_animation_extra = tuple(e if e.startswith('.') else f'.{e}' for e in _csv_strings(os.getenv("ANIMATION_EXTS_EXTRA", "")))
IMAGE_EXTS = _IMAGE_EXTS_DEFAULT + _image_extra
VIDEO_EXTS = _VIDEO_EXTS_DEFAULT + _video_extra
ANIMATION_EXTS = _ANIMATION_EXTS_DEFAULT + _animation_extra

IG_QUEUE_WARN_THRESHOLD = _env_int("IG_QUEUE_WARN_THRESHOLD", 5)

LOG_FILE_PATH = os.path.join(_BASE_DIR, "bot.log")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_MAX_BYTES = _env_int("LOG_MAX_BYTES", 20 * 1024 * 1024)
LOG_BACKUP_COUNT = _env_int("LOG_BACKUP_COUNT", 5)

ASK_DL_TIMEOUT = _env_float("ASK_DL_TIMEOUT", 5.0)
ASK_LANG_TIMEOUT = _env_float("ASK_LANG_TIMEOUT", 10.0)
ASK_CAPTION_TIMEOUT = _env_float("ASK_CAPTION_TIMEOUT", 5.0)
ASK_ARTICLE_TIMEOUT = _env_float("ASK_ARTICLE_TIMEOUT", 5.0)
ASK_SCREENSHOT_TIMEOUT = _env_float("ASK_SCREENSHOT_TIMEOUT", 5.0)
ASK_DL_DEFAULT = _env_yesno("ASK_DL_DEFAULT", "yes")
ASK_CAPTION_DEFAULT = _env_yesno("ASK_CAPTION_DEFAULT", "no")
ASK_ARTICLE_DEFAULT = _env_yesno("ASK_ARTICLE_DEFAULT", "yes")
ASK_SCREENSHOT_DEFAULT = _env_yesno("ASK_SCREENSHOT_DEFAULT", "yes")

PROMPT_DOWNLOAD_ENABLED = True
PROMPT_CAPTION_ENABLED = True
PROMPT_LANG_ENABLED = True


def should_show_prompt(kind: str, chat_id: Optional[int] = None, user_id: Optional[int] = None) -> bool:
    v = cfg(f"PROMPT_{kind.upper()}_ENABLED", chat_id, user_id)
    return True if v is None else bool(v)

YTDLP_MAX_HEIGHT = _env_int("YTDLP_MAX_HEIGHT", 1920)
YTDLP_HLS_MAX_HEIGHT = _env_int("YTDLP_HLS_MAX_HEIGHT", 720)
YTDLP_SOCKET_TIMEOUT = _env_int("YTDLP_SOCKET_TIMEOUT", 90)
YTDLP_YT_CLIENTS = _env_str("YTDLP_YT_CLIENTS", "default")
TIKTOK_PROXY = _env_str("TIKTOK_PROXY", "")
YTDLP_WORKERS = _env_int("YTDLP_WORKERS", 5)
IG_WORKERS = _env_int("IG_WORKERS", 1)
IO_WORKERS = _env_int("IO_WORKERS", 4)
PW_CONCURRENCY = _env_int("PW_CONCURRENCY", 3)

MAX_URLS_PER_MESSAGE = _env_int("MAX_URLS_PER_MESSAGE", 20)
IGNORED_DOMAINS: list[str] = _csv_strings(os.getenv("IGNORED_DOMAINS", ""))
DOWNLOAD_TIMEOUT_SECONDS = _env_int("DOWNLOAD_TIMEOUT_SECONDS", 15)
DOWNLOAD_SEGMENTS = _env_int("DOWNLOAD_SEGMENTS", 4)
# Chat que recebe aviso de erro inesperado (0 = desligado).
ERROR_NOTIFY_CHAT_ID = _env_int("ERROR_NOTIFY_CHAT_ID", 0)
SAFE_URL_MAX_LENGTH = _env_int("SAFE_URL_MAX_LENGTH", 200)
STATUS_CYCLE_INTERVAL = _env_float("STATUS_CYCLE_INTERVAL", 5.0)

AIOHTTP_TOTAL_TIMEOUT = _env_int("AIOHTTP_TOTAL_TIMEOUT", 30)
AIOHTTP_CONNECT_TIMEOUT = _env_int("AIOHTTP_CONNECT_TIMEOUT", 10)
AIOHTTP_READ_TIMEOUT = _env_int("AIOHTTP_READ_TIMEOUT", 20)
AIOHTTP_CONN_LIMIT = _env_int("AIOHTTP_CONN_LIMIT", 50)

PW_GOTO_TIMEOUT_MS = _env_int("PW_GOTO_TIMEOUT_MS", 25000)
PLAYWRIGHT_UA = _env_str(
    "PLAYWRIGHT_UA",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
)
PW_VIEWPORT_WIDTH = _env_int("PW_VIEWPORT_WIDTH", 1920)
PW_VIEWPORT_HEIGHT = _env_int("PW_VIEWPORT_HEIGHT", 1080)

SCRAPE_MAX_PARALLEL_DOWNLOADS = _env_int("SCRAPE_MAX_PARALLEL_DOWNLOADS", 6)
SCRAPE_MAX_MEDIA_URLS = _env_int("SCRAPE_MAX_MEDIA_URLS", 60)
SCRAPE_SCROLL_MAX_ROUNDS = _env_int("SCRAPE_SCROLL_MAX_ROUNDS", 4)
SCRAPE_SCROLL_PAUSE_MS = _env_int("SCRAPE_SCROLL_PAUSE_MS", 3000)
SCRAPE_MIN_IMAGE_SIZE = _env_int("SCRAPE_MIN_IMAGE_SIZE", 50)
SCRAPE_HLS_TIMEOUT_S = _env_int("SCRAPE_HLS_TIMEOUT_S", 180)
SCRAPE_FAST_PATH_TIMEOUT_S = _env_int("SCRAPE_FAST_PATH_TIMEOUT_S", 12)
SCRAPE_SCREENSHOT_FALLBACK = _env_yesno("SCRAPE_SCREENSHOT_FALLBACK", "yes")
SCRAPE_GALLERY_DL_ENABLE = _env_yesno("SCRAPE_GALLERY_DL_ENABLE", "yes")
SCRAPE_GALLERY_DL_TIMEOUT_S = _env_int("SCRAPE_GALLERY_DL_TIMEOUT_S", 90)
SCRAPE_GALLERY_DL_PARALLEL_FILES = _env_int("SCRAPE_GALLERY_DL_PARALLEL_FILES", 3)
SCRAPE_PAYWALL_BYPASS = _env_yesno("SCRAPE_PAYWALL_BYPASS", "yes")
SCRAPE_ARCHIVE_TIMEOUT_S = _env_int("SCRAPE_ARCHIVE_TIMEOUT_S", 15)
SCRAPE_ARTICLE_EXTRACT = _env_yesno("SCRAPE_ARTICLE_EXTRACT", "yes")
SCRAPE_ARTICLE_MIN_CHARS = _env_int("SCRAPE_ARTICLE_MIN_CHARS", 300)

PW_REFRESH_RSS_MB_THRESHOLD = _env_int("PW_REFRESH_RSS_MB_THRESHOLD", 1500)
PW_REFRESH_CHECK_INTERVAL_MIN = _env_int("PW_REFRESH_CHECK_INTERVAL_MIN", 15)
PW_REFRESH_MIN_INTERVAL_MIN = _env_int("PW_REFRESH_MIN_INTERVAL_MIN", 30)
PW_REFRESH_MAX_INTERVAL_HOURS = _env_int("PW_REFRESH_MAX_INTERVAL_HOURS", 6)

TELEGRAM_UPLOAD_TIMEOUT = _env_int("TELEGRAM_UPLOAD_TIMEOUT", 600)
TELEGRAM_MAX_UPLOAD_MB = _env_int("TELEGRAM_MAX_UPLOAD_MB", 2000)
VIDEO_CONVERT_TIMEOUT = _env_int("VIDEO_CONVERT_TIMEOUT", 900)
MEDIA_GROUP_DELAY = _env_float("MEDIA_GROUP_DELAY", 4.0)
MEDIA_GROUP_CHUNK_SIZE = _env_int("MEDIA_GROUP_CHUNK_SIZE", 10)

METRICS_LOG_INTERVAL_MIN = _env_int("METRICS_LOG_INTERVAL_MIN", 30)
TTL_RETRIES_SECONDS = _env_int("TTL_RETRIES_SECONDS", 3600)
TTL_FUTURES_SECONDS = _env_int("TTL_FUTURES_SECONDS", 300)

SHUTDOWN_TASKS_TIMEOUT = _env_float("SHUTDOWN_TASKS_TIMEOUT", 30.0)

IG_USER_AGENT = _env_str("IG_USER_AGENT", "Instagram 219.0.0.12.117 Android")
IG_CAPTION_MAX = _env_int("IG_CAPTION_MAX", 1000)

THREADS_MIN_IMAGE_SIZE = _env_int("THREADS_MIN_IMAGE_SIZE", 500)

AIOHTTP_UA_DEFAULT = _env_str(
    "AIOHTTP_UA_DEFAULT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
)
REDDIT_JSON_UA = _env_str(
    "REDDIT_JSON_UA",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
)


_NOISY_LIBS = (
    'httpx', 'httpcore', 'urllib3', 'asyncio', 'PIL',
    'gallery_dl', 'telegram._utils', 'telegram.ext._updater',
    'apscheduler', 'curl_cffi', 'playwright',
    'trafilatura', 'htmldate', 'courlan', 'charset_normalizer',
)


def setup_logging() -> None:
    root = logging.getLogger()
    if root.handlers:
        return
    level = getattr(logging, LOG_LEVEL, logging.INFO)
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(name)s:%(lineno)d - %(message)s'
    )
    file_handler = RotatingFileHandler(
        LOG_FILE_PATH,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding='utf-8',
    )
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root.setLevel(level)
    root.addHandler(file_handler)
    root.addHandler(stream_handler)

    if level > logging.DEBUG:
        for noisy in _NOISY_LIBS:
            logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.captureWarnings(True)


_CUSTOM_FILE = os.path.join(_BASE_DIR, "customization.json")
_CUSTOM_EXAMPLE = os.path.join(_BASE_DIR, "customization.example.json")


def _load_customization() -> dict:
    path = _CUSTOM_FILE if os.path.exists(_CUSTOM_FILE) else _CUSTOM_EXAMPLE
    if not os.path.exists(path):
        return {"default": {}, "chats": {}, "users": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        _boot_logger.warning(f"⚠️ Falha ao ler {path}: {e}")
        return {"default": {}, "chats": {}, "users": {}}
    return {
        "default": data.get("default") or {},
        "chats": data.get("chats") or {},
        "users": data.get("users") or {},
    }


_CUSTOMIZATION: dict = _load_customization()

request_context: contextvars.ContextVar[tuple[Optional[int], Optional[int]]] = (
    contextvars.ContextVar("request_context", default=(None, None))
)


def cfg(key: str, chat_id: Optional[int] = None, user_id: Optional[int] = None) -> Any:
    """Resolve config: user > chat > customization.default > .env (module-level constant)."""
    if chat_id is None and user_id is None:
        chat_id, user_id = request_context.get()

    if user_id is not None:
        u = _CUSTOMIZATION["users"].get(str(user_id))
        if isinstance(u, dict) and key in u:
            return u[key]
    if chat_id is not None:
        c = _CUSTOMIZATION["chats"].get(str(chat_id))
        if isinstance(c, dict) and key in c:
            return c[key]
    d = _CUSTOMIZATION["default"]
    if key in d:
        return d[key]
    return globals().get(key)


def validate_runtime_config() -> list[str]:
    errors: list[str] = []
    if not BASE_DOWNLOAD_DIR:
        errors.append("BASE_DOWNLOAD_DIR não configurado no .env (obrigatório).")
    elif not os.path.isabs(BASE_DOWNLOAD_DIR):
        errors.append(f"BASE_DOWNLOAD_DIR deve ser um caminho absoluto (got: {BASE_DOWNLOAD_DIR!r}).")
    else:
        try:
            os.makedirs(BASE_DOWNLOAD_DIR, exist_ok=True)
        except OSError as e:
            errors.append(f"Não foi possível criar BASE_DOWNLOAD_DIR={BASE_DOWNLOAD_DIR}: {e}")

    if not LOCAL_API_HOST:
        errors.append("LOCAL_API_HOST não configurado no .env (obrigatório).")

    return errors

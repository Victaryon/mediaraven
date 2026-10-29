import logging
import os
import shutil
import sqlite3
import tempfile
from urllib.parse import urlparse

import state
from config import FIREFOX_PROFILE_PATH
from messages import lmsg

logger = logging.getLogger(__name__)


def extract_firefox_cookies() -> list[dict]:
    db_path = os.path.join(FIREFOX_PROFILE_PATH, 'cookies.sqlite')
    if not os.path.exists(db_path):
        logger.warning(lmsg("cookies.banco_de_cookies", db_path=db_path))
        return []

    # Copia o banco junto com o -wal/-shm: com o Firefox aberto, cookies
    # recém-gravados ainda estão só no WAL.
    temp_dir = tempfile.mkdtemp(prefix="ffcookies_")
    temp_db = os.path.join(temp_dir, 'cookies.sqlite')

    cookies = []
    MAX_PLAYWRIGHT_EXPIRY = 253402300799

    conn = None
    try:
        for suffix in ('', '-wal', '-shm'):
            if os.path.exists(db_path + suffix):
                shutil.copy2(db_path + suffix, temp_db + suffix)

        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT name, value, host, path, expiry, isSecure, isHttpOnly FROM moz_cookies")

        for row in cursor.fetchall():
            name, value, host, path, expiry, isSecure, isHttpOnly = row

            clean_expires = -1
            if expiry is not None:
                try:
                    val = int(float(expiry))
                    # Firefox recente grava expiry em milissegundos.
                    if val > 10**11:
                        val //= 1000
                    if val > MAX_PLAYWRIGHT_EXPIRY:
                        clean_expires = MAX_PLAYWRIGHT_EXPIRY
                    elif val > 0:
                        clean_expires = val
                except (ValueError, TypeError):
                    pass

            cookies.append({
                'name': name,
                'value': value,
                'domain': host,
                'path': path,
                'expires': clean_expires,
                'secure': bool(isSecure),
                'httpOnly': bool(isHttpOnly)
            })
    except Exception as e:
        logger.error(lmsg("cookies.erro_ao_ler", e=e), exc_info=True)
    finally:
        if conn is not None:
            conn.close()
        shutil.rmtree(temp_dir, ignore_errors=True)

    return cookies


def get_aiohttp_cookies_for_url(url: str) -> dict[str, str]:
    host = (urlparse(url).hostname or '').lower()

    def _matches(cookie_domain: str) -> bool:
        cookie_domain = cookie_domain.lstrip('.').lower()
        return host == cookie_domain or host.endswith('.' + cookie_domain)

    return {c['name']: c['value'] for c in state.FIREFOX_COOKIES_CACHE if _matches(c['domain'])}

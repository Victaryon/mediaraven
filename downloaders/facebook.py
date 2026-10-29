import logging
import os
import re
from typing import Optional

from messages import lmsg, msg
from utils import safe_url

from .fallback import _gallery_dl_run

logger = logging.getLogger(__name__)


_FB_NUMERIC_USER_RE = re.compile(r'facebook\.com/(\d+)/')


def facebook_owner_mismatch(url: str, info_dict: Optional[dict]) -> bool:
    if not info_dict:
        return False
    m = _FB_NUMERIC_USER_RE.search(url or '')
    if not m:
        return False
    url_uid = m.group(1)
    yt_uid = str(info_dict.get('uploader_id') or '')
    if not yt_uid:
        return False
    return yt_uid != url_uid


async def download_facebook_gallery(
    url: str, unique_folder: str,
) -> tuple[list[str], str, str, str]:
    logger.info(lmsg("facebook.tentando_gallery_dl", arg0=safe_url(url)))
    os.makedirs(unique_folder, exist_ok=True)

    files = await _gallery_dl_run(url, unique_folder)
    if not files:
        return [], "", "", ""

    logger.info(lmsg("facebook.gallery_dl_ok", n=len(files)))
    return (
        files,
        msg("downloader_status.facebook_gallery", count=len(files)),
        "",
        "",
    )

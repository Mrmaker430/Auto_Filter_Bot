# monkey_patch.py
"""
Fast cover attach — monkey patch for AutoFilter bot.

No AI. Just TMDB posters, disk-cached, concurrent, skip-if-present.

Import FIRST in bot.py:
    import monkey_patch  # noqa: F401

Env:
    COVER_ATTACH_ENABLED=true|false   (default: true)
    DB_CHANNEL_ID=-100123...          (required)
    TMDB_API_KEY or TMDB_BEARER_TOKEN (required)
    COVER_CACHE_DIR=./poster_cache    (default)
"""

import asyncio
import hashlib
import io
import logging
import os
import re
from functools import wraps
from pathlib import Path
from typing import Optional, Tuple

import aiohttp
from PIL import Image

log = logging.getLogger(__name__)

# ==================================================================
# CONFIG
# ==================================================================
try:
    import info
    _DEFAULT_DB_CHANNEL = getattr(info, "BIN_CHANNEL", 0) or getattr(info, "LOG_CHANNEL", 0)
    _DEFAULT_TMDB_KEY = getattr(info, "TMDB_API_KEY", "")
except Exception:
    _DEFAULT_DB_CHANNEL = 0
    _DEFAULT_TMDB_KEY = ""

COVER_ENABLED   = os.getenv("COVER_ATTACH_ENABLED", "true").lower() == "true"
DB_CHANNEL_ID   = int(os.getenv("DB_CHANNEL_ID") or _DEFAULT_DB_CHANNEL or "0")
TMDB_API_KEY    = os.getenv("TMDB_API_KEY") or _DEFAULT_TMDB_KEY
TMDB_BEARER     = os.getenv("TMDB_BEARER_TOKEN", "")
CACHE_DIR       = Path(os.getenv("COVER_CACHE_DIR", "./poster_cache"))

THUMB_MAX_BYTES = 200 * 1024
THUMB_MAX_DIM   = 320
HTTP_TIMEOUT    = 10
TMDB_SEM        = asyncio.Semaphore(8)   # cap concurrent TMDB calls
UPLOAD_SEM      = asyncio.Semaphore(4)   # cap concurrent reuploads

_PATCHED = False
_RUNNING_CLIENT = None
CACHE_DIR.mkdir(parents=True, exist_ok=True)


# ==================================================================
# THUMB PREP — fast path
# ==================================================================
def _prepare_thumb(image_bytes: bytes) -> Optional[io.BytesIO]:
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception:
        return None

    img.thumbnail((THUMB_MAX_DIM, THUMB_MAX_DIM), Image.BILINEAR)

    for q in (85, 70, 55, 40):
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=q, optimize=False)
        if buf.tell() <= THUMB_MAX_BYTES:
            buf.seek(0)
            return buf
    return None


# ==================================================================
# TITLE EXTRACTION
# ==================================================================
_JUNK = re.compile(
    r'\b(?:480p|540p|720p|1080p|1440p|2160p|4k|8k|HDTV|WEB[- ]?DL|WEBRip|'
    r'WEB|BluRay|BRRip|BDRip|HDRip|DVDRip|HDCAM|HDTS|x264|x265|h\.?264|h\.?265|'
    r'HEVC|AVC|10bit|8bit|AAC|AC3|DTS|TrueHD|FLAC|MP3|ESubs|Subs|Dubbed|'
    r'Dual[ -]?Audio|Multi[ -]?Audio|ORG|AMZN|NF|DSNP|HMAX|ATVP|iTunes|'
    r'Remux|Proper|Repack|MKV|MP4|AVI|MOV|WEBM)\b',
    re.IGNORECASE
)
_EXT = re.compile(r'\.(mkv|mp4|avi|mov|webm|flv|wmv|ts|m2ts|m4v|mp3|m4a)$', re.I)
_SXXEXX = re.compile(r'[Ss](\d{1,2})[\s\.\-_]*[Ee](\d{1,3})')


def _extract_title(media) -> Tuple[str, Optional[int]]:
    raw = ""
    if getattr(media, "caption", None):
        raw = media.caption
    elif getattr(media, "document", None) and getattr(media.document, "file_name", None):
        raw = media.document.file_name
    elif getattr(media, "video", None) and getattr(media.video, "file_name", None):
        raw = media.video.file_name
    elif getattr(media, "audio", None):
        raw = getattr(media.audio, "title", None) or getattr(media.audio, "file_name", None) or ""

    raw = _EXT.sub('', raw)
    raw = _SXXEXX.sub(' ', raw)

    year = None
    ym = re.search(r'(?<!\d)(19\d{2}|20\d{2})(?!\d)', raw)
    if ym:
        year = int(ym.group(1))
        raw = raw[:ym.start()] + ' ' + raw[ym.end():]

    cleaned = _JUNK.sub(' ', raw)
    cleaned = re.sub(r'[\._\-]+', ' ', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned or raw, year


# ==================================================================
# DISK CACHE
# ==================================================================
def _cache_key(title: str, year: Optional[int]) -> Path:
    h = hashlib.md5(f"{title.lower()}|{year or ''}".encode()).hexdigest()
    return CACHE_DIR / f"{h}.jpg"


def _cache_get(title: str, year: Optional[int]) -> Optional[bytes]:
    p = _cache_key(title, year)
    if p.exists() and p.stat().st_size > 512:
        try:
            return p.read_bytes()
        except Exception:
            return None
    return None


def _cache_put(title: str, year: Optional[int], data: bytes):
    try:
        _cache_key(title, year).write_bytes(data)
    except Exception:
        pass


# ==================================================================
# TMDB POSTER — cached, concurrent, single-shot
# ==================================================================
async def _fetch_poster(title: str, year: Optional[int]) -> Optional[bytes]:
    if not title:
        return None

    cached = _cache_get(title, year)
    if cached:
        return cached

    if not (TMDB_API_KEY or TMDB_BEARER):
        return None

    headers = {"Authorization": f"Bearer {TMDB_BEARER}"} if TMDB_BEARER else {}
    params = {"api_key": TMDB_API_KEY} if TMDB_API_KEY else {}
    params.update({"query": title, "include_adult": "false"})
    if year:
        params["year"] = year

    async with TMDB_SEM:
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT)
            ) as s:
                # Try movie first, then tv
                for mtype in ("movie", "tv"):
                    async with s.get(
                        f"https://api.themoviedb.org/3/search/{mtype}",
                        params=params, headers=headers, ssl=False,
                    ) as r:
                        if r.status != 200:
                            continue
                        data = await r.json()

                    results = data.get("results", [])
                    if not results:
                        continue

                    results.sort(key=lambda x: x.get("popularity", 0), reverse=True)
                    path = results[0].get("poster_path")
                    if not path:
                        continue

                    async with s.get(
                        f"https://image.tmdb.org/t/p/w342{path}", ssl=False
                    ) as r:
                        if r.status == 200:
                            img = await r.read()
                            if len(img) > 512:
                                _cache_put(title, year, img)
                                return img
        except Exception as e:
            log.debug("Poster fetch failed for %r: %s", title, e)

    return None


# ==================================================================
# RE-UPLOAD WITH COVER
# ==================================================================
async def _reupload_with_cover(client, media, poster_bytes: bytes) -> Optional[str]:
    thumb = _prepare_thumb(poster_bytes)
    if not thumb:
        return None

    buf = io.BytesIO()
    await client.download_media(media, file_name=buf)
    buf.seek(0)
    caption = media.caption or ""

    async with UPLOAD_SEM:
        try:
            if media.document:
                msg = await client.send_document(
                    chat_id=DB_CHANNEL_ID, document=buf, thumb=thumb,
                    caption=caption,
                    file_name=getattr(media.document, "file_name", None) or "file.bin",
                )
                return msg.document.file_id

            if media.video:
                msg = await client.send_video(
                    chat_id=DB_CHANNEL_ID, video=buf, thumb=thumb,
                    caption=caption,
                    duration=getattr(media.video, "duration", 0) or 0,
                    width=getattr(media.video, "width", 0) or 0,
                    height=getattr(media.video, "height", 0) or 0,
                    file_name=getattr(media.video, "file_name", None) or "video.mp4",
                )
                return msg.video.file_id

            if media.audio:
                msg = await client.send_audio(
                    chat_id=DB_CHANNEL_ID, audio=buf, thumb=thumb,
                    caption=caption,
                    file_name=getattr(media.audio, "file_name", None) or "audio.mp3",
                )
                return msg.audio.file_id
        except Exception as e:
            log.warning("Reupload with cover failed: %s", e)

    return None


# ==================================================================
# HAS-THUMB GUARD — skip work if file already carries a cover
# ==================================================================
def _already_has_thumb(media) -> bool:
    for kind in ("document", "video", "audio"):
        obj = getattr(media, kind, None)
        if obj and getattr(obj, "thumbs", None):
            return True
    return False


# ==================================================================
# PATCH ia_filterdb.save_file
# ==================================================================
def _patch_save_file() -> bool:
    try:
        from database import ia_filterdb
    except ImportError as e:
        log.error("ia_filterdb import failed: %s", e)
        return False

    original = getattr(ia_filterdb, "save_file", None)
    if original is None:
        log.error("save_file not found")
        return False

    if getattr(original, "_cover_patched", False):
        return True

    @wraps(original)
    async def patched_save_file(media, *args, **kwargs):
        if not COVER_ENABLED or not DB_CHANNEL_ID:
            return await original(media, *args, **kwargs)

        # Fast skip — file already has a thumbnail
        if _already_has_thumb(media):
            return await original(media, *args, **kwargs)

        client = getattr(media, "_client", None) or _RUNNING_CLIENT
        if client is None:
            return await original(media, *args, **kwargs)

        try:
            title, year = _extract_title(media)
            if title:
                poster = await _fetch_poster(title, year)
                if poster:
                    new_id = await _reupload_with_cover(client, media, poster)
                    if new_id:
                        for kind in ("document", "video", "audio"):
                            obj = getattr(media, kind, None)
                            if obj:
                                obj.file_id = new_id
                                break
        except Exception as e:
            log.exception("Cover attach error: %s", e)

        return await original(media, *args, **kwargs)

    patched_save_file._cover_patched = True
    ia_filterdb.save_file = patched_save_file
    log.info("✅ Patched save_file [cover attach]")
    return True


# ==================================================================
# PATCH Client.__init__ — expose running instance
# ==================================================================
def _patch_media_client() -> bool:
    try:
        from pyrogram import Client
    except ImportError:
        return False

    original = Client.__init__
    if getattr(original, "_cover_patched", False):
        return True

    @wraps(original)
    def patched_init(self, *args, **kwargs):
        original(self, *args, **kwargs)
        global _RUNNING_CLIENT
        _RUNNING_CLIENT = self

    patched_init._cover_patched = True
    Client.__init__ = patched_init
    return True


# ==================================================================
# ENTRY
# ==================================================================
def apply_all():
    global _PATCHED
    if _PATCHED:
        return
    _PATCHED = True
    _patch_media_client()
    _patch_save_file()
    log.info("Cover patches applied [enabled=%s]", COVER_ENABLED)


apply_all()

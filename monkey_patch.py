# monkey_patch.py
"""
Fast cover attach — monkey patch for AutoFilter bot.

No AI. Just TMDB posters, disk-cached, concurrent, skip-if-present.
Attaches covers when users get files through the bot.

Import FIRST in bot.py:
    import monkey_patch  # noqa: F401

Env:
    COVER_ATTACH_ENABLED=true|false   (default: true)
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
    _DEFAULT_TMDB_KEY = getattr(info, "TMDB_API_KEY", "")
except Exception:
    _DEFAULT_TMDB_KEY = ""

COVER_ENABLED   = os.getenv("COVER_ATTACH_ENABLED", "true").lower() == "true"
TMDB_API_KEY    = os.getenv("TMDB_API_KEY") or _DEFAULT_TMDB_KEY
TMDB_BEARER     = os.getenv("TMDB_BEARER_TOKEN", "")
CACHE_DIR       = Path(os.getenv("COVER_CACHE_DIR", "./poster_cache"))

THUMB_MAX_BYTES = 200 * 1024
THUMB_MAX_DIM   = 320
HTTP_TIMEOUT    = 10
TMDB_SEM        = asyncio.Semaphore(8)   # cap concurrent TMDB calls

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


def _extract_title(media_or_text) -> Tuple[str, Optional[int]]:
    raw = ""
    if isinstance(media_or_text, str):
        raw = media_or_text
    elif media_or_text is not None:
        if getattr(media_or_text, "caption", None):
            raw = media_or_text.caption
        elif getattr(media_or_text, "document", None) and getattr(media_or_text.document, "file_name", None):
            raw = media_or_text.document.file_name
        elif getattr(media_or_text, "video", None) and getattr(media_or_text.video, "file_name", None):
            raw = media_or_text.video.file_name
        elif getattr(media_or_text, "audio", None):
            raw = getattr(media_or_text.audio, "title", None) or getattr(media_or_text.audio, "file_name", None) or ""

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
# HAS-THUMB GUARD — skip work if file already carries a cover
# ==================================================================
def _already_has_thumb(media) -> bool:
    for kind in ("document", "video", "audio"):
        obj = getattr(media, kind, None)
        if obj and getattr(obj, "thumbs", None):
            return True
    return False


# ==================================================================
# HELPER TO GET POSTER THUMB FOR MEDIA / FILENAME
# ==================================================================
async def _get_poster_thumb(name_or_caption: str, year: Optional[int] = None) -> Optional[io.BytesIO]:
    if not name_or_caption:
        return None
    title, extracted_year = _extract_title(name_or_caption)
    poster_bytes = await _fetch_poster(title, year or extracted_year)
    if poster_bytes:
        return _prepare_thumb(poster_bytes)
    return None


# ==================================================================
# PATCH Pyrogram Client send_video, send_document, send_audio, send_cached_media
# ==================================================================
def _patch_client_media_send():
    try:
        from pyrogram import Client
    except ImportError:
        return False

    orig_send_video = getattr(Client, "send_video", None)
    orig_send_document = getattr(Client, "send_document", None)
    orig_send_audio = getattr(Client, "send_audio", None)
    orig_send_cached_media = getattr(Client, "send_cached_media", None)

    if orig_send_video and getattr(orig_send_video, "_cover_patched", False):
        return True

    @wraps(orig_send_video)
    async def patched_send_video(self, chat_id, video, *args, **kwargs):
        if COVER_ENABLED and kwargs.get("thumb") is None:
            caption = kwargs.get("caption") or ""
            file_name = kwargs.get("file_name") or (video if isinstance(video, str) else None)
            thumb = await _get_poster_thumb(file_name or caption)
            if thumb:
                kwargs["thumb"] = thumb
        return await orig_send_video(self, chat_id, video, *args, **kwargs)

    @wraps(orig_send_document)
    async def patched_send_document(self, chat_id, document, *args, **kwargs):
        if COVER_ENABLED and kwargs.get("thumb") is None:
            caption = kwargs.get("caption") or ""
            file_name = kwargs.get("file_name") or (document if isinstance(document, str) else None)
            thumb = await _get_poster_thumb(file_name or caption)
            if thumb:
                kwargs["thumb"] = thumb
        return await orig_send_document(self, chat_id, document, *args, **kwargs)

    @wraps(orig_send_audio)
    async def patched_send_audio(self, chat_id, audio, *args, **kwargs):
        if COVER_ENABLED and kwargs.get("thumb") is None:
            caption = kwargs.get("caption") or ""
            file_name = kwargs.get("file_name") or (audio if isinstance(audio, str) else None)
            thumb = await _get_poster_thumb(file_name or caption)
            if thumb:
                kwargs["thumb"] = thumb
        return await orig_send_audio(self, chat_id, audio, *args, **kwargs)

    @wraps(orig_send_cached_media)
    async def patched_send_cached_media(self, chat_id, file_id, *args, **kwargs):
        if COVER_ENABLED:
            try:
                from database.ia_filterdb import get_file_details
                details = await get_file_details(file_id)
                if details:
                    file_info = details[0]
                    file_name = getattr(file_info, "file_name", "")
                    file_type = getattr(file_info, "file_type", "document")
                    caption = kwargs.get("caption") or getattr(file_info, "caption", "") or file_name
                    thumb = await _get_poster_thumb(file_name or caption)
                    if thumb:
                        kwargs["thumb"] = thumb
                        if file_type == "video":
                            return await orig_send_video(self, chat_id, file_id, *args, **kwargs)
                        elif file_type == "audio":
                            return await orig_send_audio(self, chat_id, file_id, *args, **kwargs)
                        else:
                            return await orig_send_document(self, chat_id, file_id, *args, **kwargs)
            except Exception as e:
                log.debug("Fallback send_cached_media due to error: %s", e)

        return await orig_send_cached_media(self, chat_id, file_id, *args, **kwargs)

    patched_send_video._cover_patched = True
    patched_send_document._cover_patched = True
    patched_send_audio._cover_patched = True
    patched_send_cached_media._cover_patched = True

    Client.send_video = patched_send_video
    Client.send_document = patched_send_document
    Client.send_audio = patched_send_audio
    Client.send_cached_media = patched_send_cached_media
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
    _patch_client_media_send()
    log.info("Cover patches applied [enabled=%s]", COVER_ENABLED)


apply_all()

import io
import unittest
import asyncio
from pathlib import Path
from PIL import Image
from unittest.mock import MagicMock, AsyncMock, patch

import monkey_patch
from monkey_patch import (
    _extract_title,
    _already_has_thumb,
    _prepare_thumb,
    _cache_key,
    _cache_put,
    _cache_get,
    _patch_save_file,
    _patch_media_client,
)

class TestMonkeyPatch(unittest.IsolatedAsyncioTestCase):

    async def test_extract_title_document(self):
        media = MagicMock()
        media.caption = None
        media.document.file_name = "Inception.2010.1080p.WEB-DL.x264.mkv"
        media.video = None
        media.audio = None

        title, year = _extract_title(media)
        self.assertEqual(title, "Inception")
        self.assertEqual(year, 2010)

    async def test_extract_title_series(self):
        media = MagicMock()
        media.caption = None
        media.document.file_name = "Stranger.Things.S01E01.720p.HDTV.x264.mp4"
        media.video = None
        media.audio = None

        title, year = _extract_title(media)
        self.assertEqual(title, "Stranger Things")
        self.assertIsNone(year)

    async def test_already_has_thumb(self):
        media_with_thumb = MagicMock()
        media_with_thumb.video.thumbs = [MagicMock()]
        media_with_thumb.document = None
        media_with_thumb.audio = None

        self.assertTrue(_already_has_thumb(media_with_thumb))

        media_no_thumb = MagicMock()
        media_no_thumb.video.thumbs = None
        media_no_thumb.document.thumbs = None
        media_no_thumb.audio = None

        self.assertFalse(_already_has_thumb(media_no_thumb))

    async def test_prepare_thumb(self):
        img = Image.new("RGB", (100, 100), color="blue")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        raw_bytes = buf.getvalue()

        thumb_buf = _prepare_thumb(raw_bytes)
        self.assertIsNotNone(thumb_buf)
        self.assertLessEqual(thumb_buf.tell(), 200 * 1024)

        invalid_buf = _prepare_thumb(b"not an image")
        self.assertIsNone(invalid_buf)

    async def test_cache_operations(self):
        title = "test_movie"
        year = 2024
        test_data = b"a" * 600

        _cache_put(title, year, test_data)
        retrieved = _cache_get(title, year)
        self.assertEqual(retrieved, test_data)

        # Cleanup
        key_file = _cache_key(title, year)
        if key_file.exists():
            key_file.unlink()

    async def test_patches_applied(self):
        from database import ia_filterdb
        from pyrogram import Client

        self.assertTrue(getattr(ia_filterdb.save_file, "_cover_patched", False))
        self.assertTrue(getattr(Client.__init__, "_cover_patched", False))

    @patch("monkey_patch._fetch_poster", new_callable=AsyncMock)
    @patch("monkey_patch._reupload_with_cover", new_callable=AsyncMock)
    async def test_patched_save_file_attaches_cover(self, mock_reupload, mock_fetch):
        from database import ia_filterdb

        mock_fetch.return_value = b"poster_bytes_data"
        mock_reupload.return_value = "new_file_id_123"

        media = MagicMock()
        media.file_id = "test_file_id"
        media.caption = "Test Movie 2023 1080p.mkv"
        media.document = MagicMock()
        media.document.thumbs = None
        media.document.file_id = "old_file_id_000"
        media.video = None
        media.audio = None
        media._client = MagicMock()

        with patch("database.ia_filterdb.unpack_new_file_id", return_value=("fid", "fref")), \
             patch("database.ia_filterdb.Media.find_one", new_callable=AsyncMock) as mock_find_one, \
             patch("database.ia_filterdb.Media.commit", new_callable=AsyncMock) as mock_commit:
            mock_find_one.return_value = None

            with patch.object(monkey_patch, "COVER_ENABLED", True), \
                 patch.object(monkey_patch, "DB_CHANNEL_ID", -100123456789):
                res, code = await ia_filterdb.save_file(media)

        mock_fetch.assert_called_once()
        mock_reupload.assert_called_once()
        self.assertEqual(media.document.file_id, "new_file_id_123")

if __name__ == "__main__":
    unittest.main()

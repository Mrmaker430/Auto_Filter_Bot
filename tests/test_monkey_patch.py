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
    _patch_client_media_send,
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

    async def test_extract_title_string(self):
        title, year = _extract_title("Interstellar.2014.1080p.mkv")
        self.assertEqual(title, "Interstellar")
        self.assertEqual(year, 2014)

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
        from pyrogram import Client

        self.assertTrue(getattr(Client.__init__, "_cover_patched", False))
        self.assertTrue(getattr(Client.send_video, "_cover_patched", False))
        self.assertTrue(getattr(Client.send_document, "_cover_patched", False))
        self.assertTrue(getattr(Client.send_audio, "_cover_patched", False))
        self.assertTrue(getattr(Client.send_cached_media, "_cover_patched", False))

    @patch("monkey_patch._fetch_poster", new_callable=AsyncMock)
    async def test_patched_send_video_attaches_cover(self, mock_fetch):
        from pyrogram import Client

        img = Image.new("RGB", (100, 100), color="red")
        img_buf = io.BytesIO()
        img.save(img_buf, format="JPEG")
        mock_fetch.return_value = img_buf.getvalue()

        dummy_orig = AsyncMock()
        with patch.object(Client, "send_video", dummy_orig):
            if hasattr(dummy_orig, "_cover_patched"):
                delattr(dummy_orig, "_cover_patched")
            _patch_client_media_send()

            client = MagicMock(spec=Client)
            with patch.object(monkey_patch, "COVER_ENABLED", True):
                await Client.send_video(client, 12345, "Inception.2010.1080p.mkv")

        mock_fetch.assert_called_once()
        dummy_orig.assert_called_once()
        _, kwargs = dummy_orig.call_args
        self.assertIn("thumb", kwargs)
        self.assertIsNotNone(kwargs["thumb"])

    @patch("monkey_patch._fetch_poster", new_callable=AsyncMock)
    @patch("database.ia_filterdb.get_file_details", new_callable=AsyncMock)
    async def test_patched_send_cached_media_attaches_cover(self, mock_get_file_details, mock_fetch):
        from pyrogram import Client

        img = Image.new("RGB", (100, 100), color="red")
        img_buf = io.BytesIO()
        img.save(img_buf, format="JPEG")
        mock_fetch.return_value = img_buf.getvalue()

        file_doc = MagicMock()
        file_doc.file_name = "Avatar.2009.1080p.mkv"
        file_doc.file_type = "video"
        file_doc.caption = "Avatar (2009)"
        mock_get_file_details.return_value = [file_doc]

        dummy_send_video = AsyncMock()
        dummy_send_cached_media = AsyncMock()

        with patch.object(Client, "send_video", dummy_send_video), \
             patch.object(Client, "send_cached_media", dummy_send_cached_media):
            if hasattr(dummy_send_video, "_cover_patched"):
                delattr(dummy_send_video, "_cover_patched")
            _patch_client_media_send()

            client = MagicMock(spec=Client)
            with patch.object(monkey_patch, "COVER_ENABLED", True):
                await Client.send_cached_media(client, 12345, "cached_file_id_999")

        mock_get_file_details.assert_called_once_with("cached_file_id_999")
        mock_fetch.assert_called_once()
        dummy_send_video.assert_called_once()
        _, kwargs = dummy_send_video.call_args
        self.assertIn("thumb", kwargs)
        self.assertIsNotNone(kwargs["thumb"])

if __name__ == "__main__":
    unittest.main()

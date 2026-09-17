import asyncio
from unittest.mock import AsyncMock, patch
from database.ia_filterdb import save_file


def test_save_file_with_str_caption():
    async def run():
        class DummyMedia:
            file_id = "BAACAgUAAxkBAAE12345"
            file_unique_id = "uniq123"
            file_name = "Sample.Movie.2024.1080p.mkv"
            file_size = 1024000
            file_type = "video"
            mime_type = "video/x-matroska"
            caption = "Sample Movie 2024 1080p Web-DL"

        media = DummyMedia()

        with patch("database.ia_filterdb.unpack_new_file_id", return_value=("enc_file_id", "enc_file_ref")), \
             patch("database.ia_filterdb.Media.find_one", new_callable=AsyncMock, return_value=None), \
             patch("database.ia_filterdb.Media.commit", new_callable=AsyncMock, return_value=None):
            ok, status = await save_file(media)
            assert ok is True
            assert status == 1

    asyncio.run(run())


def test_save_file_with_none_filename():
    async def run():
        class DummyMediaNoName:
            file_id = "BAACAgUAAxkBAAE67890"
            file_unique_id = "uniq67890"
            file_name = None
            file_size = 2048000
            file_type = "video"
            mime_type = "video/mp4"
            caption = "Awesome Video Title 720p"

        media = DummyMediaNoName()

        with patch("database.ia_filterdb.unpack_new_file_id", return_value=("enc_file_id_2", "enc_file_ref_2")), \
             patch("database.ia_filterdb.Media.find_one", new_callable=AsyncMock, return_value=None), \
             patch("database.ia_filterdb.Media.commit", new_callable=AsyncMock, return_value=None):
            ok, status = await save_file(media)
            assert ok is True
            assert status == 1

    asyncio.run(run())

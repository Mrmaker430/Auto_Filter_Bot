import os
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from utils import get_or_generate_cover

class TestMediaCover(unittest.TestCase):

    def test_get_or_generate_cover_fallback(self):
        async def run_test():
            # Test that get_or_generate_cover returns fallback_cover when details/updates missing
            with patch("database.users_chats_db.db.get_movie_update", new_callable=AsyncMock) as mock_get_update, \
                 patch("utils.get_movie_detailsx", new_callable=AsyncMock) as mock_get_details:
                mock_get_update.return_value = None
                mock_get_details.return_value = {"error": True}
                cover_res = await get_or_generate_cover("NonExistentMovie123.mkv", fallback_cover="http://example.com/fallback.jpg")
                self.assertEqual(cover_res, "http://example.com/fallback.jpg")

        asyncio.run(run_test())

    def test_get_or_generate_cover_generation(self):
        async def run_test():
            movie_doc = {
                "_id": "Test Movie 2026",
                "year": "2026",
                "rating": "8.5",
                "genres": "ACTION, THRILLER",
                "plot": "An exciting test movie plot summary for unit testing.",
                "poster_url": "https://image.tmdb.org/t/p/original/test.jpg",
                "backdrop_url": "https://image.tmdb.org/t/p/original/test_bg.jpg"
            }
            with patch("database.users_chats_db.db.get_movie_update", new_callable=AsyncMock) as mock_get_update:
                mock_get_update.return_value = movie_doc
                cover_path = await get_or_generate_cover("Test.Movie.2026.1080p.mkv")
                self.assertIsNotNone(cover_path)
                self.assertTrue(os.path.exists(cover_path))
                if os.path.exists(cover_path):
                    os.remove(cover_path)

        asyncio.run(run_test())

if __name__ == "__main__":
    unittest.main()

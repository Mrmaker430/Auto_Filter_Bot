import os
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock
from database.users_chats_db import Database
from plugins.Dreamxfutures.poster_generator import generate_movie_poster

class TestMovieUpdateAndPoster(unittest.TestCase):

    def test_database_get_movie_update_structure(self):
        # Create a mock database client and test get_movie_update logic
        db_inst = Database("mongodb://localhost:27017", "testdb")
        self.assertTrue(hasattr(db_inst, "get_movie_update"))

    def test_poster_generator(self):
        async def run_test():
            movie_doc = {
                "_id": "Epic [First Semester]",
                "year": "2026",
                "rating": "6.0",
                "genres": "ROMANCE, DRAMA",
                "plot": "Far from home, Aditya wrestles with family expectations, cultural differences and loneliness while studying in London - until he meets the lively Kadali.",
                "poster_url": "https://image.tmdb.org/t/p/original/9db21G7S0k4iS3R3F3o04.jpg",
                "backdrop_url": "https://image.tmdb.org/t/p/original/9db21G7S0k4iS3R3F3o04.jpg"
            }
            poster_buf = await generate_movie_poster(movie_doc)
            self.assertIsNotNone(poster_buf)
            data = poster_buf.getvalue()
            self.assertGreater(len(data), 0)
            with open("/tmp/generated_test_poster.jpg", "wb") as f:
                f.write(data)
            print("Successfully generated test poster: /tmp/generated_test_poster.jpg")

        asyncio.run(run_test())

if __name__ == "__main__":
    unittest.main()

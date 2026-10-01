import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock
from plugins.Dreamxfutures.Imdbposter import (
    TMDB_DETAILS_CACHE,
    IMDB_DETAILS_CACHE,
    _get_from_cache,
    _set_in_cache,
    get_movie_detailsx,
)
from utils import (
    POSTER_RESULT_CACHE,
    _get_cached_poster,
    _set_cached_poster,
    get_posterx,
)

def test_imdbposter_cache_set_and_get():
    cache = {}
    key = "test_movie_2024"
    data = {"title": "Test Movie", "year": 2024}

    _set_in_cache(cache, key, data)
    retrieved = _get_from_cache(cache, key)
    assert retrieved == data
    assert retrieved["title"] == "Test Movie"

def test_utils_poster_cache_set_and_get():
    cache_key = "get_posterx_test_query"
    data = {"title": "Cached Poster", "poster": "http://example.com/poster.jpg"}

    _set_cached_poster(cache_key, data)
    retrieved = _get_cached_poster(cache_key)
    assert retrieved == data
    assert retrieved["title"] == "Cached Poster"

@pytest.mark.asyncio
async def test_get_movie_detailsx_cache():
    query = "Unique Caching Test Title 2024"
    mock_data = {
        "title": "Unique Caching Test Title",
        "year": 2024,
        "rating": 8.5,
        "poster_url": "http://image.tmdb.org/poster.jpg",
        "backdrop_url": "http://image.tmdb.org/backdrop.jpg"
    }

    with patch("plugins.Dreamxfutures.Imdbposter._fetch_tmdb_data", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = {
            "title": "Unique Caching Test Title",
            "year": "2024",
            "rating": 8.5,
            "poster_path": "/poster.jpg",
            "images": {}
        }

        # First call - should call mock_fetch
        res1 = await get_movie_detailsx(query)
        assert mock_fetch.call_count == 1
        assert res1["title"] == "Unique Caching Test Title"

        # Second call - should return cached result without calling mock_fetch again
        res2 = await get_movie_detailsx(query)
        assert mock_fetch.call_count == 1
        assert res2["title"] == "Unique Caching Test Title"

@pytest.mark.asyncio
async def test_get_posterx_cache():
    query = "Unique Poster Cache Query 2024"
    with patch("utils._get_posterx_uncached", new_callable=AsyncMock) as mock_uncached:
        mock_uncached.return_value = {
            "title": "Unique Poster Title",
            "poster": "http://example.com/p.jpg"
        }

        # First call
        res1 = await get_posterx(query)
        assert mock_uncached.call_count == 1
        assert res1["title"] == "Unique Poster Title"

        # Second call should use POSTER_RESULT_CACHE
        res2 = await get_posterx(query)
        assert mock_uncached.call_count == 1
        assert res2["title"] == "Unique Poster Title"

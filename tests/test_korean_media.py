import pytest
from unittest.mock import patch, AsyncMock
from plugins.Dreamxfutures.Imdbposter import (
    is_korean_media,
    search_korean_media,
    get_popular_korean_media,
    _search_media_id
)

def test_is_korean_media():
    tv_kr = {"origin_country": ["KR"], "original_language": "ko"}
    tv_non_kr = {"origin_country": ["US"], "original_language": "en"}
    movie_kr = {"origin_country": [], "original_language": "ko"}
    movie_non_kr = {"origin_country": ["US"], "original_language": "en"}

    assert is_korean_media(tv_kr, "tv") is True
    assert is_korean_media(tv_non_kr, "tv") is False
    assert is_korean_media(movie_kr, "movie") is True
    assert is_korean_media(movie_non_kr, "movie") is False

@pytest.mark.asyncio
async def test_search_korean_media():
    mock_response = {
        "results": [
            {"id": 1, "name": "A Korean Odyssey", "origin_country": ["KR"], "original_language": "ko"},
            {"id": 2, "name": "Non Korean Show", "origin_country": ["US"], "original_language": "en"}
        ]
    }
    with patch("plugins.Dreamxfutures.Imdbposter._tmdb_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response
        results = await search_korean_media("Korean Odyssey", media_type="tv")
        assert len(results) == 1
        assert results[0]["id"] == 1
        assert results[0]["name"] == "A Korean Odyssey"

@pytest.mark.asyncio
async def test_get_popular_korean_media():
    mock_response = {
        "results": [
            {"id": 10, "name": "Squid Game", "origin_country": ["KR"], "original_language": "ko"},
            {"id": 11, "name": "Crash Landing on You", "origin_country": ["KR"], "original_language": "ko"}
        ]
    }
    with patch("plugins.Dreamxfutures.Imdbposter._tmdb_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response
        results = await get_popular_korean_media(media_type="tv", limit=2)
        assert len(results) == 2
        assert results[0]["name"] == "Squid Game"

@pytest.mark.asyncio
async def test_search_media_id_korean_query():
    mock_search = {
        "results": [
            {
                "id": 100,
                "media_type": "tv",
                "name": "A Korean Odyssey",
                "first_air_date": "2017-12-23",
                "origin_country": ["KR"],
                "original_language": "ko",
                "popularity": 85.0
            }
        ]
    }
    mock_details = {
        "id": 100,
        "name": "A Korean Odyssey",
        "episode_run_time": [70]
    }

    async def mock_tmdb_get(endpoint, params=None, api_key=None):
        if "search" in endpoint:
            return mock_search
        return mock_details

    with patch("plugins.Dreamxfutures.Imdbposter._tmdb_get", side_effect=mock_tmdb_get):
        mtype, mid = await _search_media_id("A Korean Odyssey", category="series")
        assert mtype == "tv"
        assert mid == 100

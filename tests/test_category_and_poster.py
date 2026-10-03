import pytest
import re
from unittest.mock import AsyncMock, patch
from plugins.Dreamxfutures.Imdbposter import _search_media_id, get_movie_detailsx


@pytest.mark.asyncio
async def test_search_media_id_exact_title_match_over_extra_words():
    # Mock TMDB multi search returning both 'Homecoming' and 'All American: Homecoming'
    mock_multi_results = {
        'results': [
            {
                'id': 101,
                'title': 'All American: Homecoming',
                'media_type': 'tv',
                'first_air_date': '2022-02-21',
                'popularity': 85.0
            },
            {
                'id': 102,
                'title': 'Homecoming',
                'media_type': 'tv',
                'first_air_date': '2018-11-02',
                'popularity': 60.0
            }
        ]
    }

    async def mock_tmdb_get(path, params=None, api_key=None):
        if 'search/' in path:
            return mock_multi_results
        return {}

    with patch("plugins.Dreamxfutures.Imdbposter._tmdb_get", side_effect=mock_tmdb_get):
        # Querying "homecoming 2022" should select "Homecoming" (id=102) rather than "All American: Homecoming" (id=101)
        mtype, mid = await _search_media_id("homecoming 2022")
        assert mid == 102


@pytest.mark.asyncio
async def test_search_media_id_category_filtering():
    mock_results = {
        'results': [
            {
                'id': 201,
                'title': 'Avatar',
                'media_type': 'movie',
                'release_date': '2009-12-18',
                'popularity': 120.0
            },
            {
                'id': 202,
                'name': 'Avatar: The Last Airbender',
                'media_type': 'tv',
                'first_air_date': '2005-02-21',
                'popularity': 90.0
            }
        ]
    }

    async def mock_tmdb_get(path, params=None, api_key=None):
        return mock_results

    async def mock_fetch_details(mtype, mid, api_key=None):
        return {'runtime': 162, 'video': False}

    with patch("plugins.Dreamxfutures.Imdbposter._tmdb_get", side_effect=mock_tmdb_get), \
         patch("plugins.Dreamxfutures.Imdbposter._fetch_media_details", side_effect=mock_fetch_details):

        mtype_movie, mid_movie = await _search_media_id("avatar", category="movie")
        assert mtype_movie == "movie"
        assert mid_movie == 201

        mtype_tv, mid_tv = await _search_media_id("avatar", category="series")
        assert mtype_tv == "tv"
        assert mid_tv == 202


@pytest.mark.asyncio
async def test_get_cap_blockquote_formatting():
    from utils import get_cap, clean_filename, get_size

    class DummyFile:
        def __init__(self, file_id, file_name, file_size):
            self.file_id = file_id
            self.file_name = file_name
            self.file_size = file_size

    class DummyUser:
        mention = "@testuser"
        id = 12345

    class DummyChat:
        id = -10012345
        title = "Test Group"

    class DummyMessage:
        chat = DummyChat()

    class DummyQuery:
        from_user = DummyUser()
        message = DummyMessage()

    files = [
        DummyFile("fid1", "Avatar.2009.1080p.mkv", 1073741824),
        DummyFile("fid2", "Avatar.2009.720p.mkv", 536870912)
    ]
    settings = {"imdb": False, "button": False}

    cap = await get_cap(settings, "0.50", files, DummyQuery(), 2, "Avatar")
    assert "<blockquote expandable>" not in cap
    assert "<b><u>Your Requested Files Are Here</u></b>" in cap
    assert "</blockquote>" not in cap
    assert "[1.00 GB] Avatar.2009.1080p.mkv" in cap

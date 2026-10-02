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
async def test_category_file_filtering():
    class DummyFile:
        def __init__(self, file_id, file_name, file_size=1000):
            self.file_id = file_id
            self.file_name = file_name
            self.file_size = file_size

    movie_file = DummyFile("1", "Homecoming.2022.1080p.WEBRip.mkv")
    series_file = DummyFile("2", "All.American.Homecoming.S01E01.1080p.mkv")

    all_files = [movie_file, series_file]

    series_pattern = re.compile(r"(?:s\d{1,2}|season\s*\d+|season\d+|e\d{1,2}|episode\s*\d+)", re.IGNORECASE)

    movie_filtered = [f for f in all_files if not series_pattern.search(f.file_name)]
    series_filtered = [f for f in all_files if series_pattern.search(f.file_name)]

    assert len(movie_filtered) == 1
    assert movie_filtered[0].file_id == "1"

    assert len(series_filtered) == 1
    assert series_filtered[0].file_id == "2"

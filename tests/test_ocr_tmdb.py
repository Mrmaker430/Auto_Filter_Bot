import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from plugins.Dreamxfutures.Imdbposter import (
    extract_text_from_poster,
    is_bangladeshi_media,
    _process_images,
    get_movie_detailsx,
    _search_media_id,
    _fetch_media_details,
)

def test_extract_text_from_poster_empty():
    assert extract_text_from_poster(None) == ""
    assert extract_text_from_poster("") == ""

def test_extract_text_from_poster_with_mock_bangla_ocr(monkeypatch):
    mock_ocr = MagicMock()
    mock_ocr.predict.return_value = "অপরাজিত"
    monkeypatch.setattr("plugins.Dreamxfutures.Imdbposter.get_bangla_ocr", lambda: mock_ocr)

    text = extract_text_from_poster("poster_image_path.jpg")
    assert text == "অপরাজিত"
    mock_ocr.predict.assert_called_once_with("poster_image_path.jpg")

def test_extract_text_from_poster_fallback_indic_ocr(monkeypatch):
    mock_bangla = MagicMock()
    mock_bangla.predict.side_effect = Exception("Bangla OCR failed")

    mock_indic = MagicMock()
    mock_indic.predict.return_value = "Apur Sansar"

    monkeypatch.setattr("plugins.Dreamxfutures.Imdbposter.get_bangla_ocr", lambda: mock_bangla)
    monkeypatch.setattr("plugins.Dreamxfutures.Imdbposter.get_indic_ocr", lambda: mock_indic)

    text = extract_text_from_poster("mixed_script_poster.png")
    assert text == "Apur Sansar"

@pytest.mark.asyncio
async def test_get_movie_detailsx_calls_ocr_when_image_provided(monkeypatch):
    ocr_called = False

    def mock_extract(img):
        nonlocal ocr_called
        ocr_called = True
        return "Apu"

    async def mock_fetch(q, api_key=None):
        assert "Apu" in q
        return {
            'title': 'Apu Trilogy',
            'year': '1955',
            'rating': 8.5,
            'poster_url': 'https://image.tmdb.org/t/p/original/apu.jpg'
        }

    monkeypatch.setattr("plugins.Dreamxfutures.Imdbposter.extract_text_from_poster", mock_extract)
    monkeypatch.setattr("plugins.Dreamxfutures.Imdbposter._fetch_tmdb_data", mock_fetch)

    res = await get_movie_detailsx("1955.mkv", image_input="http://example.com/poster.jpg")
    assert ocr_called is True
    assert res is not None
    assert res['title'] == 'Apu Trilogy'

def test_is_bangladeshi_media():
    # Bangladeshi samples
    bd_movie_1 = {'origin_country': ['BD']}
    bd_movie_2 = {'production_countries': [{'iso_3166_1': 'BD', 'name': 'Bangladesh'}]}
    bd_movie_3 = {'countries': 'Bangladesh'}
    bd_movie_4 = {'countries': ['BD']}

    assert is_bangladeshi_media(bd_movie_1) is True
    assert is_bangladeshi_media(bd_movie_2) is True
    assert is_bangladeshi_media(bd_movie_3) is True
    assert is_bangladeshi_media(bd_movie_4) is True

    # Indian / Non-Bangladeshi samples
    in_movie_1 = {'origin_country': ['IN']}
    in_movie_2 = {'production_countries': [{'iso_3166_1': 'IN', 'name': 'India'}]}
    in_movie_3 = {'countries': 'India'}
    us_movie = {'production_countries': [{'iso_3166_1': 'US', 'name': 'United States'}]}

    assert is_bangladeshi_media(in_movie_1) is False
    assert is_bangladeshi_media(in_movie_2) is False
    assert is_bangladeshi_media(in_movie_3) is False
    assert is_bangladeshi_media(us_movie) is False

def test_process_images_bn_null_en_preference():
    images_data = {
        'posters': [
            {'file_path': '/en_poster.jpg', 'iso_639_1': 'en'},
            {'file_path': '/bn_poster.jpg', 'iso_639_1': 'bn'},
            {'file_path': '/textless_poster.jpg', 'iso_639_1': None},
        ],
        'backdrops': [
            {'file_path': '/en_backdrop.jpg', 'iso_639_1': 'en'},
            {'file_path': '/bn_backdrop.jpg', 'iso_639_1': 'bn'},
        ],
        'logos': [
            {'file_path': '/bn_logo.png', 'iso_639_1': 'bn'},
        ]
    }

    processed = _process_images(images_data)
    assert 'bn' in processed['posters']
    assert 'en' in processed['posters']
    assert 'null' in processed['posters']
    assert processed['posters']['bn'][0] == 'https://image.tmdb.org/t/p/original/bn_poster.jpg'
    # Check no duplicate entry in 'en'
    assert len(processed['posters']['en']) == 1
    assert processed['posters']['en'][0] == 'https://image.tmdb.org/t/p/original/en_poster.jpg'

@pytest.mark.asyncio
async def test_get_movie_detailsx_bengali_tollywood_preference(monkeypatch):
    """
    Test Tollywood (Indian Bengali) movie details retrieval:
    - Bengali poster is prioritized over English
    - Bangladeshi movie candidates are filtered out
    """
    async def mock_fetch_tmdb_data(query, api_key=None):
        return {
            'title': 'Chokher Bali',
            'year': '2003',
            'rating': 7.6,
            'votes': 2500,
            'plot': 'A passion play set in 20th century Bengal...',
            'genres': 'Drama, Romance',
            'countries': 'India',
            'production_countries': [{'iso_3166_1': 'IN', 'name': 'India'}],
            'poster_url': None,
            'url': 'https://www.themoviedb.org/movie/42555',
            'images': {
                'original_language': 'bn',
                'posters': {
                    'en': ['https://image.tmdb.org/t/p/original/chokher_bali_en.jpg'],
                    'bn': ['https://image.tmdb.org/t/p/original/chokher_bali_bn.jpg'],
                },
                'backdrops': {
                    'bn': ['https://image.tmdb.org/t/p/original/chokher_bali_bg.jpg']
                },
                'logos': {}
            }
        }

    monkeypatch.setattr('plugins.Dreamxfutures.Imdbposter._fetch_tmdb_data', mock_fetch_tmdb_data)

    res = await get_movie_detailsx('Chokher Bali 2003')
    assert res is not None
    assert res['title'] == 'Chokher Bali'
    assert res['year'] == 2003
    # Verify Bengali poster is preferred over English
    assert res['poster_url'] == 'https://image.tmdb.org/t/p/original/chokher_bali_bn.jpg'

@pytest.mark.asyncio
async def test_filter_out_bangladeshi_movie_candidate(monkeypatch):
    """
    Verify Bangladeshi candidate movies are skipped during TMDB lookup.
    """
    async def mock_tmdb_get(endpoint, params=None, api_key=None):
        if 'search' in endpoint:
            return {
                'results': [
                    {'id': 101, 'title': 'Bangladeshi Film', 'media_type': 'movie', 'release_date': '2020-01-01'},
                    {'id': 102, 'title': 'Tollywood Film', 'media_type': 'movie', 'release_date': '2020-01-01'}
                ]
            }

        if endpoint == 'movie/101':
            return {
                'id': 101,
                'title': 'Bangladeshi Film',
                'runtime': 120,
                'production_countries': [{'iso_3166_1': 'BD', 'name': 'Bangladesh'}],
                'origin_country': ['BD']
            }
        elif endpoint == 'movie/102':
            return {
                'id': 102,
                'title': 'Tollywood Film',
                'runtime': 130,
                'production_countries': [{'iso_3166_1': 'IN', 'name': 'India'}],
                'origin_country': ['IN']
            }
        return {}

    monkeypatch.setattr('plugins.Dreamxfutures.Imdbposter._tmdb_get', mock_tmdb_get)

    mtype, mid = await _search_media_id('Tollywood Film')
    assert mtype == 'movie'
    # Must select ID 102 (Tollywood India) and skip ID 101 (Bangladesh)
    assert mid == 102

@pytest.mark.asyncio
async def test_non_bengali_movie_remains_functional(monkeypatch):
    """
    Ensure non-Bengali movies (e.g. Oppenheimer, Interstellar, Jawan) still work perfectly.
    """
    async def mock_fetch_tmdb_data(query, api_key=None):
        return {
            'title': 'Oppenheimer',
            'year': '2023',
            'rating': 8.9,
            'votes': 650000,
            'plot': 'The story of American scientist J. Robert Oppenheimer...',
            'genres': 'Biography, Drama, History',
            'countries': 'United States',
            'production_countries': [{'iso_3166_1': 'US', 'name': 'United States'}],
            'poster_url': 'https://image.tmdb.org/t/p/original/oppenheimer.jpg',
            'url': 'https://www.themoviedb.org/movie/872585',
            'images': {
                'original_language': 'en',
                'posters': {'en': ['https://image.tmdb.org/t/p/original/oppenheimer.jpg']},
                'backdrops': {'en': ['https://image.tmdb.org/t/p/original/oppenheimer_bg.jpg']},
                'logos': {'en': ['https://image.tmdb.org/t/p/original/oppenheimer_logo.png']}
            }
        }

    monkeypatch.setattr('plugins.Dreamxfutures.Imdbposter._fetch_tmdb_data', mock_fetch_tmdb_data)

    res = await get_movie_detailsx('Oppenheimer 2023')
    assert res is not None
    assert res['title'] == 'Oppenheimer'
    assert res['year'] == 2023
    assert res['poster_url'] == 'https://image.tmdb.org/t/p/original/oppenheimer.jpg'

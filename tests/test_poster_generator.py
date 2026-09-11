import pytest
import asyncio
from plugins.Dreamxfutures.poster_generator import _format_runtime, generate_movie_poster

def test_format_runtime():
    assert _format_runtime('143 min') == '2H 23M'
    assert _format_runtime('90') == '1H 30M'
    assert _format_runtime('45 min') == '45M'
    assert _format_runtime('2H 15M') == '2H 15M'
    assert _format_runtime(None) == ''

def test_generate_movie_poster_mock():
    details = {
        'title': 'Test Movie',
        'localized_title': 'TEST LOCALIZED',
        'rating': 7.5,
        'year': 2024,
        'genres': ['Action', 'Sci-Fi'],
        'plot': 'Test storyline plot overview text.',
        'runtime': '120 min',
    }
    buf = asyncio.run(generate_movie_poster(details, '@cholochhitro'))
    assert buf is not None
    assert len(buf.getvalue()) > 0

def test_get_or_generate_cover(monkeypatch):
    from io import BytesIO
    from utils import get_or_generate_cover, POSTER_CACHE

    POSTER_CACHE.clear()

    async def mock_get_movie_detailsx(query):
        return {
            'title': 'Inception',
            'rating': 8.8,
            'year': 2010,
            'genres': 'Action, Sci-Fi',
            'plot': 'A thief who steals corporate secrets...',
            'poster_url': 'http://example.com/poster.jpg',
            'backdrop_url': 'http://example.com/backdrop.jpg',
        }

    async def mock_generate_movie_poster(details):
        b = BytesIO(b"fake_poster_image_bytes")
        b.seek(0)
        return b

    monkeypatch.setattr('plugins.Dreamxfutures.Imdbposter.get_movie_detailsx', mock_get_movie_detailsx)
    monkeypatch.setattr('plugins.Dreamxfutures.poster_generator.generate_movie_poster', mock_generate_movie_poster)

    # First call generates and caches poster
    res1 = asyncio.run(get_or_generate_cover('Inception.2010.1080p.mkv', 'fallback_cover_id'))
    assert isinstance(res1, BytesIO)
    assert res1.getvalue() == b"fake_poster_image_bytes"

    # Second call returns cached poster
    res2 = asyncio.run(get_or_generate_cover('Inception.2010.720p.mkv', 'fallback_cover_id'))
    assert isinstance(res2, BytesIO)
    assert res2.getvalue() == b"fake_poster_image_bytes"

def test_get_or_generate_cover_fallback(monkeypatch):
    from utils import get_or_generate_cover, POSTER_CACHE

    POSTER_CACHE.clear()

    async def mock_get_movie_detailsx(query):
        return None

    async def mock_get_movie_details(query):
        return None

    async def mock_generate_movie_poster(details):
        return None

    monkeypatch.setattr('plugins.Dreamxfutures.Imdbposter.get_movie_detailsx', mock_get_movie_detailsx)
    monkeypatch.setattr('plugins.Dreamxfutures.Imdbposter.get_movie_details', mock_get_movie_details)
    monkeypatch.setattr('plugins.Dreamxfutures.poster_generator.generate_movie_poster', mock_generate_movie_poster)

    res = asyncio.run(get_or_generate_cover('UnknownMovie.2024.mkv', 'fallback_cover_id'))
    assert res == 'fallback_cover_id'

def test_generate_movie_poster_with_logo():
    details = {
        'title': 'Test Movie Logo',
        'rating': 8.0,
        'year': 2025,
        'genres': ['Horror'],
        'plot': 'Test plot text.',
        'runtime': '100 min',
        'logo_url': None,
    }
    buf = asyncio.run(generate_movie_poster(details, '@cholochhitro'))
    assert buf is not None
    assert len(buf.getvalue()) > 0

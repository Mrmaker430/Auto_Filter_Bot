import pytest
import asyncio
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock
from utils import get_or_generate_cover, POSTER_CACHE
from plugins.monkey_patch import _resolve_video_cover
from plugins.Dreamxfutures.poster_generator import generate_movie_poster

def test_generate_movie_poster_buffer_name():
    details = {
        'title': 'Test Cover Movie',
        'rating': 8.5,
        'year': 2025,
        'genres': ['Action', 'Thriller'],
        'plot': 'A test movie plot for poster generation.',
    }
    buf = asyncio.run(generate_movie_poster(details, '@cholochhitro'))
    assert buf is not None
    assert getattr(buf, 'name', None) == 'poster.jpg'
    assert len(buf.getvalue()) > 0

def test_get_or_generate_cover_without_poster_url(monkeypatch):
    POSTER_CACHE.clear()

    async def mock_get_movie_detailsx(query):
        return {
            'title': 'No Poster Movie',
            'rating': 'N/A',
            'year': 2025,
            'genres': 'Drama',
            'plot': 'A movie with no poster or backdrop URL.',
            'poster_url': None,
            'backdrop_url': None,
        }

    monkeypatch.setattr('plugins.Dreamxfutures.Imdbposter.get_movie_detailsx', mock_get_movie_detailsx)

    res = asyncio.run(get_or_generate_cover('NoPosterMovie.2025.mkv', 'old_cover_id'))
    assert isinstance(res, BytesIO)
    assert getattr(res, 'name', None) == 'cover.jpg'
    assert len(res.getvalue()) > 0

def test_get_or_generate_cover_caching(monkeypatch):
    POSTER_CACHE.clear()

    async def mock_get_movie_detailsx(query):
        return {
            'title': 'Cached Movie',
            'rating': 9.0,
            'year': 2023,
        }

    monkeypatch.setattr('plugins.Dreamxfutures.Imdbposter.get_movie_detailsx', mock_get_movie_detailsx)

    res1 = asyncio.run(get_or_generate_cover('CachedMovie.2023.mkv', None))
    assert isinstance(res1, BytesIO)
    assert getattr(res1, 'name', None) == 'cover.jpg'

    # Verify cached bytes are retrieved
    assert len(POSTER_CACHE) == 1
    res2 = asyncio.run(get_or_generate_cover('CachedMovie.2023.mkv', None))
    assert isinstance(res2, BytesIO)
    assert getattr(res2, 'name', None) == 'cover.jpg'

def test_resolve_video_cover_sets_name():
    client = MagicMock()

    async def run_test():
        buf = BytesIO(b"fake_image_bytes")
        assert getattr(buf, 'name', None) is None

        # Mock UploadMedia invocation to return photo object
        uploaded_mock = MagicMock()
        uploaded_mock.photo.id = 12345
        uploaded_mock.photo.access_hash = 67890
        uploaded_mock.photo.file_reference = b"ref"

        client.invoke = AsyncMock(return_value=uploaded_mock)
        client.save_file = AsyncMock(return_value="file_id_mock")

        res = await _resolve_video_cover(client, "peer", buf)
        assert buf.name == "cover.jpg"
        assert res is not None
        assert res.id == 12345

    asyncio.run(run_test())

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

def test_generate_movie_poster_4k_dimensions():
    from PIL import Image

    details = {
        'title': '4K Dimensions Test Movie',
        'rating': 8.8,
        'year': 2025,
        'genres': ['Action', 'Sci-Fi'],
        'plot': 'Testing that generated image output is exactly 4K 3840x2160 pixels resolution.',
        'runtime': '140 min',
    }
    buf = asyncio.run(generate_movie_poster(details, '@cholochhitro'))
    assert buf is not None
    img = Image.open(buf)
    assert img.size == (3840, 2160)

def test_get_movie_detailsx_tmdb(monkeypatch):
    from plugins.Dreamxfutures.Imdbposter import get_movie_detailsx

    async def mock_fetch_tmdb_data(query, api_key=None):
        return {
            'title': 'Avatar',
            'year': '2009',
            'rating': 7.9,
            'votes': 12000,
            'plot': 'A paraplegic Marine dispatched to the moon Pandora...',
            'genres': 'Action, Adventure, Fantasy',
            'poster_url': 'https://image.tmdb.org/t/p/original/tmdb_poster.jpg',
            'url': 'https://www.themoviedb.org/movie/19995',
            'images': {
                'backdrops': {'en': ['https://image.tmdb.org/t/p/original/tmdb_backdrop.jpg']},
                'logos': {'en': ['https://image.tmdb.org/t/p/original/tmdb_logo.png']}
            }
        }

    monkeypatch.setattr('plugins.Dreamxfutures.Imdbposter._fetch_tmdb_data', mock_fetch_tmdb_data)

    res = asyncio.run(get_movie_detailsx('Avatar 2009'))
    assert res is not None
    assert res['title'] == 'Avatar'
    assert res['year'] == 2009
    assert res['poster_url'] == 'https://image.tmdb.org/t/p/original/tmdb_poster.jpg'
    assert res['backdrop_url'] == 'https://image.tmdb.org/t/p/original/tmdb_backdrop.jpg'
    assert res['logo_url'] == 'https://image.tmdb.org/t/p/original/tmdb_logo.png'

def test_extract_ott_list():
    from plugins.Dreamxfutures.poster_generator import _extract_ott_list

    assert _extract_ott_list({'ott_platform': 'Netflix | SonyLiv'}) == ['Netflix', 'SonyLiv']
    assert _extract_ott_list({'ott': 'Amazon Prime Video, Zee5'}) == ['Amazon Prime Video', 'Zee5']
    assert _extract_ott_list({'custom_otts': ['Hotstar', 'Apple TV+']}) == ['Hotstar', 'Apple TV+']
    assert _extract_ott_list({'ott_platform': 'N/A'}) == []

def test_generate_movie_poster_with_ott_badges():
    details = {
        'title': 'OTT Movie Test',
        'rating': 9.0,
        'year': 2025,
        'genres': ['Action', 'Thriller'],
        'plot': 'Movie with OTT badges in top right corner.',
        'runtime': '150 min',
        'ott_platform': 'Netflix | Disney+ Hotstar | Zee5',
    }
    buf = asyncio.run(generate_movie_poster(details, '@cholochhitro'))
    assert buf is not None
    assert len(buf.getvalue()) > 0

def test_generate_movie_poster_same_backdrop_and_poster():
    from PIL import Image
    from io import BytesIO

    dummy_img = Image.new("RGB", (300, 450), color=(100, 50, 200))
    thumb_buf = BytesIO()
    dummy_img.save(thumb_buf, format="JPEG")
    thumb_buf.seek(0)

    details = {
        'title': 'Same Backdrop Poster',
        'rating': 8.2,
        'year': 2025,
        'genres': ['Comedy'],
        'plot': 'Testing when backdrop_url equals poster_url.',
        'poster_url': 'http://example.com/same.jpg',
        'backdrop_url': 'http://example.com/same.jpg',
        'primary_thumb': thumb_buf,
        'ott_platform': 'Netflix',
    }
    buf = asyncio.run(generate_movie_poster(details, '@cholochhitro'))
    assert buf is not None
    assert len(buf.getvalue()) > 0

def test_dreamxbotz_clean_title():
    from database.ia_filterdb import dreamxbotz_clean_title

    assert asyncio.run(dreamxbotz_clean_title('Deadpool.1080p.WEBRip.mkv')) == 'Deadpool'
    assert asyncio.run(dreamxbotz_clean_title('Sample.Movie.2024.1080p.mkv')) == 'Sample Movie 2024'
    assert asyncio.run(dreamxbotz_clean_title('Interstellar.2014.2160p.UHD.mkv')) == 'Interstellar 2014'


def test_extract_title_and_year():
    from plugins.Dreamxfutures.Imdbposter import _extract_title_and_year
    t, y = _extract_title_and_year("Inception 2010 1080p")
    assert t == "Inception 1080p"
    assert y == 2010

    t2, y2 = _extract_title_and_year("Interstellar (2014) WEB-DL")
    assert t2 == "Interstellar WEB-DL"
    assert y2 == 2014

def test_generate_movie_poster_with_primary_thumb():
    from PIL import Image
    from io import BytesIO

    # Create a dummy image buffer for primary_thumb
    dummy_img = Image.new("RGB", (300, 450), color=(0, 100, 200))
    thumb_buf = BytesIO()
    dummy_img.save(thumb_buf, format="JPEG")
    thumb_buf.seek(0)

    details = {
        'title': 'Local Primary Thumb Movie',
        'rating': 8.5,
        'year': 2023,
        'genres': ['Drama'],
        'plot': 'Plot using primary thumbnail.',
        'primary_thumb': thumb_buf,
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
    assert getattr(res1, 'name', None) == 'cover.jpg'
    assert res1.getvalue() == b"fake_poster_image_bytes"

    # Second call returns cached poster
    res2 = asyncio.run(get_or_generate_cover('Inception.2010.720p.mkv', 'fallback_cover_id'))
    assert isinstance(res2, BytesIO)
    assert getattr(res2, 'name', None) == 'cover.jpg'
    assert res2.getvalue() == b"fake_poster_image_bytes"

def test_get_or_generate_cover_fallback(monkeypatch):
    from utils import get_or_generate_cover, POSTER_CACHE

    POSTER_CACHE.clear()

    async def mock_get_movie_detailsx(query):
        return None

    async def mock_get_movie_details(query):
        return None

    monkeypatch.setattr('plugins.Dreamxfutures.Imdbposter.get_movie_detailsx', mock_get_movie_detailsx)
    monkeypatch.setattr('plugins.Dreamxfutures.Imdbposter.get_movie_details', mock_get_movie_details)

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

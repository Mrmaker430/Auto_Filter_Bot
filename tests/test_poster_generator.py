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
    buf = asyncio.run(generate_movie_poster(details, '@testchannel'))
    assert buf is not None
    assert len(buf.getvalue()) > 0

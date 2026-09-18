from plugins.channel import generate_movie_message

def test_generate_movie_message():
    movie_doc = {
        "_id": "Inception 2010",
        "title": "Inception",
        "genres": "Action, Sci-Fi",
        "rating": "8.8",
        "imdb_url": "https://www.imdb.com/title/tt1375666/",
        "year": "2010",
        "tag": "#MOVIE",
        "files": [
            {
                "quality": "1080p",
                "language": "English, Hindi",
                "ott_platform": "Netflix",
                "tag": "#MOVIE",
                "season": None,
                "episode": None
            }
        ]
    }

    msg = generate_movie_message(movie_doc, "Inception 2010")
    assert "<b>🔥 NEW FILE ADDED 🔥</b>" in msg
    assert "<blockquote expandable>" in msg
    assert "🏷️ <b>Title</b> : <a href=\"https://www.imdb.com/title/tt1375666/\">Inception</a>" in msg
    assert "🎭 <b>Genres</b> : Action, Sci-Fi" in msg
    assert "📡 <b>Ott</b> : Netflix" in msg
    assert "⏩ <b>Quality</b> : 1080p" in msg
    assert "☀️ <b>Languages</b> : English, Hindi" in msg
    assert "🌟 <b>Rating</b> : 8.8" in msg
    assert "</blockquote>" in msg

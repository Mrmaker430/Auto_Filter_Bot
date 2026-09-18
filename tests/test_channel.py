from plugins.channel import generate_movie_message

def test_generate_movie_message_format():
    movie_doc = {
        "_id": "Inception 2010",
        "title": "Inception",
        "genres": "Action, Sci-Fi",
        "ott_platform": "Netflix",
        "rating": "8.8",
        "imdb_url": "https://www.imdb.com/title/tt1375666/",
        "year": "2010",
        "poster_url": "https://example.com/poster.jpg",
        "files": [
            {
                "filename": "Inception.2010.1080p.mkv",
                "processed": "Inception 2010 1080p",
                "quality": "1080p",
                "language": "Hindi, English",
                "ott_platform": "Netflix",
                "tag": "#MOVIE",
                "season": None,
                "episode": None
            }
        ]
    }

    msg = generate_movie_message(movie_doc, "Inception 2010")

    # Assert title header styled centered at top
    assert "<h1>  NEW FILE ADDED  </h1>" in msg

    # Assert HTML format structure elements
    assert "<b>🎬 ᴛɪᴛʟᴇ :</b>" in msg
    assert "<b>🎭 ɢᴇɴʀᴇꜱ :</b>" in msg
    assert "<b>📺 ᴏᴛᴛ :</b>" in msg
    assert "<b>💿 Qᴜᴀʟɪᴛʏ :</b>" in msg
    assert "<b>🔊 ʟᴀɴɢᴜᴀɢᴇꜱ :</b>" in msg
    assert "<b>⭐ ʀᴀᴛɪɴɢ :</b>" in msg

    # Assert search link styled centered at bottom inside message
    assert '<a href="' in msg
    assert '🔍 ꜱᴇᴀʀᴄʜ ʜᴇʀᴇ 🔎' in msg

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
    assert "<b>🔥 𝖭𝖤𝖶 𝖥𝖨𝖫𝖤 𝖠𝖣𝖣𝖤𝖣 🔥</b>" in msg
    assert "<blockquote expandable>" in msg
    assert "🏷️ <b>𝖳𝗂𝗍𝗅𝖾</b> : <a href=\"https://www.imdb.com/title/tt1375666/\"><b>Inception</b></a>" in msg
    assert "🎭 <b>𝖦𝖾𝗇𝗋𝖾𝗌</b> : Action, Sci-Fi" in msg
    assert "📡 <b>𝖮𝗍𝗍</b> : Netflix" in msg
    assert "⏩ <b>𝖰𝗎𝖺𝗅𝗂𝗍𝗒</b> : 1080p" in msg
    assert "☀️ <b>𝖫𝖺𝗇𝗀𝗎𝖺𝗀𝖾𝗌</b> : English, Hindi" in msg
    assert "🌟 <b>𝖱𝖺𝗍𝗂𝗇𝗀</b> : 8.8" in msg
    assert "</blockquote>" in msg

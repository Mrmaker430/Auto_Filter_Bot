import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from plugins.channel import get_movie_update_buttons, REACTION_EMOJIS, movie_reaction_callback
from pyrogram import enums

def test_get_movie_update_buttons_no_reaction_panel():
    movie_doc = {
        "reactions": {
            "1001": "❤️",
            "1002": "❤️",
            "1003": "🤯",
            "1004": "😓"
        }
    }
    keyboard = get_movie_update_buttons(movie_doc, "Inception 2010")

    # 1 row of buttons (search button only, reaction panel removed)
    assert len(keyboard.inline_keyboard) == 1

    search_row = keyboard.inline_keyboard[0]
    assert len(search_row) == 1
    assert search_row[0].text == "🔍 ꜱᴇᴀʀᴄʜ ʜᴇʀᴇ 🔎"
    assert search_row[0].style == enums.ButtonStyle.SUCCESS

@pytest.mark.asyncio
async def test_movie_reaction_callback():
    query = MagicMock()
    query.data = "mreact:❤️:Inception 2010"
    query.from_user.id = 12345
    query.message.id = 999
    query.answer = AsyncMock()
    query.edit_message_reply_markup = AsyncMock()

    mock_doc = {
        "_id": "Inception 2010",
        "message_id": 999,
        "reactions": {}
    }

    mock_movie_updates = MagicMock()
    mock_movie_updates.find_one = AsyncMock(return_value=mock_doc)
    mock_movie_updates.update_one = AsyncMock()

    with patch("plugins.channel.db") as mock_db:
        mock_db.movie_updates = mock_movie_updates

        await movie_reaction_callback(MagicMock(), query)

        # Verify DB updated
        mock_movie_updates.update_one.assert_called_once_with(
            {"_id": "Inception 2010"},
            {"$set": {"reactions.12345": "❤️"}}
        )

        # Verify query answer popup text is "your thought.."
        query.answer.assert_called_once_with("your thought..", show_alert=True)
        # Verify message reply markup edit was called
        query.edit_message_reply_markup.assert_called_once()

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from plugins.channel import get_movie_update_buttons, REACTION_EMOJIS, movie_reaction_callback
from pyrogram import enums

def test_get_movie_update_buttons_counts():
    movie_doc = {
        "reactions": {
            "1001": "❤️",
            "1002": "❤️",
            "1003": "🤯",
            "1004": "😓"
        }
    }
    keyboard = get_movie_update_buttons(movie_doc, "Inception 2010")

    # 2 rows of buttons
    assert len(keyboard.inline_keyboard) == 2

    # Row 1: Reactions
    reaction_row = keyboard.inline_keyboard[0]
    assert len(reaction_row) == 4
    assert reaction_row[0].text == "❤️ 2"
    assert reaction_row[0].callback_data == "mreact:❤️:Inception 2010"
    assert reaction_row[0].style == enums.ButtonStyle.PRIMARY

    assert reaction_row[1].text == "🤮 0"
    assert reaction_row[1].style == enums.ButtonStyle.PRIMARY

    assert reaction_row[2].text == "🤯 1"
    assert reaction_row[2].style == enums.ButtonStyle.PRIMARY

    assert reaction_row[3].text == "😓 1"
    assert reaction_row[3].style == enums.ButtonStyle.PRIMARY

    # Row 2: Search button
    search_row = keyboard.inline_keyboard[1]
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

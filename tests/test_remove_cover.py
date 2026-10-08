import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from database.users_chats_db import Database
from database.ia_filterdb import remove_cover_by_query
from utils import get_or_generate_cover, clear_poster_cache, POSTER_CACHE
from plugins.commands import remove_cover_cmd

@pytest.mark.asyncio
async def test_database_disabled_cover():
    db = Database("mongodb://localhost:27017", "test_db")
    # Mock disabled_covers collection
    mock_disabled_col = MagicMock()
    mock_disabled_col.update_one = AsyncMock(return_value=True)
    mock_disabled_col.find_one = AsyncMock(return_value={"_id": "test movie", "disabled": True})
    mock_disabled_col.delete_one = AsyncMock(return_value=True)
    db.disabled_covers = mock_disabled_col

    # Test add_disabled_cover
    res_add = await db.add_disabled_cover("Test Movie")
    assert res_add is True
    assert mock_disabled_col.update_one.call_count >= 1

    # Test is_cover_disabled
    res_is = await db.is_cover_disabled("Test Movie")
    assert res_is is True

    # Test remove_disabled_cover
    res_rem = await db.remove_disabled_cover("Test Movie")
    assert res_rem is True

@pytest.mark.asyncio
async def test_remove_cover_by_query_sanitization():
    mock_res = MagicMock(modified_count=3)
    mock_update = AsyncMock(return_value=mock_res)

    with patch("motor.motor_asyncio.AsyncIOMotorCollection.update_many", mock_update):
        res = await remove_cover_by_query("Avatar.2009.1080p.mkv")
        assert res >= 3
        mock_update.assert_called()
        regex_arg = mock_update.call_args[0][0]["$or"][0]["file_name"]
        assert regex_arg is not None

@pytest.mark.asyncio
async def test_clear_poster_cache():
    POSTER_CACHE["test key"] = b"data"
    clear_poster_cache("test key")
    assert "test key" not in POSTER_CACHE

    POSTER_CACHE["test key 2"] = b"data2"
    clear_poster_cache()
    assert len(POSTER_CACHE) == 0

@pytest.mark.asyncio
async def test_get_or_generate_cover_when_disabled(monkeypatch):
    from database.users_chats_db import db

    async def mock_is_disabled(title):
        if "disabled" in title.lower():
            return True
        return False

    monkeypatch.setattr(db, 'is_cover_disabled', mock_is_disabled)

    # When cover is disabled for this file
    res = await get_or_generate_cover("Disabled.Movie.2024.1080p.mkv", "fallback_cover_id")
    assert res is None

@pytest.mark.asyncio
async def test_remove_cover_command_handler(monkeypatch):
    client = MagicMock()

    # Message with argument
    msg = MagicMock()
    msg.command = ["remove_cover", "Avatar.2009.mkv"]
    msg.text = "/remove_cover Avatar.2009.mkv"
    msg.reply_to_message = None

    sent_msg = AsyncMock()
    msg.reply_text = AsyncMock(return_value=sent_msg)

    with patch("plugins.commands.db.add_disabled_cover", new_callable=AsyncMock) as mock_add_dis, \
         patch("plugins.commands.remove_cover_by_query", new_callable=AsyncMock) as mock_rem_q, \
         patch("plugins.commands.clear_poster_cache") as mock_clear_c:

        mock_rem_q.return_value = 2

        await remove_cover_cmd(client, msg)

        mock_add_dis.assert_called()
        mock_rem_q.assert_called()
        mock_clear_c.assert_called()
        sent_msg.edit.assert_called()
        assert "Covers successfully removed" in sent_msg.edit.call_args[0][0]

@pytest.mark.asyncio
async def test_remove_cover_command_usage(monkeypatch):
    client = MagicMock()

    # Message without argument or reply
    msg = MagicMock()
    msg.command = ["remove_cover"]
    msg.text = "/remove_cover"
    msg.reply_to_message = None
    msg.reply_text = AsyncMock()

    await remove_cover_cmd(client, msg)

    msg.reply_text.assert_called()
    assert "Usage:" in msg.reply_text.call_args[0][0]

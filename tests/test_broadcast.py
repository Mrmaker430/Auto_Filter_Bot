import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from database.users_chats_db import Database
from utils import users_broadcast, groups_broadcast, temp


class DummyAsyncCursor:
    def __init__(self, data):
        self.data = data

    def __aiter__(self):
        self._iter = iter(self.data)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


def test_db_get_all_users_cursor():
    """Verify that get_all_users returns a non-awaitable cursor that can be async-iterated."""
    db = Database("mongodb://localhost:27017", "test_db")
    db.col = MagicMock()
    dummy_cursor = DummyAsyncCursor([{"id": 123, "name": "Test"}])
    db.col.find.return_value = dummy_cursor

    cursor = db.get_all_users()
    assert not asyncio.iscoroutine(cursor)

    async def iterate():
        results = [u async for u in cursor]
        return results

    res = asyncio.run(iterate())
    assert res == [{"id": 123, "name": "Test"}]


@pytest.mark.asyncio
async def test_users_broadcast_success():
    mock_msg = AsyncMock()
    mock_msg.copy.return_value = AsyncMock()

    success, result = await users_broadcast(12345, mock_msg, is_pin=False)
    assert success is True
    assert result == "Success"
    mock_msg.copy.assert_called_once_with(chat_id=12345)


@pytest.mark.asyncio
async def test_groups_broadcast_success():
    mock_msg = AsyncMock()
    mock_msg.copy.return_value = AsyncMock()

    result = await groups_broadcast(-10012345, mock_msg, is_pin=False)
    assert result == "Success"
    mock_msg.copy.assert_called_once_with(chat_id=-10012345)


@pytest.mark.asyncio
async def test_users_broadcast_handler():
    from plugins.broadcast import users_broadcast_handler

    mock_bot = AsyncMock()
    status_msg = AsyncMock()

    dummy_users = DummyAsyncCursor([{"id": 111, "name": "User 1"}, {"id": 222, "name": "User 2"}])

    mock_msg = MagicMock()
    mock_msg.command = ["broadcast"]
    mock_msg.reply_to_message = AsyncMock()
    mock_msg.reply_text = AsyncMock(return_value=status_msg)

    with patch("plugins.broadcast.db") as mock_db, patch("plugins.broadcast.users_broadcast") as mock_ub:
        mock_db.get_all_users.return_value = dummy_users
        mock_db.total_users_count = AsyncMock(return_value=2)
        mock_ub.return_value = (True, "Success")

        await users_broadcast_handler(mock_bot, mock_msg)

        assert mock_ub.call_count == 2
        status_msg.edit.assert_called()


@pytest.mark.asyncio
async def test_users_broadcast_handler_fallback_and_invalid_docs():
    """Verify that users_broadcast_handler safely handles user_id, _id, and invalid documents."""
    from plugins.broadcast import users_broadcast_handler

    mock_bot = AsyncMock()
    status_msg = AsyncMock()

    dummy_users = DummyAsyncCursor([
        {"id": 111, "name": "User 1"},
        {"user_id": 222, "name": "User 2"},
        {"_id": 333, "name": "User 3"},
        {"invalid": "no id field"},
        {"id": "not_an_int"}
    ])

    mock_msg = MagicMock()
    mock_msg.command = ["broadcast"]
    mock_msg.reply_to_message = AsyncMock()
    mock_msg.reply_text = AsyncMock(return_value=status_msg)

    with patch("plugins.broadcast.db") as mock_db, patch("plugins.broadcast.users_broadcast") as mock_ub:
        mock_db.get_all_users.return_value = dummy_users
        mock_db.total_users_count = AsyncMock(return_value=5)
        mock_ub.return_value = (True, "Success")

        await users_broadcast_handler(mock_bot, mock_msg)

        # Should have called users_broadcast for 111, 222, 333 (3 valid users out of 5)
        assert mock_ub.call_count == 3
        status_msg.edit.assert_called()


@pytest.mark.asyncio
async def test_groups_broadcast_handler():
    from plugins.broadcast import groups_broadcast_handler

    mock_bot = AsyncMock()
    status_msg = AsyncMock()

    dummy_chats = DummyAsyncCursor([{"id": -1001, "title": "Grp 1"}, {"id": -1002, "title": "Grp 2"}])

    mock_msg = MagicMock()
    mock_msg.command = ["grp_broadcast"]
    mock_msg.reply_to_message = AsyncMock()
    mock_msg.reply_text = AsyncMock(return_value=status_msg)

    with patch("plugins.broadcast.db") as mock_db, patch("plugins.broadcast.groups_broadcast") as mock_gb:
        mock_db.get_all_chats.return_value = dummy_chats
        mock_db.total_chat_count = AsyncMock(return_value=2)
        mock_gb.return_value = "Success"

        await groups_broadcast_handler(mock_bot, mock_msg)

        assert mock_gb.call_count == 2
        status_msg.edit.assert_called()


@pytest.mark.asyncio
async def test_groups_broadcast_handler_fallback_and_invalid_docs():
    """Verify that groups_broadcast_handler safely handles chat_id, _id, and invalid documents."""
    from plugins.broadcast import groups_broadcast_handler

    mock_bot = AsyncMock()
    status_msg = AsyncMock()

    dummy_chats = DummyAsyncCursor([
        {"id": -1001, "title": "Grp 1"},
        {"chat_id": -1002, "title": "Grp 2"},
        {"_id": -1003, "title": "Grp 3"},
        {"corrupted": True}
    ])

    mock_msg = MagicMock()
    mock_msg.command = ["grp_broadcast"]
    mock_msg.reply_to_message = AsyncMock()
    mock_msg.reply_text = AsyncMock(return_value=status_msg)

    with patch("plugins.broadcast.db") as mock_db, patch("plugins.broadcast.groups_broadcast") as mock_gb:
        mock_db.get_all_chats.return_value = dummy_chats
        mock_db.total_chat_count = AsyncMock(return_value=4)
        mock_gb.return_value = "Success"

        await groups_broadcast_handler(mock_bot, mock_msg)

        # Should have called groups_broadcast for -1001, -1002, -1003 (3 valid groups out of 4)
        assert mock_gb.call_count == 3
        status_msg.edit.assert_called()


@pytest.mark.asyncio
async def test_broadcast_no_reply():
    from plugins.broadcast import users_broadcast_handler

    mock_bot = AsyncMock()
    mock_msg = MagicMock()
    mock_msg.command = ["broadcast"]
    mock_msg.reply_to_message = None
    mock_msg.reply = AsyncMock()

    await users_broadcast_handler(mock_bot, mock_msg)
    mock_msg.reply.assert_called_once_with("⚠️ <b>Please reply to a message to broadcast!</b>")


@pytest.mark.asyncio
async def test_broadcast_cancel_callback():
    from plugins.broadcast import broadcast_cancel

    mock_bot = AsyncMock()
    mock_query = AsyncMock()
    mock_query.data = "broadcast_cancel#users"

    temp.USERS_CANCEL = False
    await broadcast_cancel(mock_bot, mock_query)
    assert temp.USERS_CANCEL is True
    mock_query.message.edit.assert_called_once_with("🛑 <b>Cancelling Users Broadcast...</b>")

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from database.users_chats_db import Database
from utils import users_broadcast, groups_broadcast


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
    mock_client = MagicMock()
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
async def test_start_users_broadcast():
    from plugins.broadcast import start_users_broadcast

    mock_bot = AsyncMock()
    status_msg = AsyncMock()
    mock_bot.send_message.return_value = status_msg

    dummy_users = DummyAsyncCursor([{"id": 111, "name": "User 1"}, {"id": 222, "name": "User 2"}])
    mock_b_msg = AsyncMock()

    with patch("plugins.broadcast.db") as mock_db, patch("plugins.broadcast.users_broadcast") as mock_ub:
        mock_db.get_all_users.return_value = dummy_users
        mock_ub.return_value = (True, "Success")

        mock_trigger_msg = MagicMock()
        mock_trigger_msg.chat.id = 9999

        await start_users_broadcast(mock_bot, mock_trigger_msg, mock_b_msg, is_pin=False)

        assert mock_ub.call_count == 2
        status_msg.edit.assert_called()

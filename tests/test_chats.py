import asyncio
from unittest.mock import AsyncMock, MagicMock
from database.users_chats_db import Database
from plugins.p_ttishow import get_chat_link

def test_new_group_with_user_id():
    db_inst = Database("mongodb://localhost:27017", "test_db")
    grp = db_inst.new_group(-1001234567890, "Test Group", user_id=987654321)
    assert grp["id"] == -1001234567890
    assert grp["title"] == "Test Group"
    assert grp["user_id"] == 987654321
    assert grp["chat_status"]["is_disabled"] is False

def test_new_group_without_user_id():
    db_inst = Database("mongodb://localhost:27017", "test_db")
    grp = db_inst.new_group(-1001234567890, "Test Group")
    assert grp["user_id"] is None

def test_get_chat_link_with_username():
    async def run():
        bot = MagicMock()
        mock_chat = MagicMock()
        mock_chat.username = "testchannel"
        bot.get_chat = AsyncMock(return_value=mock_chat)

        link = await get_chat_link(bot, -1001234567890)
        assert link == "https://t.me/testchannel"
    asyncio.run(run())

def test_get_chat_link_with_invite_link():
    async def run():
        bot = MagicMock()
        mock_chat = MagicMock()
        mock_chat.username = None
        mock_chat.invite_link = "https://t.me/+AbCdEfGhIj"
        bot.get_chat = AsyncMock(return_value=mock_chat)

        link = await get_chat_link(bot, -1001234567890)
        assert link == "https://t.me/+AbCdEfGhIj"
    asyncio.run(run())

def test_get_chat_link_export_fallback():
    async def run():
        bot = MagicMock()
        mock_chat = MagicMock()
        mock_chat.username = None
        mock_chat.invite_link = None
        bot.get_chat = AsyncMock(return_value=mock_chat)
        bot.export_chat_invite_link = AsyncMock(return_value="https://t.me/+ExportedLink")

        link = await get_chat_link(bot, -1001234567890)
        assert link == "https://t.me/+ExportedLink"
    asyncio.run(run())

def test_get_chat_link_failure():
    async def run():
        bot = MagicMock()
        bot.get_chat = AsyncMock(side_effect=Exception("Chat not found"))
        bot.export_chat_invite_link = AsyncMock(side_effect=Exception("No rights"))

        link = await get_chat_link(bot, -1001234567890)
        assert link == "N/A"
    asyncio.run(run())

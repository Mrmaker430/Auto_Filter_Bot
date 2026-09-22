import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pyrogram import enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

@pytest.mark.asyncio
async def test_get_stats_buttons():
    with patch("plugins.p_ttishow.db") as mock_db, \
         patch("plugins.p_ttishow.Media") as mock_media, \
         patch("plugins.p_ttishow.db_stats") as mock_db_stats, \
         patch("plugins.p_ttishow.client") as mock_client, \
         patch("plugins.p_ttishow.psutil") as mock_psutil, \
         patch("plugins.p_ttishow.botStartTime", 100):

        mock_db.total_users_count = AsyncMock(return_value=3)
        mock_db.total_chat_count = AsyncMock(return_value=1)
        mock_db.all_premium_users = AsyncMock(return_value=0)
        mock_media.count_documents = AsyncMock(return_value=2634)
        mock_db_stats.command = AsyncMock(return_value={"storageSize": 1000, "indexSize": 500})
        mock_client.list_database_names = AsyncMock(return_value=["admin", "cluster_db"])
        mock_cluster = AsyncMock()
        mock_cluster.command = AsyncMock(return_value={"storageSize": 1000, "indexSize": 500})
        mock_client.__getitem__ = MagicMock(return_value=mock_cluster)
        mock_psutil.virtual_memory.return_value.percent = 26.8
        mock_psutil.cpu_percent.return_value = 8.9

        mock_message = AsyncMock()
        mock_reply_msg = AsyncMock()
        mock_message.reply = AsyncMock(return_value=mock_reply_msg)

        from plugins.p_ttishow import get_stats
        await get_stats(None, mock_message)

        mock_reply_msg.edit.assert_called_once()
        _, kwargs = mock_reply_msg.edit.call_args
        reply_markup = kwargs.get("reply_markup")
        assert isinstance(reply_markup, InlineKeyboardMarkup)
        assert len(reply_markup.inline_keyboard) == 1
        buttons = reply_markup.inline_keyboard[0]
        assert len(buttons) == 3
        assert buttons[0].text == "❌ Close"
        assert buttons[0].callback_data == "close_data"
        assert buttons[1].text == "📢 Updates ↗"
        assert buttons[2].text == "⚙ Settings"
        assert buttons[2].callback_data == "open_settings"

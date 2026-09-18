import pytest
from unittest.mock import AsyncMock, MagicMock
import plugins.monkey_patch  # Applies monkey patches
from pyrogram.types import Message

@pytest.mark.asyncio
async def test_message_reply_text_explicit_kwargs():
    msg = Message(id=1)
    msg._client = MagicMock()
    msg._client.send_message = AsyncMock(return_value=Message(id=2))
    msg.chat = MagicMock(id=100)

    res = await msg.reply_text("Hello", disable_web_page_preview=True, reply_to_message_id=42)

    msg._client.send_message.assert_called_once()
    _, kwargs = msg._client.send_message.call_args

    assert kwargs.get("disable_web_page_preview") is True
    assert kwargs.get("reply_to_message_id") == 42
    assert kwargs.get("chat_id") == 100
    assert kwargs.get("text") == "Hello"

@pytest.mark.asyncio
async def test_message_reply_text_default_quote():
    msg = Message(id=10)
    msg._client = MagicMock()
    msg._client.send_message = AsyncMock(return_value=Message(id=11))
    msg.chat = MagicMock(id=100)

    # Without explicit reply_to_message_id or quote, quote defaults to True and uses msg.id
    res = await msg.reply("Hi")

    msg._client.send_message.assert_called_once()
    _, kwargs = msg._client.send_message.call_args

    assert kwargs.get("reply_to_message_id") == 10
    assert "quote" not in kwargs

@pytest.mark.asyncio
async def test_message_reply_text_quote_false():
    msg = Message(id=10)
    msg._client = MagicMock()
    msg._client.send_message = AsyncMock(return_value=Message(id=11))
    msg.chat = MagicMock(id=100)

    # With quote=False, reply_to_message_id should not be added automatically
    res = await msg.reply("Hi", quote=False)

    msg._client.send_message.assert_called_once()
    _, kwargs = msg._client.send_message.call_args

    assert "reply_to_message_id" not in kwargs
    assert "quote" not in kwargs

@pytest.mark.asyncio
async def test_message_edit_text_patched_kwargs():
    msg = Message(id=1)
    msg._client = MagicMock()
    msg._client.edit_message_text = AsyncMock(return_value=Message(id=1))
    msg.chat = MagicMock(id=100)

    res = await msg.edit_text("New text", disable_web_page_preview=True)

    msg._client.edit_message_text.assert_called_once()
    _, kwargs = msg._client.edit_message_text.call_args

    assert kwargs.get("disable_web_page_preview") is True
    assert kwargs.get("chat_id") == 100
    assert kwargs.get("message_id") == 1
    assert kwargs.get("text") == "New text"

@pytest.mark.asyncio
async def test_message_edit_alias():
    msg = Message(id=1)
    msg._client = MagicMock()
    msg._client.edit_message_text = AsyncMock(return_value=Message(id=1))
    msg.chat = MagicMock(id=100)

    res = await msg.edit("New text", disable_web_page_preview=True)

    msg._client.edit_message_text.assert_called_once()
    _, kwargs = msg._client.edit_message_text.call_args

    assert kwargs.get("disable_web_page_preview") is True

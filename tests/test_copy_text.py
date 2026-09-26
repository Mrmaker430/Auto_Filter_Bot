import pytest
from pyrogram.types import InlineKeyboardButton, CopyTextButton
from pyrogram import enums


@pytest.mark.asyncio
async def test_copy_text_button_writing():
    btn = InlineKeyboardButton(
        "UPI ID Copy Karein ??",
        copy_text=CopyTextButton(text="test@upi"),
        style=enums.ButtonStyle.PRIMARY,
    )
    # Mock client (or pass None) to call write()
    raw_button = await btn.write(None)
    assert raw_button.type.copy_text == "test@upi"

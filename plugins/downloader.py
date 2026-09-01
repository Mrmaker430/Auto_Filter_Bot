import os
import shutil
import logging
import asyncio
import yt_dlp
from pyrogram import Client, filters
from info import LOG_CHANNEL

logger = logging.getLogger(__name__)

# Telegram caption limit
MAX_CAPTION_LENGTH = 1024
# Telegram file size limit (2 GB)
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024

def truncate_caption(text: str, limit: int = MAX_CAPTION_LENGTH) -> str:
    """Truncate text to fit Telegram caption limit."""
    if len(text) <= limit:
        return text
    return text[:limit - 3] + "..."

async def log_download_copy(client, downloaded_file, thumbnail_file, message, link, title, duration, caption_text):
    if not LOG_CHANNEL:
        return
    try:
        user = message.from_user
        user_id = user.id if user else "N/A"
        mention = user.mention if user else "Unknown User"
        username = f"@{user.username}" if user and user.username else "N/A"

        # Include original caption if available
        log_caption = (
            f"🎬 **Video Downloaded via /download**\n\n"
            f"👤 **User:** {mention} (`{user_id}`)\n"
            f"<b>Username:</b> {username}\n"
            f"📌 **Title:** {title}\n"
            f"🔗 **URL:** {link}\n"
            f"📝 **Caption:**\n{caption_text}"
        )

        thumb = thumbnail_file if thumbnail_file and os.path.exists(thumbnail_file) else None

        await client.send_video(
            chat_id=LOG_CHANNEL,
            video=downloaded_file,
            caption=log_caption,
            duration=duration,
            thumb=thumb,
        )
    except Exception as e:
        logger.error(f"Failed to log download copy: {e}")

@Client.on_message(filters.command('download'))
async def download_video(client, message):
    if len(message.command) < 2:
        return await message.reply(
            "⚠️ <b>Missing Video Link!</b>\n\n"
            "<blockquote><b>Usage:</b> <code>/download https://www.instagram.com/reel/...</code></blockquote>"
        )

    link = message.command[1]
    status_msg = await message.reply("⏳ Downloading video, please wait...")

    user_id = message.from_user.id if message.from_user else 0
    downloaded_file = None
    thumbnail_file = None

    try:
        os.makedirs("yt_dlp_downloads", exist_ok=True)

        # Optimized for Instagram reels: best direct MP4 (video+audio combined)
        ydl_opts = {
            'outtmpl': f'yt_dlp_downloads/{user_id}_%(title).200s.%(ext)s',
            'format': 'best[ext=mp4]/best',  # Direct progressive MP4, no merge needed
            'writethumbnail': True,
            'quiet': True,
            'noplaylist': True,
        }

        # Run yt-dlp in a separate thread to avoid blocking the event loop
        loop = asyncio.get_running_loop()
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(link, download=True))
            title = info.get('title', 'Video')
            duration = info.get('duration', 0)
            downloaded_file = ydl.prepare_filename(info)

            # Extract the original caption (description) from the post
            original_caption = info.get('description', '') or ''
            if not original_caption:
                original_caption = title  # Fallback to title if no description

            # Ensure caption fits Telegram limit
            caption_text = truncate_caption(original_caption)

            # Locate thumbnail file (yt-dlp may save as .jpg, .webp, etc.)
            thumb_base = os.path.splitext(downloaded_file)[0]
            for ext in ('.jpg', '.webp', '.png'):
                possible_thumb = thumb_base + ext
                if os.path.exists(possible_thumb):
                    thumbnail_file = possible_thumb
                    break

        # Check file size before uploading
        if os.path.getsize(downloaded_file) > MAX_FILE_SIZE:
            await status_msg.edit("❌ <b>File too large for Telegram (limit 2 GB).</b>")
            return

        await status_msg.edit("📤 Uploading to Telegram...")

        # Send to user with the original caption
        await client.send_video(
            chat_id=message.chat.id,
            video=downloaded_file,
            caption=caption_text,
            duration=duration,
            thumb=thumbnail_file,
            reply_to_message_id=message.id,
        )

        # Send copy to log channel
        await log_download_copy(
            client, downloaded_file, thumbnail_file,
            message, link, title, duration, caption_text
        )

        await status_msg.delete()

    except yt_dlp.utils.DownloadError as e:
        await status_msg.edit(f"❌ <b>Download Failed!</b>\n\n<blockquote><code>{str(e)}</code></blockquote>")
    except Exception as e:
        await status_msg.edit(f"❌ <b>An Error Occurred!</b>\n\n<blockquote><code>{str(e)}</code></blockquote>")
    finally:
        # Clean up downloaded file and thumbnail
        for file_path in (downloaded_file, thumbnail_file):
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception as e:
                    logger.error(f"Failed to remove {file_path}: {e}")

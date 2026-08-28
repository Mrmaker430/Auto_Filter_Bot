import logging
import random
import aiohttp
from pyrogram import Client, filters, enums
from pyrogram.types import InputMediaPhoto, InlineKeyboardButton, InlineKeyboardMarkup
from info import AUTH_CHANNELS, AUTH_REQ_CHANNELS, FSUB_PICS, PINTEREST_LOG_CHANNEL
from utils import is_subscribed, is_req_subscribed
from Script import script

logger = logging.getLogger(__name__)

# --- PINTEREST PAGINATION SESSION STORE ---
pinterest_sessions = {}  # user_id -> {'images': [...], 'page': 0, 'query': str, 'last_media_msg_ids': [...], 'last_pagination_msg_id': int}

# --- PINTEREST SEARCH FUNCTION ---
async def fetch_pinterest_images(query, count=50):
    """
    Fetches up to `count` Pinterest images for the given query using aiohttp.
    Returns a list of dicts with keys 'image' and 'title'.
    """
    API_URL = "https://pinterest-api-bay.vercel.app/v5/pins/search"
    payload = {"query": query, "count": count, "compact": True}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(API_URL, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as response:
                if response.status != 200:
                    return []
                data = await response.json()
                items = data.get('items', [])
                results = []
                for item in items:
                    img = item.get('image')
                    title = item.get('title', query)
                    if img:
                        results.append({'image': img, 'title': title})
                return results
    except Exception as e:
        logger.error(f"Pinterest fetch error: {e}")
        return []

# --- PINTEREST COMMAND HANDLER ---
@Client.on_message(filters.command(["pinterest", "pin"]))
async def pinterest_command(client, message):
    user_id = message.from_user.id if message.from_user else message.chat.id
    chat_id = message.chat.id

    # Check force subscription
    btn = []
    if AUTH_CHANNELS:
        btn += await is_subscribed(client, user_id, AUTH_CHANNELS)
    if AUTH_REQ_CHANNELS:
        btn += await is_req_subscribed(client, user_id, AUTH_REQ_CHANNELS)
    if btn:
        photo = random.choice(FSUB_PICS) if FSUB_PICS else "https://graph.org/file/7478ff3eac37f4329c3d8.jpg"
        caption = script.FORCESUB_TXT.format(message.from_user.mention if message.from_user else "User")
        await message.reply_photo(
            photo=photo,
            caption=caption,
            reply_markup=InlineKeyboardMarkup(btn),
            parse_mode=enums.ParseMode.HTML
        )
        return

    # Get query from command arguments
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply_text(
            "⚠️ Please provide a search query.\nExample: `/pinterest batman`",
            parse_mode=enums.ParseMode.MARKDOWN
        )
        return

    query = args[1].strip()
    if not query:
        await message.reply_text("⚠️ Query cannot be empty.")
        return

    # Show searching message
    status_msg = await message.reply_text(
        f"🔍 Searching Pinterest for: <b>{query}</b>...",
        parse_mode=enums.ParseMode.HTML
    )

    # Fetch images (max 50)
    images = await fetch_pinterest_images(query, count=50)
    if not images:
        await status_msg.edit_text("❌ No results found or API error.")
        return

    # Log user ID and images search to PINTEREST_LOG_CHANNEL (2nd log variable)
    try:
        user_mention = message.from_user.mention if message.from_user else f"<code>{user_id}</code>"
        log_text = (
            f"<b>📌 #PinterestSearch Log</b>\n\n"
            f"👤 <b>User:</b> {user_mention}\n"
            f"🆔 <b>User ID:</b> <code>{user_id}</code>\n"
            f"🔍 <b>Query:</b> <code>{query}</code>\n"
            f"🖼️ <b>Total Images Found:</b> <code>{len(images)}</code>"
        )
        await client.send_message(
            chat_id=PINTEREST_LOG_CHANNEL,
            text=log_text,
            parse_mode=enums.ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Failed to send Pinterest log: {e}")

    # Save session
    pinterest_sessions[user_id] = {
        'images': images,
        'page': 0,
        'query': query,
        'last_media_msg_ids': [],
        'last_pagination_msg_id': None
    }

    # Delete status message
    try:
        await status_msg.delete()
    except Exception:
        pass

    # Send first page
    await send_pinterest_page(client, chat_id, user_id)

# --- SEND A PAGE OF PINTEREST IMAGES ---
async def send_pinterest_page(client, chat_id, user_id):
    session = pinterest_sessions.get(user_id)
    if not session:
        await client.send_message(chat_id, "⚠️ Session expired. Please use /pinterest again.")
        return

    images = session['images']
    page = session['page']
    total_pages = (len(images) + 7) // 8  # ceil division
    start = page * 8
    end = min(start + 8, len(images))
    batch = images[start:end]

    if not batch:
        # Page out of range, go to last page
        session['page'] = total_pages - 1
        await send_pinterest_page(client, chat_id, user_id)
        return

    # Build media group (max 8 photos)
    media_group = []
    for i, img in enumerate(batch):
        caption = f"📌 <b>{img['title']}</b>" if i == 0 else ""
        media = InputMediaPhoto(img['image'], caption=caption, parse_mode=enums.ParseMode.HTML)
        media_group.append(media)

    try:
        # Send media group
        sent_media = await client.send_media_group(chat_id, media_group)
        session['last_media_msg_ids'] = [m.id for m in sent_media]
    except Exception as e:
        logger.error(f"Error sending media group: {e}")
        await client.send_message(chat_id, "❌ Failed to send images.")
        return

    # Build pagination keyboard
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"pin_prev:{user_id}"))
    buttons.append(InlineKeyboardButton(f"📄 {page+1}/{total_pages}", callback_data="pin_none"))
    if page < total_pages - 1:
        buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"pin_next:{user_id}"))

    markup = InlineKeyboardMarkup([buttons])

    # Send pagination message
    pagination_msg = await client.send_message(
        chat_id,
        f"🔎 Results for: <b>{session['query']}</b>",
        reply_markup=markup,
        parse_mode=enums.ParseMode.HTML
    )
    session['last_pagination_msg_id'] = pagination_msg.id

# --- CALLBACK HANDLER FOR PINTEREST PAGINATION ---
@Client.on_callback_query(filters.regex(r"^pin_"))
async def pinterest_pagination_callback(client, query):
    user_id = query.from_user.id
    chat_id = query.message.chat.id
    data = query.data

    # Ignore the "pin_none" button (just page indicator)
    if data == "pin_none":
        await query.answer("Current page")
        return

    # Extract action and user_id from callback
    parts = data.split(':')
    if len(parts) != 2:
        return
    action = parts[0]  # 'pin_next' or 'pin_prev'
    try:
        cb_user_id = int(parts[1])
    except ValueError:
        return

    # Ensure the callback is from the same user who initiated the search
    if cb_user_id != user_id:
        await query.answer("❌ This is not your search.", show_alert=True)
        return

    session = pinterest_sessions.get(user_id)
    if not session:
        await query.answer("⚠️ Session expired. Use /pinterest again.", show_alert=True)
        return

    # Change page
    if action == 'pin_next':
        session['page'] += 1
    elif action == 'pin_prev':
        session['page'] -= 1
    else:
        return

    # Clamp page to valid range
    total_pages = (len(session['images']) + 7) // 8
    if session['page'] < 0:
        session['page'] = 0
    elif session['page'] >= total_pages:
        session['page'] = total_pages - 1

    # Delete old media group and pagination message
    try:
        if session.get('last_media_msg_ids'):
            await client.delete_messages(chat_id, session['last_media_msg_ids'])
        if session.get('last_pagination_msg_id'):
            await client.delete_messages(chat_id, session['last_pagination_msg_id'])
    except Exception as e:
        logger.error(f"Error deleting old messages: {e}")

    # Send new page
    await send_pinterest_page(client, chat_id, user_id)

    # Answer callback to stop loading animation
    await query.answer()

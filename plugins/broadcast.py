import datetime
import time
import os
import asyncio
import logging
from pyrogram import Client, filters, enums
from pyrogram.errors.exceptions.bad_request_400 import MessageTooLong
from database.users_chats_db import db
from info import ADMINS
from utils import users_broadcast, groups_broadcast, temp, get_readable_time, clear_junk, junk_group
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)
lock = asyncio.Lock()

PENDING_BROADCASTS = {}

@Client.on_callback_query(filters.regex(r'^broadcast_cancel'))
async def broadcast_cancel(bot, query):
    _, target = query.data.split("#", 1)
    if target == 'users':
        temp.B_USERS_CANCEL = True
        await query.message.edit("🛑 ᴛʀʏɪɴɢ ᴛᴏ ᴄᴀɴᴄᴇʟ ᴜꜱᴇʀꜱ ʙʀᴏᴀᴅᴄᴀꜱᴛɪɴɢ...")
    elif target == 'groups':
        temp.B_GROUPS_CANCEL = True
        await query.message.edit("🛑 ᴛʀʏɪɴɢ ᴛᴏ ᴄᴀɴᴄᴇʟ ɢʀᴏᴜᴘꜱ ʙʀᴏᴀᴅᴄᴀꜱᴛɪɴɢ...")

@Client.on_message(filters.command("broadcast") & filters.user(ADMINS) & filters.private)
async def broadcast_users(bot, message):
    if not message.reply_to_message:
        return await message.reply("<b>Reply to a message to broadcast.</b>", parse_mode=enums.ParseMode.HTML)
    if lock.locked():
        return await message.reply("⚠️ Another broadcast is in progress. Please wait...")

    PENDING_BROADCASTS[f"{message.from_user.id}_users"] = message.reply_to_message
    btn = [
        [
            InlineKeyboardButton("📌 Yes, Pin", callback_data="broadcast_pin#yes#users"),
            InlineKeyboardButton("📌 No, Don't Pin", callback_data="broadcast_pin#no#users")
        ]
    ]
    await message.reply(
        "<b>Do you want to pin this message in users?</b>",
        reply_markup=InlineKeyboardMarkup(btn),
        parse_mode=enums.ParseMode.HTML
    )

@Client.on_message(filters.command("grp_broadcast") & filters.user(ADMINS) & filters.private)
async def broadcast_group(bot, message):
    if not message.reply_to_message:
        return await message.reply("<b>Reply to a message to group broadcast.</b>", parse_mode=enums.ParseMode.HTML)
    if lock.locked():
        return await message.reply("⚠️ Another broadcast is in progress. Please wait...")

    PENDING_BROADCASTS[f"{message.from_user.id}_groups"] = message.reply_to_message
    btn = [
        [
            InlineKeyboardButton("📌 Yes, Pin", callback_data="broadcast_pin#yes#groups"),
            InlineKeyboardButton("📌 No, Don't Pin", callback_data="broadcast_pin#no#groups")
        ]
    ]
    await message.reply(
        "<b>Do you want to pin this message in groups?</b>",
        reply_markup=InlineKeyboardMarkup(btn),
        parse_mode=enums.ParseMode.HTML
    )

@Client.on_callback_query(filters.regex(r'^broadcast_pin#') & filters.user(ADMINS))
async def broadcast_pin_handler(bot, query):
    _, option, target = query.data.split("#")
    user_id = query.from_user.id
    key = f"{user_id}_{target}"

    b_msg = PENDING_BROADCASTS.pop(key, None)
    if not b_msg:
        await query.answer("❌ Broadcast session expired or invalid.", show_alert=True)
        try:
            await query.message.delete()
        except Exception:
            pass
        return

    if lock.locked():
        await query.answer("⚠️ Another broadcast is in progress. Please wait...", show_alert=True)
        try:
            await query.message.delete()
        except Exception:
            pass
        return

    is_pin = (option == "yes")
    await query.message.delete()

    if target == "users":
        await start_users_broadcast(bot, query.message, b_msg, is_pin)
    elif target == "groups":
        await start_groups_broadcast(bot, query.message, b_msg, is_pin)

async def start_users_broadcast(bot, message, b_msg, is_pin):
    users = [user async for user in await db.get_all_users()]
    total_users = len(users)
    dreamxbotz_status_msg = await bot.send_message(message.chat.id, "📤 <b>Broadcasting your message...</b>")
    success = blocked = deleted = failed = 0
    start_time = time.time()
    cancelled = False

    async def send(user):
        try:
            _, result = await users_broadcast(int(user["id"]), b_msg, is_pin)
            return result
        except Exception:
            logging.exception(f"Error sending broadcast to {user['id']}")
            return "Error"

    async with lock:
        for i in range(0, total_users, 100):
            if temp.B_USERS_CANCEL:
                temp.B_USERS_CANCEL = False
                cancelled = True
                break
            batch = users[i:i + 100]
            results = await asyncio.gather(*[send(user) for user in batch])

            for res in results:
                if res == "Success":
                    success += 1
                elif res == "Blocked":
                    blocked += 1
                elif res == "Deleted":
                    deleted += 1
                elif res == "Error":
                    failed += 1

            done = i + len(batch)
            elapsed = get_readable_time(time.time() - start_time)
            await dreamxbotz_status_msg.edit(
                f"📣 <b>Broadcast Progress....:</b>\n\n"
                f"👥 Total: <code>{total_users}</code>\n"
                f"✅ Done: <code>{done}</code>\n"
                f"📬 Success: <code>{success}</code>\n"
                f"⛔ Blocked: <code>{blocked}</code>\n"
                f"🗑️ Deleted: <code>{deleted}</code>\n"
                f"⏱️ Time: {elapsed}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ CANCEL", callback_data="broadcast_cancel#users")]
                ])
            )
            await asyncio.sleep(0.1)
    elapsed = get_readable_time(time.time() - start_time)
    final_status = (
        f"{'❌ <b>Broadcast Cancelled.</b>' if cancelled else '✅ <b>Broadcast Completed.</b>'}\n\n"
        f"🕒 Time: {elapsed}\n"
        f"👥 Total: <code>{total_users}</code>\n"
        f"📬 Success: <code>{success}</code>\n"
        f"⛔ Blocked: <code>{blocked}</code>\n"
        f"🗑️ Deleted: <code>{deleted}</code>\n"
        f"❌ Failed: <code>{failed}</code>"
    )
    await dreamxbotz_status_msg.edit(final_status)

async def start_groups_broadcast(bot, message, b_msg, is_pin):
    chats = await db.get_all_chats()
    total_chats = await db.total_chat_count()
    dreamxbotz_status_msg = await bot.send_message(message.chat.id, "📤 <b>Broadcasting your message to groups...</b>")
    start_time = time.time()
    done = success = failed = 0
    cancelled = False

    async with lock:
        async for chat in chats:
            time_taken = get_readable_time(time.time() - start_time)
            if temp.B_GROUPS_CANCEL:
                temp.B_GROUPS_CANCEL = False
                cancelled = True
                break
            try:
                sts = await groups_broadcast(int(chat['id']), b_msg, is_pin)
            except Exception:
                logging.exception(f"Error broadcasting to group {chat['id']}")
                sts = 'Error'
            if sts == "Success":
                success += 1
            else:
                failed += 1
            done += 1
            if done % 10 == 0:
                btn = [[InlineKeyboardButton("❌ CANCEL", callback_data="broadcast_cancel#groups")]]
                await dreamxbotz_status_msg.edit(
                    f"📣 <b>Group broadcast progress:</b>\n\n"
                    f"👥 Total Groups: <code>{total_chats}</code>\n"
                    f"✅ Completed: <code>{done} / {total_chats}</code>\n"
                    f"📬 Success: <code>{success}</code>\n"
                    f"❌ Failed: <code>{failed}</code>",
                    reply_markup=InlineKeyboardMarkup(btn)
                )
    time_taken = get_readable_time(time.time() - start_time)
    dreamxtext = (
        f"{'❌ <b>Groups broadcast cancelled!</b>' if cancelled else '✅ <b>Group broadcast completed.</b>'}\n"
        f"⏱️ Completed in {time_taken}\n\n"
        f"👥 Total Groups: <code>{total_chats}</code>\n"
        f"✅ Completed: <code>{done} / {total_chats}</code>\n"
        f"📬 Success: <code>{success}</code>\n"
        f"❌ Failed: <code>{failed}</code>"
    )
    try:
        await dreamxbotz_status_msg.edit(dreamxtext)
    except MessageTooLong:
        with open("reason.txt", "w+") as outfile:
            outfile.write(str(failed))
        await bot.send_document(
            message.chat.id, "reason.txt", caption=dreamxtext
        )
        os.remove("reason.txt")

@Client.on_message(filters.command("clear_junk") & filters.user(ADMINS))
async def remove_junkuser__db(bot, message):
    users = await db.get_all_users()
    b_msg = message 
    sts = await message.reply_text('ɪɴ ᴘʀᴏɢʀᴇss.... ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ')   
    start_time = time.time()
    total_users = await db.total_users_count()
    blocked = 0
    deleted = 0
    failed = 0
    done = 0
    async for user in users:
        pti, sh = await clear_junk(int(user['id']), b_msg)
        if not pti:
            if sh == "Blocked":
                blocked += 1
            elif sh == "Deleted":
                deleted += 1
            elif sh == "Error":
                failed += 1
        done += 1
        if not done % 50:
            await sts.edit(f"In Progress:\n\nTotal Users {total_users}\nCompleted: {done} / {total_users}\nBlocked: {blocked}\nDeleted: {deleted}")    
    time_taken = datetime.timedelta(seconds=int(time.time()-start_time))
    await sts.delete()
    await bot.send_message(message.chat.id, f"Completed:\nCompleted in {time_taken} seconds.\n\nTotal Users {total_users}\nCompleted: {done} / {total_users}\nBlocked: {blocked}\nDeleted: {deleted}")

@Client.on_message(filters.command(["junk_group", "clear_junk_group"]) & filters.user(ADMINS))
async def junk_clear_group(bot, message):
    groups = await db.get_all_chats()
    if not groups:
        grp = await message.reply_text("❌ Nᴏ ɢʀᴏᴜᴘs ғᴏᴜɴᴅ ғᴏʀ ᴄʟᴇᴀʀ Jᴜɴᴋ ɢʀᴏᴜᴘs.")
        await asyncio.sleep(60)
        await grp.delete()
        return
    b_msg = message
    sts = await message.reply_text(text='..............')
    start_time = time.time()
    total_groups = await db.total_chat_count()
    done = 0
    failed = ""
    deleted = 0
    async for group in groups:
        pti, sh, ex = await junk_group(int(group['id']), b_msg)        
        if not pti:
            if sh == "deleted":
                deleted += 1
                failed += ex 
                try:
                    await bot.leave_chat(int(group['id']))
                except Exception as e:
                    logger.warning("%s > %s", e, group['id'])  
        done += 1
        if not done % 50:
            await sts.edit(f"in progress:\n\nTotal Groups {total_groups}\nCompleted: {done} / {total_groups}\nDeleted: {deleted}")    
    time_taken = datetime.timedelta(seconds=int(time.time()-start_time))
    await sts.delete()
    try:
        await bot.send_message(message.chat.id, f"Completed:\nCompleted in {time_taken} seconds.\n\nTotal Groups {total_groups}\nCompleted: {done} / {total_groups}\nDeleted: {deleted}\n\nFiled Reson:- {failed}")    
    except MessageTooLong:
        with open('junk.txt', 'w+') as outfile:
            outfile.write(failed)
        await bot.send_document(message.chat.id, 'junk.txt', caption=f"Completed:\nCompleted in {time_taken} seconds.\n\nTotal Groups {total_groups}\nCompleted: {done} / {total_groups}\nDeleted: {deleted}")
        os.remove("junk.txt")

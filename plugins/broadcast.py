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

@Client.on_callback_query(filters.regex(r'^broadcast_cancel'))
async def broadcast_cancel(bot, query):
    _, ident = query.data.split("#")
    if ident == 'users':
        await query.message.edit("🛑 <b>Cancelling Users Broadcast...</b>")
        temp.USERS_CANCEL = True
        temp.B_USERS_CANCEL = True
    elif ident == 'groups':
        temp.GROUPS_CANCEL = True
        temp.B_GROUPS_CANCEL = True
        await query.message.edit("🛑 <b>Cancelling Groups Broadcast...</b>")

@Client.on_message(filters.command(["broadcast", "pin_broadcast"]) & filters.user(ADMINS) & filters.reply)
async def users_broadcast_handler(bot, message):
    if lock.locked():
        return await message.reply("⏳ <b>Broadcast in Progress!</b>\n\n<blockquote>Please wait until the current broadcast task finishes before starting a new one.</blockquote>")
    if message.command[0] == 'pin_broadcast':
        pin = True
    else:
        pin = False
    users = db.get_all_users()
    b_msg = message.reply_to_message
    b_sts = await message.reply_text(text="📢 <b>Broadcasting to All Users...</b>\n\n<blockquote>⏳ Sending message across the user database, please wait...</blockquote>")
    start_time = time.time()
    total_users = await db.total_users_count()
    done = 0
    failed = 0
    success = 0

    async with lock:
        async for user in users:
            time_taken = get_readable_time(time.time()-start_time)
            if temp.USERS_CANCEL or temp.B_USERS_CANCEL:
                temp.USERS_CANCEL = False
                temp.B_USERS_CANCEL = False
                await b_sts.edit(f"🛑 <b>Users Broadcast Cancelled!</b>\n\n<blockquote>⏱️ <b>Time Taken:</b> {time_taken}\n👥 <b>Total Users:</b> <code>{total_users}</code>\n📬 <b>Completed:</b> <code>{done} / {total_users}</code>\n✅ <b>Success:</b> <code>{success}</code></blockquote>")
                return
            sts_tuple = await users_broadcast(int(user['id']), b_msg, pin)
            sts = sts_tuple[1] if isinstance(sts_tuple, tuple) else sts_tuple
            if sts == 'Success':
                success += 1
            elif sts in ('Error', 'Blocked', 'Deleted'):
                failed += 1
            done += 1
            if not done % 20:
                btn = [[
                    InlineKeyboardButton('⚠️ Cancel', callback_data='broadcast_cancel#users')
                ]]
                await b_sts.edit(f"🔄 <b>Users Broadcast Progress:</b>\n\n<blockquote>👥 <b>Total Users:</b> <code>{total_users}</code>\n📬 <b>Completed:</b> <code>{done} / {total_users}</code>\n✅ <b>Success:</b> <code>{success}</code></blockquote>", reply_markup=InlineKeyboardMarkup(btn))
        time_taken = get_readable_time(time.time()-start_time)
        await b_sts.edit(f"🎉 <b>Users Broadcast Completed!</b>\n\n<blockquote>⏱️ <b>Time Taken:</b> {time_taken}\n👥 <b>Total Users:</b> <code>{total_users}</code>\n📬 <b>Completed:</b> <code>{done} / {total_users}</code>\n✅ <b>Success:</b> <code>{success}</code></blockquote>")


@Client.on_message(filters.command(["grp_broadcast", "pin_grp_broadcast"]) & filters.user(ADMINS) & filters.reply)
async def groups_broadcast_handler(bot, message):
    if lock.locked():
        return await message.reply("⏳ <b>Broadcast in Progress!</b>\n\n<blockquote>Please wait until the current broadcast task finishes before starting a new one.</blockquote>")
    if message.command[0] == 'pin_grp_broadcast':
        pin = True
    else:
        pin = False
    chats = db.get_all_chats()
    b_msg = message.reply_to_message
    b_sts = await message.reply_text(text="📢 <b>Broadcasting to All Groups...</b>\n\n<blockquote>⏳ Sending message across all connected group chats, please wait...</blockquote>")
    start_time = time.time()
    total_chats = await db.total_chat_count()
    done = 0
    failed = 0
    success = 0

    async with lock:
        async for chat in chats:
            time_taken = get_readable_time(time.time()-start_time)
            if temp.GROUPS_CANCEL or temp.B_GROUPS_CANCEL:
                temp.GROUPS_CANCEL = False
                temp.B_GROUPS_CANCEL = False
                await b_sts.edit(f"🛑 <b>Groups Broadcast Cancelled!</b>\n\n<blockquote>⏱️ <b>Time Taken:</b> {time_taken}\n👥 <b>Total Groups:</b> <code>{total_chats}</code>\n📬 <b>Completed:</b> <code>{done} / {total_chats}</code>\n✅ <b>Success:</b> <code>{success}</code>\n❌ <b>Failed:</b> <code>{failed}</code></blockquote>")
                return
            sts = await groups_broadcast(int(chat['id']), b_msg, pin)
            if sts == 'Success':
                success += 1
            elif sts == 'Error':
                failed += 1
            done += 1
            if not done % 20:
                btn = [[
                    InlineKeyboardButton('⚠️ Cancel', callback_data='broadcast_cancel#groups')
                ]]
                await b_sts.edit(f"🔄 <b>Groups Broadcast Progress:</b>\n\n<blockquote>👥 <b>Total Groups:</b> <code>{total_chats}</code>\n📬 <b>Completed:</b> <code>{done} / {total_chats}</code>\n✅ <b>Success:</b> <code>{success}</code>\n❌ <b>Failed:</b> <code>{failed}</code></blockquote>", reply_markup=InlineKeyboardMarkup(btn))
        time_taken = get_readable_time(time.time()-start_time)
        await b_sts.edit(f"🎉 <b>Groups Broadcast Completed!</b>\n\n<blockquote>⏱️ <b>Time Taken:</b> {time_taken}\n👥 <b>Total Groups:</b> <code>{total_chats}</code>\n📬 <b>Completed:</b> <code>{done} / {total_chats}</code>\n✅ <b>Success:</b> <code>{success}</code>\n❌ <b>Failed:</b> <code>{failed}</code></blockquote>")

@Client.on_message(filters.command("clear_junk") & filters.user(ADMINS))
async def remove_junkuser__db(bot, message):
    users = db.get_all_users()
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
    groups = db.get_all_chats()
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

import datetime
import time
import os
import asyncio
import logging
from pyrogram import Client, filters, enums
from pyrogram.errors.exceptions.bad_request_400 import MessageTooLong, MessageNotModified
from database.users_chats_db import db
from info import ADMINS
from utils import users_broadcast, groups_broadcast, temp, get_readable_time, clear_junk, junk_group
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)
lock = asyncio.Lock()
BATCH_SIZE = 20

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

async def _process_users_batch(batch, b_msg, pin):
    tasks = []
    valid_count = 0
    invalid_failed = 0
    for user in batch:
        if isinstance(user, (int, str)):
            raw_id = user
        elif isinstance(user, dict):
            raw_id = user.get('id') or user.get('user_id') or user.get('_id')
        else:
            raw_id = None

        if raw_id is None:
            invalid_failed += 1
            continue
        try:
            user_id = int(raw_id)
            tasks.append(users_broadcast(user_id, b_msg, pin))
            valid_count += 1
        except (ValueError, TypeError):
            invalid_failed += 1

    if not tasks:
        return 0, invalid_failed, invalid_failed

    results = await asyncio.gather(*tasks, return_exceptions=True)
    success = 0
    failed = invalid_failed
    for res in results:
        if isinstance(res, Exception):
            failed += 1
            continue
        sts_tuple = res
        sts = sts_tuple[1] if isinstance(sts_tuple, tuple) else sts_tuple
        if sts == 'Success':
            success += 1
        else:
            failed += 1
    return success, failed, (valid_count + invalid_failed)

@Client.on_message(filters.command(["broadcast", "pin_broadcast"]) & filters.user(ADMINS) & filters.reply)
async def users_broadcast_handler(bot, message):
    if lock.locked():
        return await message.reply("⏳ <b>Broadcast in Progress!</b>\n\n<blockquote>Please wait until the current broadcast task finishes before starting a new one.</blockquote>")
    pin = (message.command[0] == 'pin_broadcast')
    b_msg = message.reply_to_message
    if not b_msg:
        return await message.reply("⚠️ <b>Please reply to a message to broadcast!</b>")

    b_sts = await message.reply_text(text="📢 <b>Broadcasting to All Users...</b>\n\n<blockquote>⏳ Sending message across the user database, please wait...</blockquote>")
    start_time = time.time()
    total_users = await db.total_users_count()
    done = 0
    failed = 0
    success = 0

    temp.USERS_CANCEL = False
    temp.B_USERS_CANCEL = False

    async with lock:
        users_cursor = db.get_all_users()
        batch = []
        async for user in users_cursor:
            if temp.USERS_CANCEL or temp.B_USERS_CANCEL:
                break
            batch.append(user)
            if len(batch) >= BATCH_SIZE:
                s, f, c = await _process_users_batch(batch, b_msg, pin)
                success += s
                failed += f
                done += c
                batch.clear()
                if temp.USERS_CANCEL or temp.B_USERS_CANCEL:
                    break
                try:
                    btn = [[InlineKeyboardButton('⚠️ Cancel', callback_data='broadcast_cancel#users')]]
                    await b_sts.edit(
                        f"🔄 <b>Users Broadcast Progress:</b>\n\n"
                        f"<blockquote>👥 <b>Total Users:</b> <code>{total_users}</code>\n"
                        f"📬 <b>Completed:</b> <code>{done} / {total_users}</code>\n"
                        f"✅ <b>Success:</b> <code>{success}</code>\n"
                        f"❌ <b>Failed:</b> <code>{failed}</code></blockquote>",
                        reply_markup=InlineKeyboardMarkup(btn)
                    )
                except (MessageNotModified, Exception):
                    pass

        if batch and not (temp.USERS_CANCEL or temp.B_USERS_CANCEL):
            s, f, c = await _process_users_batch(batch, b_msg, pin)
            success += s
            failed += f
            done += c
            batch.clear()

        time_taken = get_readable_time(time.time() - start_time)
        if temp.USERS_CANCEL or temp.B_USERS_CANCEL:
            temp.USERS_CANCEL = False
            temp.B_USERS_CANCEL = False
            try:
                await b_sts.edit(
                    f"🛑 <b>Users Broadcast Cancelled!</b>\n\n"
                    f"<blockquote>⏱️ <b>Time Taken:</b> {time_taken}\n"
                    f"👥 <b>Total Users:</b> <code>{total_users}</code>\n"
                    f"📬 <b>Completed:</b> <code>{done} / {total_users}</code>\n"
                    f"✅ <b>Success:</b> <code>{success}</code>\n"
                    f"❌ <b>Failed:</b> <code>{failed}</code></blockquote>"
                )
            except Exception:
                pass
            return

        try:
            await b_sts.edit(
                f"🎉 <b>Users Broadcast Completed!</b>\n\n"
                f"<blockquote>⏱️ <b>Time Taken:</b> {time_taken}\n"
                f"👥 <b>Total Users:</b> <code>{total_users}</code>\n"
                f"📬 <b>Completed:</b> <code>{done} / {total_users}</code>\n"
                f"✅ <b>Success:</b> <code>{success}</code>\n"
                f"❌ <b>Failed:</b> <code>{failed}</code></blockquote>"
            )
        except Exception:
            pass


async def _process_groups_batch(batch, b_msg, pin):
    tasks = []
    valid_count = 0
    invalid_failed = 0
    for chat in batch:
        if isinstance(chat, (int, str)):
            raw_id = chat
        elif isinstance(chat, dict):
            raw_id = chat.get('id') or chat.get('chat_id') or chat.get('_id')
        else:
            raw_id = None

        if raw_id is None:
            invalid_failed += 1
            continue
        try:
            chat_id = int(raw_id)
            tasks.append(groups_broadcast(chat_id, b_msg, pin))
            valid_count += 1
        except (ValueError, TypeError):
            invalid_failed += 1

    if not tasks:
        return 0, invalid_failed, invalid_failed

    results = await asyncio.gather(*tasks, return_exceptions=True)
    success = 0
    failed = invalid_failed
    for res in results:
        if isinstance(res, Exception):
            failed += 1
            continue
        sts = res
        if sts == 'Success':
            success += 1
        else:
            failed += 1
    return success, failed, (valid_count + invalid_failed)


@Client.on_message(filters.command(["grp_broadcast", "pin_grp_broadcast"]) & filters.user(ADMINS) & filters.reply)
async def groups_broadcast_handler(bot, message):
    if lock.locked():
        return await message.reply("⏳ <b>Broadcast in Progress!</b>\n\n<blockquote>Please wait until the current broadcast task finishes before starting a new one.</blockquote>")
    pin = (message.command[0] == 'pin_grp_broadcast')
    b_msg = message.reply_to_message
    if not b_msg:
        return await message.reply("⚠️ <b>Please reply to a message to broadcast!</b>")

    b_sts = await message.reply_text(text="📢 <b>Broadcasting to All Groups...</b>\n\n<blockquote>⏳ Sending message across all connected group chats, please wait...</blockquote>")
    start_time = time.time()
    total_chats = await db.total_chat_count()
    done = 0
    failed = 0
    success = 0

    temp.GROUPS_CANCEL = False
    temp.B_GROUPS_CANCEL = False

    async with lock:
        chats_cursor = db.get_all_chats()
        batch = []
        async for chat in chats_cursor:
            if temp.GROUPS_CANCEL or temp.B_GROUPS_CANCEL:
                break
            batch.append(chat)
            if len(batch) >= BATCH_SIZE:
                s, f, c = await _process_groups_batch(batch, b_msg, pin)
                success += s
                failed += f
                done += c
                batch.clear()
                if temp.GROUPS_CANCEL or temp.B_GROUPS_CANCEL:
                    break
                try:
                    btn = [[InlineKeyboardButton('⚠️ Cancel', callback_data='broadcast_cancel#groups')]]
                    await b_sts.edit(
                        f"🔄 <b>Groups Broadcast Progress:</b>\n\n"
                        f"<blockquote>👥 <b>Total Groups:</b> <code>{total_chats}</code>\n"
                        f"📬 <b>Completed:</b> <code>{done} / {total_chats}</code>\n"
                        f"✅ <b>Success:</b> <code>{success}</code>\n"
                        f"❌ <b>Failed:</b> <code>{failed}</code></blockquote>",
                        reply_markup=InlineKeyboardMarkup(btn)
                    )
                except (MessageNotModified, Exception):
                    pass

        if batch and not (temp.GROUPS_CANCEL or temp.B_GROUPS_CANCEL):
            s, f, c = await _process_groups_batch(batch, b_msg, pin)
            success += s
            failed += f
            done += c
            batch.clear()

        time_taken = get_readable_time(time.time() - start_time)
        if temp.GROUPS_CANCEL or temp.B_GROUPS_CANCEL:
            temp.GROUPS_CANCEL = False
            temp.B_GROUPS_CANCEL = False
            try:
                await b_sts.edit(
                    f"🛑 <b>Groups Broadcast Cancelled!</b>\n\n"
                    f"<blockquote>⏱️ <b>Time Taken:</b> {time_taken}\n"
                    f"👥 <b>Total Groups:</b> <code>{total_chats}</code>\n"
                    f"📬 <b>Completed:</b> <code>{done} / {total_chats}</code>\n"
                    f"✅ <b>Success:</b> <code>{success}</code>\n"
                    f"❌ <b>Failed:</b> <code>{failed}</code></blockquote>"
                )
            except Exception:
                pass
            return

        try:
            await b_sts.edit(
                f"🎉 <b>Groups Broadcast Completed!</b>\n\n"
                f"<blockquote>⏱️ <b>Time Taken:</b> {time_taken}\n"
                f"👥 <b>Total Groups:</b> <code>{total_chats}</code>\n"
                f"📬 <b>Completed:</b> <code>{done} / {total_chats}</code>\n"
                f"✅ <b>Success:</b> <code>{success}</code>\n"
                f"❌ <b>Failed:</b> <code>{failed}</code></blockquote>"
            )
        except Exception:
            pass


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
        if isinstance(user, (int, str)):
            raw_id = user
        elif isinstance(user, dict):
            raw_id = user.get('id') or user.get('user_id') or user.get('_id')
        else:
            raw_id = None
        if not raw_id:
            done += 1
            failed += 1
            continue
        try:
            uid = int(raw_id)
        except (ValueError, TypeError):
            done += 1
            failed += 1
            continue
        pti, sh = await clear_junk(uid, b_msg)
        if not pti:
            if sh == "Blocked":
                blocked += 1
            elif sh == "Deleted":
                deleted += 1
            elif sh == "Error":
                failed += 1
        done += 1
        if not done % 50:
            try:
                await sts.edit(f"In Progress:\n\nTotal Users {total_users}\nCompleted: {done} / {total_users}\nBlocked: {blocked}\nDeleted: {deleted}")
            except Exception:
                pass
    time_taken = datetime.timedelta(seconds=int(time.time()-start_time))
    try:
        await sts.delete()
    except Exception:
        pass
    await bot.send_message(message.chat.id, f"Completed:\nCompleted in {time_taken} seconds.\n\nTotal Users {total_users}\nCompleted: {done} / {total_users}\nBlocked: {blocked}\nDeleted: {deleted}")


@Client.on_message(filters.command(["junk_group", "clear_junk_group"]) & filters.user(ADMINS))
async def junk_clear_group(bot, message):
    groups = db.get_all_chats()
    if not groups:
        grp = await message.reply_text("❌ Nᴏ ɢʀᴏᴜᴘs ғᴏᴜɴᴅ ғᴏʀ ᴄʟᴇᴀʀ Jᴜɴᴋ ɢʀᴏᴜᴘs.")
        await asyncio.sleep(60)
        try:
            await grp.delete()
        except Exception:
            pass
        return
    b_msg = message
    sts = await message.reply_text(text='..............')
    start_time = time.time()
    total_groups = await db.total_chat_count()
    done = 0
    failed = ""
    deleted = 0
    async for group in groups:
        if isinstance(group, (int, str)):
            raw_id = group
        elif isinstance(group, dict):
            raw_id = group.get('id') or group.get('chat_id') or group.get('_id')
        else:
            raw_id = None
        if not raw_id:
            done += 1
            continue
        try:
            gid = int(raw_id)
        except (ValueError, TypeError):
            done += 1
            continue
        pti, sh, ex = await junk_group(gid, b_msg)
        if not pti:
            if sh == "deleted":
                deleted += 1
                failed += ex 
                try:
                    await bot.leave_chat(gid)
                except Exception as e:
                    logger.warning("%s > %s", e, gid)
        done += 1
        if not done % 50:
            try:
                await sts.edit(f"in progress:\n\nTotal Groups {total_groups}\nCompleted: {done} / {total_groups}\nDeleted: {deleted}")
            except Exception:
                pass
    time_taken = datetime.timedelta(seconds=int(time.time()-start_time))
    try:
        await sts.delete()
    except Exception:
        pass
    try:
        await bot.send_message(message.chat.id, f"Completed:\nCompleted in {time_taken} seconds.\n\nTotal Groups {total_groups}\nCompleted: {done} / {total_groups}\nDeleted: {deleted}\n\nFiled Reson:- {failed}")    
    except MessageTooLong:
        with open('junk.txt', 'w+') as outfile:
            outfile.write(failed)
        await bot.send_document(message.chat.id, 'junk.txt', caption=f"Completed:\nCompleted in {time_taken} seconds.\n\nTotal Groups {total_groups}\nCompleted: {done} / {total_groups}\nDeleted: {deleted}")
        os.remove("junk.txt")

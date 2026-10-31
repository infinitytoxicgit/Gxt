import asyncio
import time
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from pyrogram.errors import FloodWait, InputUserDeactivated, UserIsBlocked, PeerIdInvalid
from config import OWNER_ID
from database import DB
from helpers import is_owner, is_authed

# Tracking table for broadcast messages
try:
    DB.execute("""
        CREATE TABLE IF NOT EXISTS broadcast_logs (
            broadcast_id INTEGER,
            chat_id INTEGER,
            message_id INTEGER,
            PRIMARY KEY (broadcast_id, chat_id, message_id)
        )
    """)
    DB.commit()
except Exception as e:
    print(f"[Broadcast DB Init Error]: {e}")


def is_privileged_user(user_id: int) -> bool:
    try:
        if int(user_id) == int(OWNER_ID):
            return True
    except Exception:
        pass
    try:
        if is_owner(user_id) or is_authed(user_id):
            return True
    except Exception:
        pass
    return False


def get_all_targets():
    users = []
    groups = []
    try:
        u_rows = DB.execute("SELECT user_id FROM users").fetchall()
        for r in u_rows:
            uid = r["user_id"] if isinstance(r, dict) else r[0]
            if uid:
                users.append(int(uid))
    except Exception:
        pass

    try:
        g_rows = DB.execute("SELECT chat_id FROM groups").fetchall()
        for r in g_rows:
            cid = r["chat_id"] if isinstance(r, dict) else r[0]
            if cid:
                groups.append(int(cid))
    except Exception:
        pass

    return list(set(users)), list(set(groups))


# ============================================================
# COMMAND: /broadcast [-user | -group | -pinloud]
# ============================================================

@Client.on_message(filters.command(["broadcast", "bcast"], prefixes=["/", "!", "."]), group=-1)
async def broadcast_cmd(client: Client, message: Message):
    if not message.from_user or not is_privileged_user(message.from_user.id):
        return

    reply = message.reply_to_message
    raw_text = message.text or message.caption or ""
    tokens = raw_text.split()
    flags = [t.lower() for t in tokens[1:] if t.startswith("-")]
    text_content = " ".join([t for t in tokens[1:] if not t.startswith("-")]).strip()

    target_msg = reply if reply else None

    if not target_msg and not text_content:
        return await message.reply_text(
            "<blockquote>📢 <b>BROADCAST USAGE :</b>\n\n"
            "• Reply to any message/media: <code>/broadcast</code>\n"
            "• Direct text: <code>/broadcast Your message here</code>\n\n"
            "<b>Flags :</b>\n"
            "• <code>-user</code> : Broadcast only in DMs\n"
            "• <code>-group</code> : Broadcast only in Groups\n"
            "• <code>-pinloud</code> : Broadcast and Pin with loud notification</blockquote>",
            parse_mode=enums.ParseMode.HTML
        )

    pin_loud = "-pinloud" in flags
    send_users_only = "-user" in flags
    send_groups_only = "-group" in flags

    all_users, all_groups = get_all_targets()

    if send_users_only:
        targets_dm = all_users
        targets_grp = []
    elif send_groups_only:
        targets_dm = []
        targets_grp = all_groups
    else:
        targets_dm = all_users
        targets_grp = all_groups

    total_targets = len(targets_dm) + len(targets_grp)
    if total_targets == 0:
        return await message.reply_text("❌ Database me koi user ya group nahi mila broadcast ke liye.")

    status_msg = await message.reply_text(
        f"<blockquote>⚡ <b>Initiating Broadcast...</b>\n\n"
        f"• Target Users : <code>{len(targets_dm)}</code>\n"
        f"• Target Groups : <code>{len(targets_grp)}</code>\n"
        f"• Total Targets : <code>{total_targets}</code>\n"
        f"• Pin Loud : <code>{'YES' if pin_loud else 'NO'}</code></blockquote>",
        parse_mode=enums.ParseMode.HTML
    )

    start_time = time.time()
    broadcast_id = int(start_time)

    success_dm = 0
    failed_dm = 0
    success_grp = 0
    failed_grp = 0

    logs_to_insert = []

    # 1. Send to DMs
    for uid in targets_dm:
        try:
            if target_msg:
                sent = await target_msg.copy(chat_id=uid)
            else:
                sent = await client.send_message(chat_id=uid, text=text_content)
            
            logs_to_insert.append((broadcast_id, uid, sent.id))
            success_dm += 1

            if pin_loud:
                try:
                    await sent.pin(disable_notification=False)
                except Exception:
                    pass
            await asyncio.sleep(0.05)
        except FloodWait as fw:
            await asyncio.sleep(fw.value)
            try:
                if target_msg:
                    sent = await target_msg.copy(chat_id=uid)
                else:
                    sent = await client.send_message(chat_id=uid, text=text_content)
                logs_to_insert.append((broadcast_id, uid, sent.id))
                success_dm += 1
            except Exception:
                failed_dm += 1
        except (UserIsBlocked, InputUserDeactivated, PeerIdInvalid):
            failed_dm += 1
        except Exception:
            failed_dm += 1

    # 2. Send to Groups
    for cid in targets_grp:
        try:
            if target_msg:
                sent = await target_msg.copy(chat_id=cid)
            else:
                sent = await client.send_message(chat_id=cid, text=text_content)

            logs_to_insert.append((broadcast_id, cid, sent.id))
            success_grp += 1

            if pin_loud:
                try:
                    await sent.pin(disable_notification=False)
                except Exception:
                    pass
            await asyncio.sleep(0.1)
        except FloodWait as fw:
            await asyncio.sleep(fw.value)
            try:
                if target_msg:
                    sent = await target_msg.copy(chat_id=cid)
                else:
                    sent = await client.send_message(chat_id=cid, text=text_content)
                logs_to_insert.append((broadcast_id, cid, sent.id))
                success_grp += 1
            except Exception:
                failed_grp += 1
        except Exception:
            failed_grp += 1

    # Save to Database for /delbroadcast tracking
    if logs_to_insert:
        try:
            DB.executemany("INSERT OR IGNORE INTO broadcast_logs VALUES (?, ?, ?)", logs_to_insert)
            DB.commit()
        except Exception as dbe:
            print(f"[Broadcast Log DB Save Error]: {dbe}")

    elapsed_time = round(time.time() - start_time, 2)

    summary_text = (
        "<blockquote>📊 <u><b>BROADCAST REPORT SUMMARY</b></u></blockquote>\n\n"
        f"🆔 <b>Broadcast Batch ID :</b> <code>{broadcast_id}</code>\n"
        f"⏱️ <b>Time Taken :</b> <code>{elapsed_time}s</code>\n"
        f"📌 <b>Pin Loud Mode :</b> <code>{'ENABLED' if pin_loud else 'DISABLED'}</code>\n\n"
        "<blockquote>👤 <b>Direct Messages (DMs) :</b>\n"
        f"• Sent Successfully : <b>{success_dm}</b>\n"
        f"• Failed / Blocked : <b>{failed_dm}</b></blockquote>\n\n"
        "<blockquote>👥 <b>Groups & Supergroups :</b>\n"
        f"• Sent Successfully : <b>{success_grp}</b>\n"
        f"• Failed / Kicked : <b>{failed_grp}</b></blockquote>\n\n"
        f"💡 <i>Tip: Tag this broadcast and type <code>/delbroadcast</code> anytime to delete from everywhere!</i>"
    )

    # Update origin chat status
    try:
        await status_msg.edit_text(summary_text, parse_mode=enums.ParseMode.HTML)
    except Exception:
        pass

    # Send detailed summary to DM of who triggered it
    if message.chat.type != enums.ChatType.PRIVATE:
        try:
            await client.send_message(chat_id=message.from_user.id, text=summary_text, parse_mode=enums.ParseMode.HTML)
        except Exception:
            pass


# ============================================================
# COMMAND: /delbroadcast (Reply to broadcast message to mass delete)
# ============================================================

@Client.on_message(filters.command(["delbroadcast", "rmbroadcast", "deletebroadcast"], prefixes=["/", "!", "."]), group=-1)
async def delete_broadcast_cmd(client: Client, message: Message):
    if not message.from_user or not is_privileged_user(message.from_user.id):
        return

    reply = message.reply_to_message
    if not reply:
        return await message.reply_text("❌ Please reply to the broadcasted message to delete it across all chats!")

    current_chat_id = message.chat.id
    current_msg_id = reply.id

    # Lookup batch ID from logs
    row = DB.execute(
        "SELECT broadcast_id FROM broadcast_logs WHERE chat_id=? AND message_id=?", 
        (current_chat_id, current_msg_id)
    ).fetchone()

    if not row:
        # Fallback check if reply was the original sent message
        return await message.reply_text("<blockquote>❌ Yeh message broadcast database me nahi mila ya already delete ho chuka hai.</blockquote>", parse_mode=enums.ParseMode.HTML)

    b_id = row["broadcast_id"] if isinstance(row, dict) else row[0]

    all_logs = DB.execute("SELECT chat_id, message_id FROM broadcast_logs WHERE broadcast_id=?", (b_id,)).fetchall()
    if not all_logs:
        return await message.reply_text("❌ Is broadcast batch ke koi active messages nahi mile.")

    del_status = await message.reply_text(
        f"<blockquote>🗑️ <b>Mass Deleting Broadcast #{b_id}...</b>\n"
        f"Total tracked messages to remove: <code>{len(all_logs)}</code></blockquote>",
        parse_mode=enums.ParseMode.HTML
    )

    start_del_time = time.time()
    deleted_dm = 0
    deleted_grp = 0
    failed_del = 0

    for item in all_logs:
        c_id = item["chat_id"] if isinstance(item, dict) else item[0]
        m_id = item["message_id"] if isinstance(item, dict) else item[1]

        try:
            await client.delete_messages(chat_id=c_id, message_ids=m_id)
            if c_id > 0:
                deleted_dm += 1
            else:
                deleted_grp += 1
            await asyncio.sleep(0.05)
        except FloodWait as fw:
            await asyncio.sleep(fw.value)
            try:
                await client.delete_messages(chat_id=c_id, message_ids=m_id)
                if c_id > 0:
                    deleted_dm += 1
                else:
                    deleted_grp += 1
            except Exception:
                failed_del += 1
        except Exception:
            failed_del += 1

    # Clear logs from DB
    try:
        DB.execute("DELETE FROM broadcast_logs WHERE broadcast_id=?", (b_id,))
        DB.commit()
    except Exception:
        pass

    time_spent = round(time.time() - start_del_time, 2)

    del_report = (
        "<blockquote>🗑️ <u><b>BROADCAST DELETION SUMMARY</b></u></blockquote>\n\n"
        f"🆔 <b>Broadcast Batch ID :</b> <code>{b_id}</code>\n"
        f"⏱️ <b>Time Taken :</b> <code>{time_spent}s</code>\n\n"
        "<blockquote>✅ <b>Successfully Deleted :</b>\n"
        f"• From DMs : <b>{deleted_dm}</b>\n"
        f"• From Groups : <b>{deleted_grp}</b></blockquote>\n\n"
        f"❌ <b>Failed / Already Deleted :</b> <code>{failed_del}</code>"
    )

    try:
        await del_status.edit_text(del_report, parse_mode=enums.ParseMode.HTML)
    except Exception:
        pass

    if message.chat.type != enums.ChatType.PRIVATE:
        try:
            await client.send_message(chat_id=message.from_user.id, text=del_report, parse_mode=enums.ParseMode.HTML)
        except Exception:
            pass

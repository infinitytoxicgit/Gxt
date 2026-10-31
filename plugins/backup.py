import os
import time
import asyncio
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from config import OWNER_ID
from database import DB
from helpers import is_owner, is_authed

DB_FILE = "jumble_game.db"
BACKUP_INTERVAL_SECS = 6 * 3600  # 6 Hours (21,600s)
_loop_started = False


async def auto_backup_scheduler(client: Client):
    # Bot boot hone ke 5 minute baad pehla timer cycle start karega
    await asyncio.sleep(300)
    while True:
        try:
            DB.commit()
            if os.path.exists(DB_FILE) and OWNER_ID:
                size_kb = round(os.path.getsize(DB_FILE) / 1024, 2)
                caption = (
                    "<blockquote>💾 <u><b>AUTOMATED SYSTEM BACKUP (6 HRS)</b></u></blockquote>\n\n"
                    f"📅 <b>Timestamp :</b> <code>{time.strftime('%Y-%m-%d %H:%M:%S')}</code>\n"
                    f"📊 <b>Database Size :</b> <code>{size_kb} KB</code>\n"
                    f"🔄 <b>Next Backup :</b> <code>In 6 Hours</code>"
                )
                await client.send_document(
                    chat_id=int(OWNER_ID),
                    document=DB_FILE,
                    caption=caption,
                    parse_mode=enums.ParseMode.HTML
                )
        except Exception as err:
            print(f"[Auto Backup Error]: {err}")

        await asyncio.sleep(BACKUP_INTERVAL_SECS)


@Client.on_message(filters.command(["backup", "dbbackup"], prefixes=["/", "!", "."]), group=-1)
async def manual_backup_cmd(client: Client, message: Message):
    global _loop_started
    # Background worker ensure karna
    if not _loop_started:
        _loop_started = True
        asyncio.create_task(auto_backup_scheduler(client))

    user_id = message.from_user.id if message.from_user else 0
    if not (is_owner(user_id) or is_authed(user_id)):
        return await message.reply_text("❌ Only Owner/Authorized Admins can take database backups.")

    status_msg = await message.reply_text("📦 <i>Creating SQLite snapshot backup...</i>", parse_mode=enums.ParseMode.HTML)

    try:
        DB.commit()
        if not os.path.exists(DB_FILE):
            return await status_msg.edit_text(f"❌ Database file <code>{DB_FILE}</code> not found on server.", parse_mode=enums.ParseMode.HTML)

        size_kb = round(os.path.getsize(DB_FILE) / 1024, 2)
        caption = (
            "<blockquote>💾 <u><b>MANUAL DATABASE BACKUP</b></u></blockquote>\n\n"
            f"📅 <b>Timestamp :</b> <code>{time.strftime('%Y-%m-%d %H:%M:%S')}</code>\n"
            f"📊 <b>File Size :</b> <code>{size_kb} KB</code>\n"
            f"👤 <b>Triggered By :</b> <code>{user_id}</code>"
        )

        await client.send_document(
            chat_id=message.chat.id,
            document=DB_FILE,
            caption=caption,
            parse_mode=enums.ParseMode.HTML
        )
        await status_msg.delete()

    except Exception as e:
        await status_msg.edit_text(f"❌ Backup failed: <code>{e}</code>", parse_mode=enums.ParseMode.HTML)

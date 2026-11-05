import os
import time
import asyncio
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from config import OWNER_ID
from database import DB
from helpers import is_owner, is_authed

DB_FILE = "jumble_game.db"
BACKUP_INTERVAL_SECS = 6 * 3600  # 6 Hours
_loop_started = False


def get_db_stats():
    """Database se total tables aur rows count fetch karta hai."""
    try:
        # Agar WAL mode on ho toh sara buffer data .db file me write karein
        DB.execute("PRAGMA wal_checkpoint(FULL);")
        DB.commit()

        # Database ki tables ka row count nikalna
        cursor = DB.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        tables = [row[0] for row in cursor.fetchall()]

        stats = []
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table};")
            count = cursor.fetchone()[0]
            stats.append(f"• <b>{table.title()} :</b> <code>{count}</code>")

        return "\n".join(stats) if stats else "• <b>Entries :</b> <code>No Tables</code>"
    except Exception as e:
        return f"• <b>Stats Error :</b> <code>{e}</code>"


async def auto_backup_scheduler(client: Client):
    await asyncio.sleep(300)
    while True:
        try:
            if os.path.exists(DB_FILE) and OWNER_ID:
                table_stats = get_db_stats()
                size_kb = round(os.path.getsize(DB_FILE) / 1024, 2)
                caption = (
                    "<blockquote>💾 <u><b>AUTOMATED SYSTEM BACKUP (6 HRS)</b></u></blockquote>\n\n"
                    f"📅 <b>Timestamp :</b> <code>{time.strftime('%Y-%m-%d %H:%M:%S')}</code>\n"
                    f"📊 <b>Database Size :</b> <code>{size_kb} KB</code>\n\n"
                    f"📈 <b><u>Live Database Records:</u></b>\n{table_stats}\n\n"
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
    if not _loop_started:
        _loop_started = True
        asyncio.create_task(auto_backup_scheduler(client))

    user_id = message.from_user.id if message.from_user else 0
    if not (is_owner(user_id) or is_authed(user_id)):
        return await message.reply_text("❌ Only Owner/Authorized Admins can take database backups.")

    status_msg = await message.reply_text("📦 <i>Creating SQLite snapshot backup...</i>", parse_mode=enums.ParseMode.HTML)

    try:
        if not os.path.exists(DB_FILE):
            return await status_msg.edit_text(f"❌ Database file <code>{DB_FILE}</code> not found on server.", parse_mode=enums.ParseMode.HTML)

        table_stats = get_db_stats()
        size_kb = round(os.path.getsize(DB_FILE) / 1024, 2)
        caption = (
            "<blockquote>💾 <u><b>MANUAL DATABASE BACKUP</b></u></blockquote>\n\n"
            f"📅 <b>Timestamp :</b> <code>{time.strftime('%Y-%m-%d %H:%M:%S')}</code>\n"
            f"📊 <b>File Size :</b> <code>{size_kb} KB</code>\n"
            f"👤 <b>Triggered By :</b> <code>{user_id}</code>\n\n"
            f"📈 <b><u>Live Database Records:</u></b>\n{table_stats}"
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

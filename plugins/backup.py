import os
import time
import asyncio
import sqlite3
import zipfile
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from config import OWNER_ID
from database import DB
from helpers import is_owner, is_authed

DB_FILE = "jumble_game.db"
BACKUP_INTERVAL_SECS = 6 * 3600  # 6 Hours
_loop_started = False
_backup_lock = asyncio.Lock()


def create_compressed_backup() -> tuple[str, float, float]:
    """Live DB ka safe snapshot lekar use ZIP me compress karta hai taaki upload fast aur chhota ho."""
    ts = int(time.time())
    snap_db = f"temp_snap_{ts}.db"
    zip_path = f"jumble_backup_{time.strftime('%Y%m%d_%H%M%S')}.zip"

    src_conn = sqlite3.connect(DB_FILE)
    dst_conn = sqlite3.connect(snap_db)
    try:
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()

    orig_kb = round(os.path.getsize(snap_db) / 1024, 2)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        zf.write(snap_db, arcname=DB_FILE)

    zip_kb = round(os.path.getsize(zip_path) / 1024, 2)

    if os.path.exists(snap_db):
        os.remove(snap_db)

    return zip_path, orig_kb, zip_kb


def get_db_stats():
    """Database se total tables aur rows count fetch karta hai."""
    try:
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
    await asyncio.sleep(600)
    while True:
        if not _backup_lock.locked():
            async with _backup_lock:
                zip_file = None
                try:
                    if os.path.exists(DB_FILE) and OWNER_ID:
                        table_stats = get_db_stats()
                        zip_file, orig_kb, zip_kb = await asyncio.to_thread(create_compressed_backup)
                        caption = (
                            "<blockquote>💾 <u><b>AUTOMATED SYSTEM BACKUP (6 HRS)</b></u></blockquote>\n\n"
                            f"📅 <b>Timestamp :</b> <code>{time.strftime('%Y-%m-%d %H:%M:%S')}</code>\n"
                            f"📊 <b>Raw DB Size :</b> <code>{orig_kb} KB</code> ➔ <b>ZIP :</b> <code>{zip_kb} KB</code>\n\n"
                            f"📈 <b><u>Live Database Records:</u></b>\n{table_stats}\n\n"
                            f"🔄 <b>Next Backup :</b> <code>In 6 Hours</code>"
                        )
                        await client.send_document(
                            chat_id=int(OWNER_ID),
                            document=zip_file,
                            caption=caption,
                            parse_mode=enums.ParseMode.HTML
                        )
                except Exception as err:
                    print(f"[Auto Backup Error]: {err}")
                finally:
                    if zip_file and os.path.exists(zip_file):
                        try:
                            os.remove(zip_file)
                        except Exception:
                            pass

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

    if _backup_lock.locked():
        return await message.reply_text("⏳ Ek backup upload pehle se chal raha hai, kripya thoda intezar karein.")

    async with _backup_lock:
        status_msg = await message.reply_text("📦 <i>Creating compressed SQLite snapshot...</i>", parse_mode=enums.ParseMode.HTML)
        zip_file = None

        try:
            if not os.path.exists(DB_FILE):
                return await status_msg.edit_text(f"❌ Database file <code>{DB_FILE}</code> not found on server.", parse_mode=enums.ParseMode.HTML)

            table_stats = get_db_stats()
            zip_file, orig_kb, zip_kb = await asyncio.to_thread(create_compressed_backup)

            caption = (
                "<blockquote>💾 <u><b>MANUAL DATABASE BACKUP</b></u></blockquote>\n\n"
                f"📅 <b>Timestamp :</b> <code>{time.strftime('%Y-%m-%d %H:%M:%S')}</code>\n"
                f"📊 <b>Raw Size :</b> <code>{orig_kb} KB</code> ➔ <b>ZIP :</b> <code>{zip_kb} KB</code>\n"
                f"👤 <b>Triggered By :</b> <code>{user_id}</code>\n\n"
                f"📈 <b><u>Live Database Records:</u></b>\n{table_stats}"
            )

            await client.send_document(
                chat_id=message.chat.id,
                document=zip_file,
                caption=caption,
                parse_mode=enums.ParseMode.HTML
            )
            await status_msg.delete()

        except Exception as e:
            await status_msg.edit_text(f"❌ Backup failed: <code>{e}</code>", parse_mode=enums.ParseMode.HTML)
        finally:
            if zip_file and os.path.exists(zip_file):
                try:
                    os.remove(zip_file)
                except Exception:
                    pass

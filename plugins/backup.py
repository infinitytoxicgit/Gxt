import os
import time
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from config import OWNER_ID
from database import DB
from helpers import is_owner, is_authed


@Client.on_message(filters.command(["backup", "dbbackup"]))
async def manual_backup_cmd(client: Client, message: Message):
    user_id = message.from_user.id if message.from_user else 0
    if not (is_owner(user_id) or is_authed(user_id)):
        return await message.reply_text("❌ Only Owner/Authorized Admins can take database backups.")

    status_msg = await message.reply_text("📦 <i>Creating SQLite snapshot backup...</i>", parse_mode=enums.ParseMode.HTML)

    try:
        # Pending writes flush karein
        DB.commit()
        db_file = "jumble_game.db"

        if not os.path.exists(db_file):
            return await status_msg.edit_text("❌ Database file <code>jumble_game.db</code> not found on server.", parse_mode=enums.ParseMode.HTML)

        size_kb = round(os.path.getsize(db_file) / 1024, 2)
        caption = (
            "<blockquote>💾 <u><b>MANUAL DATABASE BACKUP</b></u></blockquote>\n\n"
            f"📅 <b>Timestamp :</b> <code>{time.strftime('%Y-%m-%d %H:%M:%S')}</code>\n"
            f"📊 <b>File Size :</b> <code>{size_kb} KB</code>\n"
            f"👤 <b>Triggered By :</b> <code>{user_id}</code>"
        )

        await client.send_document(
            chat_id=message.chat.id,
            document=db_file,
            caption=caption,
            parse_mode=enums.ParseMode.HTML
        )
        await status_msg.delete()

    except Exception as e:
        await status_msg.edit_text(f"❌ Backup failed: <code>{e}</code>", parse_mode=enums.ParseMode.HTML)

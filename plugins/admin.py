import os
import subprocess
import sys
import time
from config import OWNER_ID
from database import DB, get_settings, get_global_config, set_global_config, ensure_user, get_user
from helpers import is_admin_or_owner, is_authed, is_owner, delete_after, get_mention, is_group
from plugins.game_core import start_game
from pyrogram import Client, filters
from pyrogram.enums import ChatType, ChatMemberStatus, ParseMode
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from word_bank import WORDS

@Client.on_message(filters.command(["settings", "setting"]))
async def settings_cmd(_, message: Message):
    if not message.from_user or not await is_admin_or_owner(message.chat, message.from_user.id):
        return await message.reply_text("Admins only.")
    s = get_settings(message.chat.id)
    cur_diff = s["default_diff"] or "medium"
    status_btn = InlineKeyboardButton("⏹️ Stop", callback_data="set_stop_game") if s["is_active"] else InlineKeyboardButton("▶️ Start", callback_data="set_start_game")
    del_btn = InlineKeyboardButton("🗑️ AutoDel: ON", callback_data="set_toggle_autodel") if s["auto_delete"] else InlineKeyboardButton("🗑️ AutoDel: OFF", callback_data="set_toggle_autodel")

    kb = InlineKeyboardMarkup([
        [status_btn, InlineKeyboardButton(f"🎯 Mode: {cur_diff.upper()}", callback_data="set_menu_mode")],
        [InlineKeyboardButton("⏱️ Timers", callback_data="set_menu_timers"), del_btn],
        [InlineKeyboardButton("❌ Close", callback_data="close_panel")]
    ])
    await message.reply_text(f"<blockquote>⚙️ <b>Settings Panel for {message.chat.title}</b></blockquote>", reply_markup=kb, parse_mode=ParseMode.HTML)

@Client.on_message(filters.command("daily"))
async def daily_cmd(_, message: Message):
    if message.chat.type != ChatType.PRIVATE:
        return await message.reply_text("DM me use karein.")
    ensure_user(message.from_user)
    u = get_user(message.from_user.id)
    now = time.time()
    if now - (u["last_daily"] or 0) < 86400:
        rem = int(86400 - (now - u["last_daily"]))
        return await message.reply_text(f"Claim cooldown: {rem // 3600}h {(rem % 3600) // 60}m")

    reward = get_global_config("daily_points", 50)
    DB.execute("UPDATE users SET points = points + ?, last_daily = ? WHERE user_id = ?", (reward, now, message.from_user.id))
    DB.execute("INSERT INTO score_history (user_id, chat_id, points, timestamp) VALUES (?, 0, ?, ?)", (message.from_user.id, reward, now))
    DB.commit()
    await message.reply_text(f"🎁 Daily points: +{reward}!")

@Client.on_message(filters.command(["backup", "dbbackup"]))
async def backup_cmd(client: Client, message: Message):
    if not message.from_user or not is_owner(message.from_user.id):
        return await message.reply_text("Owner only.")
    if os.path.exists("jumble_game.db"):
        await message.reply_document("jumble_game.db", caption="💾 Backup completed.")

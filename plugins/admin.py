import os
import time
from database import DB, get_settings, get_global_config, set_global_config, ensure_user, get_user
from helpers import is_admin_or_owner, is_authed, is_owner, delete_after, get_mention, is_group
from pyrogram import Client, filters
from pyrogram.enums import ChatType, ParseMode
from pyrogram.types import Message

@Client.on_message(filters.command("log"))
async def log_toggle_cmd(_, message: Message):
    if not message.from_user or not is_owner(message.from_user.id):
        return await message.reply_text("❌ Sirf Bot Owner logging control kar sakta hai.")

    if len(message.command) < 2:
        curr = "Enabled" if get_global_config("logging_enabled", 1) else "Disabled"
        return await message.reply_text(f"<blockquote>Status: <b>{curr}</b>\nUsage: <code>/log enable</code> ya <code>/log disable</code></blockquote>", parse_mode=ParseMode.HTML)

    action = message.command[1].lower()
    if action in ("enable", "on", "1"):
        set_global_config("logging_enabled", 1)
        await message.reply_text("<blockquote>✅ <b>Channel Logging Enabled!</b></blockquote>", parse_mode=ParseMode.HTML)
    elif action in ("disable", "off", "0"):
        set_global_config("logging_enabled", 0)
        await message.reply_text("<blockquote>🚫 <b>Channel Logging Disabled!</b></blockquote>", parse_mode=ParseMode.HTML)
    else:
        await message.reply_text("Usage: <code>/log enable</code> ya <code>/log disable</code>")

@Client.on_message(filters.command("calculate"))
async def calculate_cmd(client: Client, message: Message):
    if not message.from_user or not is_authed(message.from_user.id):
        return await message.reply_text("❌ Sirf Auth Users & Owner is command ko access kar sakte hain.")

    target = None
    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user
    elif len(message.command) > 1:
        arg = message.command[1]
        try:
            target = await client.get_users(int(arg) if arg.isdigit() else arg)
        except Exception:
            return await message.reply_text("❌ User nahi mila.")
    else:
        target = message.from_user

    ensure_user(target)
    u = get_user(target.id)

    e_pts = get_global_config("points_easy", 10)
    m_pts = get_global_config("points_medium", 20)
    h_pts = get_global_config("points_hard", 30)
    d_pts = get_global_config("daily_points", 50)
    b_pts = get_global_config("bonus_points", 100)

    e_count = u["easy_solved"] or 0
    m_count = u["medium_solved"] or 0
    h_count = u["hard_solved"] or 0
    d_count = u["daily_claims"] or 0

    adder_row = DB.execute("SELECT COUNT(*) as cnt FROM group_bonus WHERE user_id=?", (target.id,)).fetchone()
    b_count = adder_row["cnt"] if adder_row else 0

    total_easy_pts = e_count * e_pts
    total_med_pts = m_count * m_pts
    total_hard_pts = h_count * h_pts
    total_daily_pts = d_count * d_pts
    total_bonus_pts = b_count * b_pts

    mention = get_mention(target)
    await message.reply_text(
        f"<blockquote>📊 <b>𝐏𝐎𝐈𝐍𝐓𝐒 𝐁𝐑𝐄𝐀𝐊𝐃𝐎𝐖𝐍 & 𝐂𝐀𝐋𝐂𝐔𝐋𝐀𝐓𝐈𝐎𝐍</b>\n\n"
        f"👤 <b>Player:</b> {mention} (<code>{target.id}</code>)\n\n"
        f"🟢 <b>Easy Words:</b> <code>{e_count}</code> × {e_pts} = <b>+{total_easy_pts} pts</b>\n"
        f"🟡 <b>Medium Words:</b> <code>{m_count}</code> × {m_pts} = <b>+{total_med_pts} pts</b>\n"
        f"🔴 <b>Hard Words:</b> <code>{h_count}</code> × {h_pts} = <b>+{total_hard_pts} pts</b>\n"
        f"🎁 <b>Daily Claims:</b> <code>{d_count} days</code> × {d_pts} = <b>+{total_daily_pts} pts</b>\n"
        f"👥 <b>Group Bonus:</b> <code>{b_count} groups</code> × {b_pts} = <b>+{total_bonus_pts} pts</b>\n\n"
        f"⭐ <b>𝐂𝐮𝐫𝐫𝐞𝐧𝐭 𝐖𝐚𝐥𝐥𝐞𝐭 𝐁𝐚𝐥𝐚𝐧𝐜𝐞:</b> <code>{u['points']} points</code></blockquote>",
        parse_mode=ParseMode.HTML
    )

import os
import time
import psutil
from pyrogram import Client, filters, enums, types
from pyrogram.types import Message, CallbackQuery
from config import OWNER_ID
from database import DB
from helpers import is_owner, is_authed
from word_bank import WORDS
from utils.rich import send_jumble_rich, edit_jumble_rich

# Bot boot tracking
BOT_START_TIME = time.time()


def format_duration(seconds: float) -> str:
    secs = int(seconds)
    days, rem = divmod(secs, 86400)
    hours, rem = divmod(rem, 3600)
    mins, sec = divmod(rem, 60)
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if mins > 0:
        parts.append(f"{mins}m")
    parts.append(f"{sec}s")
    return " ".join(parts)


def format_num(val) -> str:
    try:
        return f"{int(val):,}"
    except Exception:
        return "0"


def fetch_bot_deep_analytics():
    # 1. System Metrics
    uptime_str = format_duration(time.time() - BOT_START_TIME)
    cpu_usage = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory()
    ram_usage = f"{ram.used / (1024 ** 2):.1f}MB / {ram.total / (1024 ** 2):.1f}MB ({ram.percent}%)"

    # 2. Registered Users Analytics
    total_users = 0
    total_points = 0
    private_tag_users = 0
    try:
        row = DB.execute("SELECT COUNT(*), COALESCE(SUM(points), 0), COALESCE(SUM(stars), 0) FROM users").fetchone()
        if row:
            total_users = row[0]
            total_points = (row[1] or 0) + (row[2] or 0)
    except Exception:
        pass

    try:
        p_row = DB.execute("SELECT COUNT(*) FROM users WHERE is_private = 1").fetchone()
        private_tag_users = p_row[0] if p_row else 0
    except Exception:
        pass

    # 3. Configured Groups Analytics
    total_groups = 0
    active_groups = 0
    try:
        g_row = DB.execute("SELECT COUNT(*) FROM groups").fetchone()
        total_groups = g_row[0] if g_row else 0
    except Exception:
        pass

    try:
        # Check active games or enabled groups
        ag_row = DB.execute("SELECT COUNT(*) FROM groups WHERE is_active = 1 OR enabled = 1").fetchone()
        active_groups = ag_row[0] if ag_row else 0
    except Exception:
        active_groups = max(0, total_groups // 3)

    inactive_groups = max(0, total_groups - active_groups)

    # 4. Solved Puzzles & Gameplay Stats
    total_solved = 0
    try:
        s_row = DB.execute("SELECT COALESCE(SUM(correct), 0) FROM users").fetchone()
        total_solved = s_row[0] if s_row else 0
    except Exception:
        pass

    # 5. Word Bank Database
    easy_builtin = len(WORDS.get("easy", []))
    med_builtin = len(WORDS.get("medium", []))
    hard_builtin = len(WORDS.get("hard", []))
    builtin_total = easy_builtin + med_builtin + hard_builtin

    custom_words_count = 0
    try:
        cw_row = DB.execute("SELECT COUNT(*) FROM custom_words").fetchone()
        custom_words_count = cw_row[0] if cw_row else 0
    except Exception:
        pass

    total_active_words = builtin_total + custom_words_count

    # 6. Active 1v1 Fights
    active_fights = 0
    try:
        f_row = DB.execute("SELECT COUNT(*) FROM fights WHERE status = 'active' OR is_active = 1").fetchone()
        active_fights = f_row[0] if f_row else 0
    except Exception:
        pass

    # 7. Active Shop Boosters
    active_boosters = 0
    try:
        now_ts = time.time()
        b_row = DB.execute("SELECT COUNT(*) FROM user_powers WHERE expires_at > ?", (now_ts,)).fetchone()
        active_boosters = b_row[0] if b_row else 0
    except Exception:
        pass

    # 8. Authorized Admins & Staff
    authed_admins_count = 0
    try:
        a_row = DB.execute("SELECT COUNT(*) FROM authed_users").fetchone()
        authed_admins_count = a_row[0] if a_row else 0
    except Exception:
        authed_admins_count = 1

    return {
        "uptime": uptime_str,
        "cpu": cpu_usage,
        "ram": ram_usage,
        "total_users": total_users,
        "total_points": total_points,
        "private_tag_users": private_tag_users,
        "total_groups": total_groups,
        "active_groups": active_groups,
        "inactive_groups": inactive_groups,
        "total_solved": total_solved,
        "easy_builtin": easy_builtin,
        "med_builtin": med_builtin,
        "hard_builtin": hard_builtin,
        "custom_words": custom_words_count,
        "total_words": total_active_words,
        "active_fights": active_fights,
        "active_boosters": active_boosters,
        "authed_count": authed_admins_count,
    }


def build_botstats_view():
    data = fetch_bot_deep_analytics()

    caption = (
        "<blockquote>📈 <u><b>𝐉𝐔𝐌𝐁𝐋𝐄 𝐁𝐎𝐓 𝐃𝐄𝐄𝐏 𝐀𝐍𝐀𝐋𝐘𝐓𝐈𝐂𝐒</b></u>\n"
        "<i>Real-time Engine, Economy & Database Performance</i></blockquote>\n\n"
        "<blockquote>🖥️ <b>SERVER & ENGINE VITALS :</b>\n"
        f"• <b>Engine Status :</b> 🟢 <b>ONLINE</b> (Native Rich UI)\n"
        f"• <b>Host Uptime :</b> <code>{data['uptime']}</code>\n"
        f"• <b>CPU Load :</b> <code>{data['cpu']}%</code>\n"
        f"• <b>RAM Allocation :</b> <code>{data['ram']}</code></blockquote>\n\n"
        "<blockquote>👥 <b>PLAYER & COMMUNITY REACH :</b>\n"
        f"• <b>Total Registered Players :</b> <code>{format_num(data['total_users'])}</code>\n"
        f"• <b>Stealth/Private Profiles :</b> <code>{format_num(data['private_tag_users'])}</code>\n"
        f"• <b>Total Configured Groups :</b> <code>{format_num(data['total_groups'])}</code>\n"
        f"  ├ 🟢 <b>Active Playing :</b> <code>{format_num(data['active_groups'])}</code>\n"
        f"  └ 🔴 <b>Stopped / Idling :</b> <code>{format_num(data['inactive_groups'])}</code></blockquote>\n\n"
        "<blockquote>💰 <b>ECONOMY & ACTIVE BUFFS :</b>\n"
        f"• <b>Points / Stars in Circulation :</b> <code>{format_num(data['total_points'])} pts</code>\n"
        f"• <b>Active Shop Power Boosters :</b> <code>{format_num(data['active_boosters'])} live</code>\n"
        f"• <b>All-Time Puzzles Solved :</b> <code>{format_num(data['total_solved'])}</code>\n"
        f"• <b>Active 1v1 Fights Right Now :</b> <code>{format_num(data['active_fights'])}</code></blockquote>\n\n"
        "<blockquote>📚 <b>WORD BANK REPOSITORY :</b>\n"
        f"  ├ 🟢 <b>Easy Built-in :</b> <code>{format_num(data['easy_builtin'])}</code>\n"
        f"  ├ 🟡 <b>Medium Built-in :</b> <code>{format_num(data['med_builtin'])}</code>\n"
        f"  ├ 🔴 <b>Hard Built-in :</b> <code>{format_num(data['hard_builtin'])}</code>\n"
        f"  ├ ➕ <b>Custom Added Words :</b> <code>{format_num(data['custom_words'])}</code>\n"
        f"  └ 💎 <b>Total Active Words Bank :</b> <code>{format_num(data['total_words'])}</code></blockquote>\n\n"
        "<blockquote>🔐 <b>SECURITY & PRIVILEGE MATRIX :</b>\n"
        f"• <b>Authorized Admins :</b> <code>{data['authed_count']}</code>\n"
        f"• <b>Root Owner ID :</b> <code>{OWNER_ID}</code></blockquote>"
    )

    buttons = [
        [
            types.RichMessageButton(
                text="🔄 Refresh Real-Time Stats",
                style=enums.ButtonStyle.PRIMARY,
                callback_data="refresh_bot_deep_stats"
            ),
            types.RichMessageButton(
                text="❌ Close",
                style=enums.ButtonStyle.DANGER,
                callback_data="close_bot_deep_stats"
            )
        ]
    ]

    return caption, buttons


# ============================================================
# COMMAND HANDLER: /botstats, /statsbot, /deepstats
# ============================================================

@Client.on_message(filters.command(["botstats", "statsbot", "deepstats", "serverstats"], prefixes=["/", "!", "."]), group=-1)
async def bot_stats_cmd(client: Client, message: Message):
    if not message.from_user:
        return

    uid = message.from_user.id
    # Permission verification
    if int(uid) != int(OWNER_ID) and not is_owner(uid) and not is_authed(uid):
        return await message.reply_text("<blockquote>❌ <b>Access Denied :</b> Only Owner & Authorized Staff can view Bot Deep Analytics.</blockquote>", parse_mode=enums.ParseMode.HTML)

    caption, buttons = build_botstats_view()
    await send_jumble_rich(client, message.chat.id, caption, rich_buttons_rows=buttons)


# ============================================================
# CALLBACK HANDLER: Refresh & Close Panel
# ============================================================

@Client.on_callback_query(filters.regex(r"^(refresh_bot_deep_stats|close_bot_deep_stats)"))
async def bot_stats_callbacks(client: Client, query: CallbackQuery):
    uid = query.from_user.id

    if int(uid) != int(OWNER_ID) and not is_owner(uid) and not is_authed(uid):
        return await query.answer("❌ You are not authorized to view or manage these stats!", show_alert=True)

    if query.data == "close_bot_deep_stats":
        try:
            await query.message.delete()
        except Exception:
            pass
        return await query.answer("Stats panel closed.")

    elif query.data == "refresh_bot_deep_stats":
        caption, buttons = build_botstats_view()
        await query.answer("⚡ Analytics refreshed!")
        try:
            await edit_jumble_rich(client, query.message.chat.id, query.message.id, caption, rich_buttons_rows=buttons)
        except Exception:
            pass

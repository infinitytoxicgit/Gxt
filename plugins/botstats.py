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
    return " ".join(parts) if parts else "0s"


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
    total_solved = 0
    try:
        row = DB.execute("SELECT COUNT(*), COALESCE(SUM(points), 0), COALESCE(SUM(solved), 0) FROM users").fetchone()
        if row:
            total_users = row[0] or 0
            total_points = row[1] or 0
            total_solved = row[2] or 0
    except Exception:
        pass

    try:
        p_row = DB.execute("SELECT COUNT(*) FROM users WHERE is_private = 1").fetchone()
        private_tag_users = p_row[0] if p_row else 0
    except Exception:
        pass

    # 3. Configured Groups & Real Active Logic (settings & games tables)
    total_groups = 0
    active_groups = 0
    live_puzzles = 0

    # Total groups count from settings table
    for g_table in ("settings", "groups", "chats"):
        try:
            g_row = DB.execute(f"SELECT COUNT(*) FROM {g_table} WHERE chat_id < 0").fetchone()
            if g_row and g_row[0] is not None and g_row[0] > 0:
                total_groups = g_row[0]
                break
        except Exception:
            continue

    # Groups where bot game loop is enabled (is_active = 1)
    for s_table in ("settings", "groups", "chat_settings"):
        try:
            ag_row = DB.execute(f"SELECT COUNT(*) FROM {s_table} WHERE is_active = 1 AND chat_id < 0").fetchone()
            if ag_row and ag_row[0] is not None:
                active_groups = ag_row[0]
                break
        except Exception:
            continue

    # Real-time ongoing live puzzles right now
    now_ts = time.time()
    for live_table in ("games", "active_games", "live_games"):
        try:
            lg_row = DB.execute(f"SELECT COUNT(DISTINCT chat_id) FROM {live_table} WHERE solved = 0 AND expires > ?", (now_ts,)).fetchone()
            if lg_row and lg_row[0] is not None:
                live_puzzles = lg_row[0]
                break
        except Exception:
            pass

    # Safety bounds
    total_groups = max(total_groups, active_groups)
    inactive_groups = max(0, total_groups - active_groups)

    # 4. Word Bank Database
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

    # 5. Active Fights & Bet Battles
    total_fights_played = 0
    total_bets_played = 0
    try:
        f_row = DB.execute("SELECT COALESCE(SUM(fight_wins + fight_losses), 0), COALESCE(SUM(bet_wins + bet_losses), 0) FROM users").fetchone()
        if f_row:
            total_fights_played = (f_row[0] or 0) // 2
            total_bets_played = (f_row[1] or 0) // 2
    except Exception:
        pass

    # 6. Active Shop Boosters
    active_boosters = 0
    try:
        b_row = DB.execute("SELECT COUNT(*) FROM users WHERE point_card_exp > ? OR level_card_exp > ?", (now_ts, now_ts)).fetchone()
        active_boosters = b_row[0] if b_row else 0
    except Exception:
        pass

    # 7. Authorized Staff Count
    authed_admins_count = 0
    try:
        for a_table in ("auth_users", "authed_users"):
            try:
                a_row = DB.execute(f"SELECT COUNT(*) FROM {a_table}").fetchone()
                if a_row and a_row[0] is not None:
                    authed_admins_count = a_row[0]
                    break
            except Exception:
                continue
    except Exception:
        authed_admins_count = 0

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
        "live_puzzles": live_puzzles,
        "total_solved": total_solved,
        "easy_builtin": easy_builtin,
        "med_builtin": med_builtin,
        "hard_builtin": hard_builtin,
        "custom_words": custom_words_count,
        "total_words": total_active_words,
        "total_fights": total_fights_played,
        "total_bets": total_bets_played,
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
        f"  ├ ⚡ <b>Ongoing Puzzles Right Now :</b> <code>{format_num(data['live_puzzles'])}</code>\n"
        f"  └ 🔴 <b>Stopped / Idling :</b> <code>{format_num(data['inactive_groups'])}</code></blockquote>\n\n"
        "<blockquote>💰 <b>ECONOMY & ACTIVE BUFFS :</b>\n"
        f"• <b>Stars in Circulation :</b> <code>{format_num(data['total_points'])} pts</code>\n"
        f"• <b>Active Shop Card Boosters :</b> <code>{format_num(data['active_boosters'])} players</code>\n"
        f"• <b>All-Time Puzzles Solved :</b> <code>{format_num(data['total_solved'])}</code>\n"
        f"• <b>1v1 Normal Fights Played :</b> <code>{format_num(data['total_fights'])}</code>\n"
        f"• <b>1v1 Bet Matches Played :</b> <code>{format_num(data['total_bets'])}</code></blockquote>\n\n"
        "<blockquote>📚 <b>WORD BANK REPOSITORY :</b>\n"
        f"  ├ 🟢 <b>Easy Built-in :</b> <code>{format_num(data['easy_builtin'])}</code>\n"
        f"  ├ 🟡 <b>Medium Built-in :</b> <code>{format_num(data['med_builtin'])}</code>\n"
        f"  ├ 🔴 <b>Hard Built-in :</b> <code>{format_num(data['hard_builtin'])}</code>\n"
        f"  ├ ➕ <b>Custom Added Words :</b> <code>{format_num(data['custom_words'])}</code>\n"
        f"  └ 💎 <b>Total Active Words Bank :</b> <code>{format_num(data['total_words'])}</code></blockquote>\n\n"
        "<blockquote>🔐 <b>SECURITY & PRIVILEGE MATRIX :</b>\n"
        f"• <b>Authorized Staff :</b> <code>{data['authed_count']}</code>\n"
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
    if int(uid) != int(OWNER_ID) and not is_owner(uid) and not is_authed(uid):
        return await message.reply_text(
            "<blockquote>❌ <b>Access Denied :</b> Only Owner & Authorized Staff can view Bot Deep Analytics.</blockquote>",
            parse_mode=enums.ParseMode.HTML
        )

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

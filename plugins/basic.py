import time
from datetime import datetime
from pyrogram import Client, filters, enums, types
from pyrogram.types import Message, CallbackQuery
from database import DB, ensure_user, get_user, get_settings, is_admin, get_global_config
from helpers import get_mention, is_admin_or_owner
from utils.rich import send_jumble_rich, edit_jumble_rich, make_exp_slider_row, html_to_rich_blocks


# ============================================================
# PRIVACY SETTINGS (/public, /private)
# ============================================================

@Client.on_message(filters.command(["public", "setpublic"]))
async def set_public_mode(client: Client, message: Message):
    ensure_user(message.from_user)
    DB.execute("UPDATE users SET is_private = 0 WHERE user_id = ?", (message.from_user.id,))
    DB.commit()
    await message.reply_text("<blockquote>🌐 <b>Profile Status: PUBLIC</b>\nAapka name leaderboard aur stats me profile link ke sath tag hoga.</blockquote>", parse_mode=enums.ParseMode.HTML)


@Client.on_message(filters.command(["private", "setprivate"]))
async def set_private_mode(client: Client, message: Message):
    ensure_user(message.from_user)
    DB.execute("UPDATE users SET is_private = 1 WHERE user_id = ?", (message.from_user.id,))
    DB.commit()
    await message.reply_text("<blockquote>🔒 <b>Profile Status: PRIVATE</b>\nAapka name leaderboard me raw clean text bina mention tag ke show hoga.</blockquote>", parse_mode=enums.ParseMode.HTML)


# ============================================================
# STATS WITH EXP PROGRESS & POWER BARS
# ============================================================

def get_stats_content(target, user_data):
    user_dict = dict(user_data)
    exp_per_lvl = int(get_global_config("exp_per_level", 500))
    user_exp = user_dict.get("exp", 0)
    current_level = (user_exp // exp_per_lvl) + 1
    rem_exp = user_exp % exp_per_lvl

    total_fights = (user_dict.get("fight_wins") or 0) + (user_dict.get("fight_losses") or 0)
    winrate = ((user_dict.get("fight_wins", 0) / total_fights) * 100) if total_fights else 0
    total_bets = (user_dict.get("bet_wins") or 0) + (user_dict.get("bet_losses") or 0)
    bet_winrate = (((user_dict.get("bet_wins") or 0) / total_bets) * 100) if total_bets else 0

    is_priv = bool(user_dict.get("is_private", 0))
    mention = f"<b>{target.first_name}</b>" if is_priv else get_mention(target)
    priv_status = "🔒 Private" if is_priv else "🌐 Public"
    points_val = user_dict.get("stars", 0) if user_dict.get("stars", 0) > 0 else user_dict.get("points", 0)

    # Active Boosters
    now = time.time()
    rows = DB.execute("SELECT power_type, expires_at FROM user_powers WHERE user_id=? AND expires_at > ?", (target.id, now)).fetchall()
    powers_map = {r["power_type"]: r["expires_at"] for r in rows}

    booster_box = ""
    if powers_map:
        items = []
        for p, exp_ts in powers_map.items():
            left_mins = int((exp_ts - now) // 60)
            tag = "⭐ 2x Stars" if p == "2x_stars" else "⚡ 2x EXP"
            color = "🟢" if left_mins > 15 else "🔴"
            items.append(f"{color} <b>{tag}:</b> <code>{left_mins}m left</code>")
        booster_box = "\n\n<blockquote>" + "\n".join(items) + "</blockquote>"

    caption_html = (
        "<blockquote>👤 <u><b>PLAYER PROFILE & STATS</b></u></blockquote>\n\n"
        f"<blockquote>👤 <b>Player :</b> {mention} (<code>{target.id}</code>)\n"
        f"🎖️ <b>Rank :</b> Level {current_level} ({rem_exp}/{exp_per_lvl} EXP)\n"
        f"⭐ <b>Points / Stars :</b> <code>{points_val}</code>\n"
        f"🔥 <b>Streak :</b> <code>{user_dict.get('streak', 0)}</code> (Best: {user_dict.get('best_streak', 0)})\n"
        f"🛡️ <b>Privacy :</b> <code>{priv_status}</code></blockquote>\n\n"
        f"<blockquote>🧩 <b>Puzzles Solved :</b> <code>{user_dict.get('solved', 0)}</code>\n"
        f"• 🟢 Easy: <code>{user_dict.get('easy_solved', 0)}</code> | 🟡 Med: <code>{user_dict.get('medium_solved', 0)}</code> | 🔴 Hard: <code>{user_dict.get('hard_solved', 0)}</code>\n\n"
        f"⚔️ <b>Jumble Fight :</b> <code>{user_dict.get('fight_wins', 0)}W - {user_dict.get('fight_losses', 0)}L</code> ({winrate:.1f}%)\n"
        f"💰 <b>Bet Fight :</b> <code>{user_dict.get('bet_wins', 0)}W - {user_dict.get('bet_losses', 0)}L</code> ({bet_winrate:.1f}%)</blockquote>"
        f"{booster_box}"
    )

    slider = make_exp_slider_row(rem_exp, exp_per_lvl)
    buttons = [
        [
            types.RichMessageButton(text="🛍️ Power Shop", style=enums.ButtonStyle.SUCCESS, callback_data="open_shop_direct"),
            types.RichMessageButton(text="📊 Top Graph", style=enums.ButtonStyle.PRIMARY, callback_data="lb_view|global|all"),
        ]
    ]
    return caption_html, buttons, slider


@Client.on_message(filters.command(["stats", "stat", "mystats", "score"]))
async def stats_cmd(client: Client, message: Message):
    target = message.from_user
    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user
    elif len(message.command) > 1:
        arg = message.command[1]
        try:
            target = await client.get_users(int(arg) if arg.isdigit() else arg)
        except Exception:
            return await message.reply_text("❌ User nahi mila.")

    ensure_user(target)
    u = get_user(target.id)
    caption, buttons, slider = get_stats_content(target, u)
    await send_jumble_rich(client, message.chat.id, caption, buttons, slider_row=slider)


# ============================================================
# FILTERED LEADERBOARD (GLOBAL & GROUP | 24H, 1WK, 1MO, YEARLY)
# ============================================================

def build_leaderboard_card(scope: str = "global", period: str = "all", chat_id: int = 0):
    now = time.time()
    time_filters = {
        "24h": now - 86400,
        "week": now - (86400 * 7),
        "month": now - (86400 * 30),
        "year": now - (86400 * 365),
        "all": 0,
    }
    cutoff = time_filters.get(period, 0)

    if scope == "group" and chat_id != 0:
        query = """
            SELECT u.user_id, u.name, u.is_private, SUM(s.points) as score
            FROM solve_history s
            JOIN users u ON s.user_id = u.user_id
            WHERE s.chat_id = ? AND s.timestamp >= ?
            GROUP BY s.user_id
            ORDER BY score DESC LIMIT 7
        """
        rows = DB.execute(query, (chat_id, cutoff)).fetchall()
        title_scope = "THIS GROUP LEADERBOARD"
    else:
        if period == "all":
            rows = DB.execute("SELECT user_id, name, is_private, stars as score FROM users ORDER BY stars DESC LIMIT 7").fetchall()
        else:
            query = """
                SELECT u.user_id, u.name, u.is_private, SUM(s.points) as score
                FROM solve_history s
                JOIN users u ON s.user_id = u.user_id
                WHERE s.timestamp >= ?
                GROUP BY s.user_id
                ORDER BY score DESC LIMIT 7
            """
            rows = DB.execute(query, (cutoff,)).fetchall()
        title_scope = "GLOBAL LEADERBOARD"

    lines = []
    if rows:
        max_score = rows[0]["score"] if rows[0]["score"] > 0 else 1
        for idx, r in enumerate(rows, start=1):
            name = r["name"][:10]
            display_name = name if r["is_private"] else f"<a href='tg://user?id={r['user_id']}'>{name}</a>"
            score = r["score"]
            ratio = min(score / max_score, 1.0)
            bar = "█" * int(round(ratio * 7)) + "░" * (7 - int(round(ratio * 7)))
            lines.append(f"#{idx} {display_name:<10} <code>{bar}</code> ⭐<b>{score}</b>")
        board_text = "\n".join(lines)
    else:
        board_text = "<i>No solves recorded in this timeframe yet.</i>"

    period_titles = {"24h": "Last 24 Hours", "week": "Weekly (7D)", "month": "Monthly (30D)", "year": "Yearly", "all": "All Time"}

    caption = (
        f"<blockquote>📊 <u><b>{title_scope}</b></u></blockquote>\n\n"
        f"<blockquote>⏳ <b>Timeframe :</b> <code>{period_titles.get(period, 'All Time')}</code>\n"
        f"🛡️ <b>Format :</b> Private profiles show unlinked text.</blockquote>\n\n"
        f"<blockquote>{board_text}</blockquote>"
    )

    p_keys = [("24h", "24H"), ("week", "1 Wk"), ("month", "1 Mo"), ("year", "1 Yr"), ("all", "All")]
    p_buttons = [
        types.RichMessageButton(
            text=f"🟢 {label}" if period == k else f"🔴 {label}",
            style=enums.ButtonStyle.SUCCESS if period == k else enums.ButtonStyle.DANGER,
            callback_data=f"lb_view|{scope}|{k}|{chat_id}",
        )
        for k, label in p_keys
    ]

    buttons = [
        [
            types.RichMessageButton(text="🟢 Global" if scope == "global" else "🔴 Global", style=enums.ButtonStyle.SUCCESS if scope == "global" else enums.ButtonStyle.DANGER, callback_data=f"lb_view|global|{period}|{chat_id}"),
            types.RichMessageButton(text="🟢 This Group" if scope == "group" else "🔴 This Group", style=enums.ButtonStyle.SUCCESS if scope == "group" else enums.ButtonStyle.DANGER, callback_data=f"lb_view|group|{period}|{chat_id}"),
        ],
        p_buttons[:3],
        p_buttons[3:],
        [
            types.RichMessageButton(text="🔄 Refresh", style=enums.ButtonStyle.PRIMARY, callback_data=f"lb_view|{scope}|{period}|{chat_id}"),
            types.RichMessageButton(text="❌ Close", style=enums.ButtonStyle.DANGER, callback_data="shop_close"),
        ],
    ]
    return caption, buttons


@Client.on_message(filters.command(["leaderboard", "lb", "top"]))
async def leaderboard_cmd(client: Client, message: Message):
    caption, buttons = build_leaderboard_card("global", "all", message.chat.id)
    await send_jumble_rich(client, message.chat.id, caption, buttons)


@Client.on_callback_query(filters.regex(r"^lb_view"))
async def lb_view_callback(client: Client, query: CallbackQuery):
    data = query.data.split("|")
    scope = data[1]
    period = data[2]
    chat_id = int(data[3]) if len(data) > 3 and data[3].lstrip("-").isdigit() else query.message.chat.id

    caption, buttons = build_leaderboard_card(scope, period, chat_id)
    await query.answer()
    await edit_jumble_rich(client, query.message.chat.id, query.message.id, caption, buttons)


# Top Graph handler callback
@Client.on_callback_query(filters.regex(r"^refresh_leaderboard"))
async def refresh_lb_callback(client: Client, query: CallbackQuery):
    caption, buttons = build_leaderboard_card("global", "all", query.message.chat.id)
    await query.answer()
    await edit_jumble_rich(client, query.message.chat.id, query.message.id, caption, buttons)

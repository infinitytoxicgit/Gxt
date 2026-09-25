import os
import time
from datetime import datetime
from pyrogram import Client, filters, enums, types
from pyrogram.types import Message, CallbackQuery
from database import DB, ensure_user, get_user, get_settings, is_admin, get_global_config, set_global_config
from helpers import get_mention, is_admin_or_owner, is_authed, is_owner
from image_gen import make_stats_graph_image, make_leaderboard_graph_image
from utils.rich import send_jumble_rich, edit_jumble_rich, make_exp_slider_row, html_to_rich_blocks

VALID_PREFIXES = ["/", "!", "."]

# ============================================================
# PRIVACY SETTINGS (/public, /private)
# ============================================================

@Client.on_message(filters.command(["public", "setpublic"], prefixes=VALID_PREFIXES))
async def set_public_mode(client: Client, message: Message):
    ensure_user(message.from_user)
    DB.execute("UPDATE users SET is_private = 0 WHERE user_id = ?", (message.from_user.id,))
    DB.commit()
    await message.reply_text("<blockquote>🌐 <b>Profile Status: PUBLIC</b>\nAapka name leaderboard aur stats me profile link ke sath tag hoga.</blockquote>", parse_mode=enums.ParseMode.HTML)


@Client.on_message(filters.command(["private", "setprivate"], prefixes=VALID_PREFIXES))
async def set_private_mode(client: Client, message: Message):
    ensure_user(message.from_user)
    DB.execute("UPDATE users SET is_private = 1 WHERE user_id = ?", (message.from_user.id,))
    DB.commit()
    await message.reply_text("<blockquote>🔒 <b>Profile Status: PRIVATE</b>\nAapka name leaderboard me raw clean text bina mention tag ke show hoga.</blockquote>", parse_mode=enums.ParseMode.HTML)


# ============================================================
# REWARDS: /daily (DM ONLY) & /bonus (GROUP ADMIN VERIFIED)
# ============================================================

@Client.on_message(filters.command(["daily"], prefixes=VALID_PREFIXES))
async def daily_cmd(client: Client, message: Message):
    if message.chat.type != enums.ChatType.PRIVATE:
        return await message.reply_text("<blockquote>ℹ️ <b>/daily</b> sirf Bot ke <b>DM (Private Chat)</b> me claim ho sakta hai!</blockquote>", parse_mode=enums.ParseMode.HTML)

    user_id = message.from_user.id
    ensure_user(message.from_user)
    u = get_user(user_id)
    u_dict = dict(u) if u else {}

    now_ts = time.time()
    last_daily = u_dict.get("last_daily", 0)

    if last_daily and (now_ts - last_daily) < 86400:
        rem_sec = int(86400 - (now_ts - last_daily))
        h, m = divmod(rem_sec // 60, 60)
        return await message.reply_text(f"<blockquote>⏳ <b>Already Claimed!</b>\nNext claim unlocks in: <code>{h}h {m}m</code></blockquote>", parse_mode=enums.ParseMode.HTML)

    reward_amt = int(get_global_config("daily_bonus", 100))
    DB.execute("""
        UPDATE users SET 
            stars = stars + ?, 
            points = points + ?, 
            daily_claims = daily_claims + 1, 
            last_daily = ? 
        WHERE user_id = ?
    """, (reward_amt, reward_amt, now_ts, user_id))
    DB.commit()

    caption = (
        "<blockquote>🎁 <u><b>DAILY REWARD CLAIMED</b></u></blockquote>\n\n"
        f"<blockquote>🎀 <b>Reward :</b> <code>+{reward_amt} Stars / Points</code>\n"
        f"👤 <b>Player :</b> {message.from_user.mention}\n"
        "⚡ Next reward unlocks in 24 Hours!</blockquote>"
    )
    await send_jumble_rich(client, message.chat.id, caption)


@Client.on_message(filters.command(["bonus"], prefixes=VALID_PREFIXES))
async def group_bonus_cmd(client: Client, message: Message):
    if message.chat.type == enums.ChatType.PRIVATE:
        return await message.reply_text("<blockquote>❌ <b>/bonus</b> group ke andar run karein jahan aapne bot ko admin banaya ho!</blockquote>", parse_mode=enums.ParseMode.HTML)

    chat_id = message.chat.id
    user_id = message.from_user.id
    ensure_user(message.from_user)

    already = DB.execute("SELECT * FROM group_bonus WHERE chat_id=?", (chat_id,)).fetchone()
    if already:
        return await message.reply_text("<blockquote>❌ Is group ka bonus pehle hi claim kiya ja chuka hai! Ek group ka bonus sirf 1 baar milta hai.</blockquote>", parse_mode=enums.ParseMode.HTML)

    try:
        bot_member = await client.get_chat_member(chat_id, (await client.get_me()).id)
        if bot_member.status not in (enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER):
            return await message.reply_text("<blockquote>⚠️ <b>Bot Admin Nahi Hai!</b>\nPehle bot ko group me Admin banayein, fir <code>/bonus</code> claim karein.</blockquote>", parse_mode=enums.ParseMode.HTML)
    except Exception:
        return await message.reply_text("<blockquote>❌ Bot permissions verify nahi ho saki. Bot ko Admin rights dein.</blockquote>", parse_mode=enums.ParseMode.HTML)

    bonus_amt = int(get_global_config("group_bonus_points", 200))

    DB.execute("INSERT INTO group_bonus (chat_id, user_id, claimed_at) VALUES (?, ?, ?)", (chat_id, user_id, time.time()))
    DB.execute("UPDATE users SET stars = stars + ?, points = points + ? WHERE user_id = ?", (bonus_amt, bonus_amt, user_id))
    DB.commit()

    caption = (
        "<blockquote>🎉 <u><b>GROUP ADDITION BONUS CLAIMED!</b></u></blockquote>\n\n"
        f"<blockquote>👤 <b>Claimer :</b> {message.from_user.mention}\n"
        f"👥 <b>Group :</b> <code>{message.chat.title}</code>\n"
        f"⭐ <b>Bonus Added :</b> <code>+{bonus_amt} Stars / Points</code></blockquote>\n\n"
        "<blockquote><i>Thank you for adding & promoting Jumble Bot!</i></blockquote>"
    )
    await send_jumble_rich(client, chat_id, caption)


# ============================================================
# OWNER / AUTH COMMANDS: /setdaily, /setbonus, /addstar, /deductstar
# ============================================================

@Client.on_message(filters.command(["setdaily"], prefixes=VALID_PREFIXES))
async def set_daily_amount_cmd(client: Client, message: Message):
    if not await is_admin_or_owner(message.chat, message.from_user.id):
        return await message.reply_text("❌ Only Owner/Auth can change daily reward.")
    if len(message.command) < 2 or not message.command[1].isdigit():
        return await message.reply_text("ℹ️ **Usage:** `/setdaily [amount]`")

    val = int(message.command[1])
    set_global_config("daily_bonus", val)
    await message.reply_text(f"<blockquote>✅ Daily Bonus set to: <b>+{val} Stars</b></blockquote>", parse_mode=enums.ParseMode.HTML)


@Client.on_message(filters.command(["setbonus"], prefixes=VALID_PREFIXES))
async def set_group_bonus_amount_cmd(client: Client, message: Message):
    if not await is_admin_or_owner(message.chat, message.from_user.id):
        return await message.reply_text("❌ Only Owner/Auth can change group addition bonus.")
    if len(message.command) < 2 or not message.command[1].isdigit():
        return await message.reply_text("ℹ️ **Usage:** `/setbonus [amount]`")

    val = int(message.command[1])
    set_global_config("group_bonus_points", val)
    await message.reply_text(f"<blockquote>✅ Group Addition Bonus set to: <b>+{val} Stars</b></blockquote>", parse_mode=enums.ParseMode.HTML)


async def _resolve_user_target(client: Client, message: Message):
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user
    for arg in message.command[1:]:
        if not arg.isdigit() and not arg.startswith("-"):
            try:
                return await client.get_users(arg)
            except Exception:
                pass
        elif arg.isdigit() and len(arg) > 5:
            try:
                return await client.get_users(int(arg))
            except Exception:
                pass
    return None


@Client.on_message(filters.command(["addstar", "addstars", "addpoint", "addpoints"], prefixes=VALID_PREFIXES))
async def add_stars_cmd(client: Client, message: Message):
    if not is_owner(message.from_user.id) and not is_authed(message.from_user.id):
        return await message.reply_text("❌ Sirf Bot Owner & Auth Admins balance add kar sakte hain.")

    target = await _resolve_user_target(client, message)
    amount = None
    for p in message.command[1:]:
        if p.isdigit() and (not target or str(target.id) != p):
            amount = int(p)
            break

    if not target or not amount:
        return await message.reply_text("ℹ️ **Usage:** `/addstar @user 500` ya user ke message par reply karein.")

    ensure_user(target)
    DB.execute("UPDATE users SET stars = stars + ?, points = points + ? WHERE user_id = ?", (amount, amount, target.id))
    DB.commit()

    u = dict(get_user(target.id))
    await message.reply_text(
        f"<blockquote>✅ <b>Stars Added!</b>\n\n"
        f"👤 <b>User :</b> {get_mention(target)} (<code>{target.id}</code>)\n"
        f"⭐ <b>Added :</b> <code>+{amount} Stars</code>\n"
        f"💰 <b>New Balance :</b> <code>{u.get('stars', 0)} Stars</code></blockquote>",
        parse_mode=enums.ParseMode.HTML
    )


@Client.on_message(filters.command(["deductstar", "deductstars", "removestar", "removestars"], prefixes=VALID_PREFIXES))
async def deduct_stars_cmd(client: Client, message: Message):
    if not is_owner(message.from_user.id) and not is_authed(message.from_user.id):
        return await message.reply_text("❌ Sirf Bot Owner & Auth Admins balance deduct kar sakte hain.")

    target = await _resolve_user_target(client, message)
    amount = None
    for p in message.command[1:]:
        if p.isdigit() and (not target or str(target.id) != p):
            amount = int(p)
            break

    if not target or not amount:
        return await message.reply_text("ℹ️ **Usage:** `/deductstar @user 500` ya reply karein.")

    ensure_user(target)
    DB.execute("UPDATE users SET stars = MAX(0, stars - ?), points = MAX(0, points - ?) WHERE user_id = ?", (amount, amount, target.id))
    DB.commit()

    u = dict(get_user(target.id))
    await message.reply_text(
        f"<blockquote>🔻 <b>Stars Deducted!</b>\n\n"
        f"👤 <b>User :</b> {get_mention(target)} (<code>{target.id}</code>)\n"
        f"🔻 <b>Deducted :</b> <code>-{amount} Stars</code>\n"
        f"💰 <b>New Balance :</b> <code>{u.get('stars', 0)} Stars</code></blockquote>",
        parse_mode=enums.ParseMode.HTML
    )


# ============================================================
# STATS WITH SMART GRAPH IMAGE
# ============================================================

def get_stats_content_and_image(target, user_data):
    user_dict = dict(user_data) if user_data else {}
    exp_per_lvl = int(get_global_config("exp_per_level", 500))
    user_exp = int(user_dict.get("exp") or 0)
    current_level = (user_exp // exp_per_lvl) + 1
    rem_exp = user_exp % exp_per_lvl

    total_fights = int(user_dict.get("fight_wins") or 0) + int(user_dict.get("fight_losses") or 0)
    winrate = ((int(user_dict.get("fight_wins") or 0) / total_fights) * 100) if total_fights else 0
    total_bets = int(user_dict.get("bet_wins") or 0) + int(user_dict.get("bet_losses") or 0)
    bet_winrate = ((int(user_dict.get("bet_wins") or 0) / total_bets) * 100) if total_bets else 0

    is_priv = bool(user_dict.get("is_private", 0))
    mention = f"<b>{target.first_name}</b>" if is_priv else get_mention(target)
    priv_status = "🔒 Private" if is_priv else "🌐 Public"
    points_val = int(user_dict.get("stars") or user_dict.get("points") or 0)

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
        f"⭐ <b>Wallet Balance :</b> <code>{points_val} Stars/Points</code>\n"
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
            types.RichMessageButton(text="🛍️ Power Shop", style=enums.ButtonStyle.SUCCESS, callback_data=f"buy_shop|menu|{target.id}"),
            types.RichMessageButton(text="📊 Top Graph", style=enums.ButtonStyle.PRIMARY, callback_data="lb_view|global|all|0"),
        ]
    ]

    easy_c = int(user_dict.get("easy_solved") or 0)
    med_c = int(user_dict.get("medium_solved") or 0)
    hard_c = int(user_dict.get("hard_solved") or 0)
    
    img_path = None
    try:
        img_path = make_stats_graph_image(target.first_name, easy_c, med_c, hard_c, current_level, rem_exp, exp_per_lvl)
    except Exception as e:
        print(f"[make_stats_graph_image Error]: {e}")

    return caption_html, buttons, slider, img_path


@Client.on_message(filters.command(["stats", "stat", "mystats", "score"], prefixes=VALID_PREFIXES))
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
    caption, buttons, slider, img_path = get_stats_content_and_image(target, u)
    await send_jumble_rich(client, message.chat.id, caption, buttons, slider_row=slider, photo=img_path)


# ============================================================
# FILTERED LEADERBOARDS
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
    top_chart_list = []
    if rows:
        max_score = int(rows[0]["score"] or 1)
        for idx, r in enumerate(rows, start=1):
            name = str(r["name"] or "Player")[:10]
            sc = int(r["score"] or 0)
            top_chart_list.append({"name": name, "score": sc})
            display_name = name if r["is_private"] else f"<a href='tg://user?id={r['user_id']}'>{name}</a>"
            ratio = min(sc / max(max_score, 1), 1.0)
            bar = "█" * int(round(ratio * 7)) + "░" * (7 - int(round(ratio * 7)))
            lines.append(f"#{idx} {display_name:<10} <code>{bar}</code> ⭐<b>{sc}</b>")
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

    graph_img = None
    try:
        graph_img = make_leaderboard_graph_image(title_scope, period_titles.get(period, "All Time"), top_chart_list)
    except Exception as e:
        print(f"[make_leaderboard_graph_image Error]: {e}")

    return caption, buttons, graph_img


@Client.on_message(filters.command(["leaderboard", "lb", "top"], prefixes=VALID_PREFIXES))
async def leaderboard_cmd(client: Client, message: Message):
    caption, buttons, graph_img = build_leaderboard_card("global", "all", message.chat.id)
    await send_jumble_rich(client, message.chat.id, caption, buttons, photo=graph_img)


@Client.on_callback_query(filters.regex(r"^lb_view"))
async def lb_view_callback(client: Client, query: CallbackQuery):
    data = query.data.split("|")
    scope = data[1]
    period = data[2]
    chat_id = int(data[3]) if len(data) > 3 and data[3].lstrip("-").isdigit() else query.message.chat.id

    caption, buttons, graph_img = build_leaderboard_card(scope, period, chat_id)
    await query.answer()

    # Smooth Rich Card Transition: Purana delete karke fresh rich with updated photo drop karein
    try:
        await query.message.delete()
    except Exception:
        pass
    await send_jumble_rich(client, query.message.chat.id, caption, buttons, photo=graph_img)


@Client.on_callback_query(filters.regex(r"^refresh_leaderboard"))
async def refresh_lb_callback(client: Client, query: CallbackQuery):
    caption, buttons, graph_img = build_leaderboard_card("global", "all", query.message.chat.id)
    await query.answer()
    try:
        await query.message.delete()
    except Exception:
        pass
    await send_jumble_rich(client, query.message.chat.id, caption, buttons, photo=graph_img)


@Client.on_callback_query(filters.regex(r"^show_my_stats"))
async def show_my_stats_callback(client: Client, query: CallbackQuery):
    ensure_user(query.from_user)
    u = get_user(query.from_user.id)
    caption, buttons, slider, img_path = get_stats_content_and_image(query.from_user, u)
    await query.answer()
    try:
        await query.message.delete()
    except Exception:
        pass
    await send_jumble_rich(client, query.message.chat.id, caption, buttons, slider_row=slider, photo=img_path)


# ============================================================
# CALCULATOR COMMAND ENGINE (/calculate 25*4, /calc, /math)
# ============================================================

@Client.on_message(filters.command(["calculate", "calc", "math"], prefixes=VALID_PREFIXES))
async def calculate_cmd(client: Client, message: Message):
    if len(message.command) < 2:
        return await message.reply_text(
            "<blockquote>🧮 <b>CALCULATOR USAGE</b>\n\n"
            "Format: <code>/calculate [math expression]</code>\n"
            "Example: <code>/calculate (25 * 4) + 50</code></blockquote>",
            parse_mode=enums.ParseMode.HTML
        )

    raw_expr = message.text.split(None, 1)[1].strip()
    
    # Validation
    allowed_chars = set("0123456789+-*/(). %^")
    if not all(c in allowed_chars for c in raw_expr):
        return await message.reply_text("❌ Sirf basic mathematical operations allowed hain!")

    eval_expr = raw_expr.replace("^", "**")
    try:
        result = eval(eval_expr, {"__builtins__": None}, {})
        ans_text = (
            "<blockquote>🧮 <u><b>CALCULATOR RESULT</b></u></blockquote>\n\n"
            f"<blockquote>📝 <b>Expression :</b> <code>{raw_expr}</code>\n"
            f"✅ <b>Answer :</b> <code>{result}</code></blockquote>"
        )
        await send_jumble_rich(client, message.chat.id, ans_text)
    except Exception as e:
        await message.reply_text(f"❌ Calculation Error: <code>{e}</code>", parse_mode=enums.ParseMode.HTML)

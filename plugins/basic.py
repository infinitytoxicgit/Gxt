import time
from datetime import datetime
from pyrogram import Client, filters, enums, types
from pyrogram.types import Message, CallbackQuery
from database import DB, ensure_user, get_user, get_settings, set_settings, is_admin, get_top_players, get_global_config
from helpers import get_mention, is_admin_or_owner
from utils.rich import send_jumble_rich, make_exp_slider_row, html_to_rich_blocks


async def resolve_target_user(client: Client, message: Message):
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user
    if len(message.command) > 1:
        arg = message.command[1]
        try:
            return await client.get_users(int(arg) if arg.isdigit() else arg)
        except Exception:
            return None
    if message.entities:
        for entity in message.entities:
            if entity.type.name == "TEXT_MENTION" and entity.user:
                return entity.user
    return message.from_user


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

    mention = get_mention(target)
    priv_status = "🔒 Private" if user_dict.get("is_private") else "🌐 Public"
    points_val = user_dict.get("stars", 0) if user_dict.get("stars", 0) > 0 else user_dict.get("points", 0)

    # Active boosters visual bars
    now = time.time()
    rows = DB.execute("SELECT power_type, expires_at FROM user_powers WHERE user_id=? AND expires_at > ?", (target.id, now)).fetchall()
    powers_map = {r["power_type"]: r["expires_at"] for r in rows}

    active_boosters_text = ""
    if powers_map:
        booster_items = []
        for p_name, exp_ts in powers_map.items():
            left_mins = int((exp_ts - now) // 60)
            tag = "⭐ 2x Stars" if p_name == "2x_stars" else "⚡ 2x EXP"
            # Green if > 15m, Red if <= 15m
            bar_color = "🟢" if left_mins > 15 else "🔴"
            booster_items.append(f"{bar_color} <b>{tag}:</b> <code>{left_mins}m left</code>")
        active_boosters_text = "\n\n<blockquote>" + "\n".join(booster_items) + "</blockquote>"

    caption_html = (
        "<blockquote>👤 <u><b>PLAYER PROFILE & STATS</b></u>\n\n"
        f"👤 <b>Player :</b> {mention} (<code>{target.id}</code>)\n"
        f"🎖️ <b>Rank :</b> Level {current_level} ({rem_exp}/{exp_per_lvl} EXP)\n"
        f"⭐ <b>Points / Stars :</b> <code>{points_val}</code>\n"
        f"🔥 <b>Streak :</b> <code>{user_dict.get('streak', 0)}</code> (Best: {user_dict.get('best_streak', 0)})\n"
        f"🛡️ <b>Privacy :</b> <code>{priv_status}</code>\n\n"
        f"🧩 <b>Puzzles Solved :</b> <code>{user_dict.get('solved', 0)}</code>\n"
        f"• 🟢 Easy: <code>{user_dict.get('easy_solved', 0)}</code> | 🟡 Med: <code>{user_dict.get('medium_solved', 0)}</code> | 🔴 Hard: <code>{user_dict.get('hard_solved', 0)}</code>\n\n"
        f"⚔️ <b>Jumble Fight :</b> <code>{user_dict.get('fight_wins', 0)}W - {user_dict.get('fight_losses', 0)}L</code> ({winrate:.1f}%)\n"
        f"💰 <b>Bet Fight :</b> <code>{user_dict.get('bet_wins', 0)}W - {user_dict.get('bet_losses', 0)}L</code> ({bet_winrate:.1f}%)</blockquote>"
        f"{active_boosters_text}"
    )

    slider = make_exp_slider_row(rem_exp, exp_per_lvl)
    buttons = [
        [
            types.RichMessageButton(
                text="🛍️ Power Shop",
                style=enums.ButtonStyle.SUCCESS,
                callback_data=f"buy_shop|menu|{target.id}",
            ),
            types.RichMessageButton(
                text="📊 Top Graph",
                style=enums.ButtonStyle.PRIMARY,
                callback_data="refresh_leaderboard",
            ),
        ]
    ]
    return caption_html, buttons, slider


def get_leaderboard_content():
    top_users = get_top_players(limit=5)
    if not top_users:
        return "<blockquote>📊 No players recorded in leaderboard yet.</blockquote>", []

    max_score = top_users[0]["stars"] if top_users[0]["stars"] > 0 else 1
    graph_lines = []
    for idx, u in enumerate(top_users, start=1):
        u_dict = dict(u)
        name = (u_dict.get("name") or f"Player {idx}")[:10]
        stars = u_dict.get("stars", 0)
        ratio = min(stars / max_score, 1.0)
        filled = int(round(ratio * 8))
        bar = "█" * filled + "░" * (8 - filled)
        graph_lines.append(f"#{idx} {name:<10} {bar} ⭐{stars}")

    chart_body = "\n".join(graph_lines)
    caption = (
        "<blockquote>📊 <u><b>JUMBLE LEADERBOARD GRAPH</b></u>\n\n"
        "<b>Performance Chart :</b>\n"
        f"<code>{chart_body}</code>\n\n"
        "🎖️ <b>Formula :</b> 1 Level = Configured EXP\n"
        "⚡ <b>Boosters :</b> 2x Multipliers affect solves in real-time</blockquote>"
    )

    buttons = [
        [
            types.RichMessageButton(
                text="👤 My Profile",
                style=enums.ButtonStyle.SUCCESS,
                callback_data="show_my_stats",
            ),
            types.RichMessageButton(
                text="🔄 Refresh",
                style=enums.ButtonStyle.PRIMARY,
                callback_data="refresh_leaderboard",
            ),
        ]
    ]
    return caption, buttons


# 1. /stats
@Client.on_message(filters.command(["stats", "stat", "mystats", "score"]))
async def stats_cmd(client: Client, message: Message):
    target = await resolve_target_user(client, message)
    if not target:
        return await message.reply_text("❌ User nahi mila.")

    ensure_user(target)
    u = get_user(target.id)
    if not u:
        return await message.reply_text("❌ Is user ka koi database record nahi hai.")

    caption_html, buttons, slider = get_stats_content(target, u)
    await send_jumble_rich(client, message.chat.id, caption_html, buttons, slider_row=slider)


# 2. /leaderboard
@Client.on_message(filters.command(["leaderboard", "lb", "top"]))
async def leaderboard_cmd(client: Client, message: Message):
    caption, buttons = get_leaderboard_content()
    await send_jumble_rich(client, message.chat.id, caption, buttons)


# 3. /daily & /bonus
@Client.on_message(filters.command(["daily", "bonus"]))
async def daily_bonus_handler(client: Client, message: Message):
    user_id = message.from_user.id
    ensure_user(message.from_user)

    row = DB.execute("SELECT stars, last_daily, exp FROM users WHERE user_id=?", (user_id,)).fetchone()
    u_dict = dict(row) if row else {}
    now_ts = datetime.utcnow().timestamp()
    last_daily = u_dict.get("last_daily", 0)

    if last_daily and (now_ts - last_daily) < 86400:
        rem_sec = int(86400 - (now_ts - last_daily))
        h, m = divmod(rem_sec // 60, 60)
        return await message.reply_text(f"⏳ **Already claimed!** Return in `{h}h {m}m`.")

    bonus_reward = int(get_global_config("daily_bonus", 100))
    DB.execute("UPDATE users SET stars = stars + ?, points = points + ?, last_daily = ? WHERE user_id = ?", (bonus_reward, bonus_reward, now_ts, user_id))
    DB.commit()

    exp_per_lvl = int(get_global_config("exp_per_level", 500))
    curr_exp = (u_dict.get("exp", 0)) % exp_per_lvl
    caption = (
        "<blockquote>🎁 <u><b>DAILY BONUS CLAIMED</b></u>\n\n"
        f"🎀 <b>Reward :</b> +{bonus_reward} Stars / Points ⭐\n"
        f"👤 <b>Player :</b> {message.from_user.mention}\n"
        "⚡ Next reward unlocks in 24 Hours!</blockquote>"
    )

    slider = make_exp_slider_row(curr_exp, exp_per_lvl)
    buttons = [
        [
            types.RichMessageButton(
                text="🛍️ Visit Power Shop",
                style=enums.ButtonStyle.SUCCESS,
                callback_data=f"buy_shop|menu|{user_id}",
            )
        ]
    ]

    await send_jumble_rich(client, message.chat.id, caption, buttons, slider_row=slider)


# 4. /calculate & /audit
@Client.on_message(filters.command(["calculate", "audit"]))
async def calculate_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    ensure_user(message.from_user)

    row = DB.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    u_dict = dict(row) if row else {}
    stars = u_dict.get("stars", 0)
    easy_c = u_dict.get("easy_solved", 0)
    med_c = u_dict.get("medium_solved", 0)
    hard_c = u_dict.get("hard_solved", 0)

    caption = (
        "<blockquote>📊 <u><b>POINTS BREAKDOWN & AUDIT</b></u>\n\n"
        f"👤 <b>Player :</b> {message.from_user.mention} (<code>{user_id}</code>)\n\n"
        f"🟢 <b>Easy Solved :</b> {easy_c} × 10 = +{easy_c * 10} pts\n"
        f"🟡 <b>Medium Solved :</b> {med_c} × 20 = +{med_c * 20} pts\n"
        f"🔴 <b>Hard Solved :</b> {hard_c} × 30 = +{hard_c * 30} pts\n\n"
        f"⭐ <b>Net Wallet Balance :</b> <code>{stars} Stars/Points</code></blockquote>"
    )

    await send_jumble_rich(client, message.chat.id, caption)


# ============================================================
# OWNER & AUTH COMMANDS (/setlevel, /setexp, /setbonus, /setdaily)
# ============================================================

# Command: /setlevel 1000  (Sets 1 Level = 1000 EXP)
@Client.on_message(filters.command(["setlevel", "setlvl"]))
async def admin_set_level_exp(client: Client, message: Message):
    if not await is_admin_or_owner(message.chat, message.from_user.id):
        return await message.reply_text("❌ Only Owner/Admin can change EXP per level.")
    if len(message.command) < 2 or not message.command[1].isdigit():
        return await message.reply_text("ℹ️ **Usage:** `/setlevel [EXP_amount]` (e.g. `/setlevel 1000`)")

    val = int(message.command[1])
    DB.execute("INSERT OR REPLACE INTO bot_config(key, value) VALUES('exp_per_level', ?)", (val,))
    DB.commit()
    await message.reply_text(f"✅ Leveling updated! <b>1 Level = {val} EXP</b>", parse_mode=enums.ParseMode.HTML)


# Command: /setexp easy 50 OR /setexp 1000
@Client.on_message(filters.command("setexp"))
async def admin_set_exp_cmd(client: Client, message: Message):
    if not await is_admin_or_owner(message.chat, message.from_user.id):
        return await message.reply_text("❌ Only Owner/Admin can set EXP configs.")

    args = message.command
    if len(args) == 2 and args[1].isdigit():
        val = int(args[1])
        DB.execute("INSERT OR REPLACE INTO bot_config(key, value) VALUES('exp_per_level', ?)", (val,))
        DB.commit()
        return await message.reply_text(f"✅ Set 1 Level formula to `{val} EXP`!")

    if len(args) >= 3 and args[1].lower() in ["easy", "medium", "hard"] and args[2].isdigit():
        diff = args[1].lower()
        val = int(args[2])
        DB.execute(f"INSERT OR REPLACE INTO bot_config(key, value) VALUES('exp_{diff}', ?)", (val,))
        DB.commit()
        return await message.reply_text(f"✅ `{diff.title()}` reward set to: `+{val} EXP`!")

    return await message.reply_text("ℹ️ **Usage:** `/setexp 1000` OR `/setexp [easy/medium/hard] [EXP]`")


# Command: /setbonus 150 OR /setdaily 150
@Client.on_message(filters.command(["setbonus", "setdaily"]))
async def admin_set_daily_bonus(client: Client, message: Message):
    if not await is_admin_or_owner(message.chat, message.from_user.id):
        return await message.reply_text("❌ Only Owner/Admin can change daily bonus.")
    if len(message.command) < 2 or not message.command[1].isdigit():
        return await message.reply_text("ℹ️ **Usage:** `/setbonus [amount]` (e.g. `/setbonus 200`)")

    val = int(message.command[1])
    DB.execute("INSERT OR REPLACE INTO bot_config(key, value) VALUES('daily_bonus', ?)", (val,))
    DB.commit()
    await message.reply_text(f"✅ Daily Bonus updated to: `+{val} Stars/Points`!")


# ============================================================
# CALLBACKS FOR STATS & LEADERBOARD
# ============================================================

@Client.on_callback_query(filters.regex(r"^(refresh_leaderboard|show_my_stats)"))
async def basic_callbacks_handler(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    data = query.data

    if data == "refresh_leaderboard":
        caption, buttons = get_leaderboard_content()
        blocks = html_to_rich_blocks(caption)
        for r in buttons:
            blocks.append(types.InputRichBlockButtons(buttons=r))
        await query.answer("Leaderboard refreshed!")
        try:
            await query.message.edit_rich_message(rich_message=types.InputRichMessage(blocks=blocks))
        except Exception:
            pass

    elif data == "show_my_stats":
        ensure_user(query.from_user)
        u = get_user(user_id)
        caption, buttons, slider = get_stats_content(query.from_user, u)
        blocks = html_to_rich_blocks(caption)
        if slider:
            blocks.append(slider)
        for r in buttons:
            blocks.append(types.InputRichBlockButtons(buttons=r))
        await query.answer()
        try:
            await query.message.edit_rich_message(rich_message=types.InputRichMessage(blocks=blocks))
        except Exception:
            pass

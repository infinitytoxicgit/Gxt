from datetime import datetime, timedelta
from pyrogram import Client, filters, enums, types
from pyrogram.types import Message
from database import DB, ensure_user, get_user, get_settings, set_settings, is_admin, get_top_players
from helpers import get_mention, is_group
from utils.rich import send_jumble_rich, make_exp_slider_row


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


# 1. /stats command with Music-style Red Slider Bar
@Client.on_message(filters.command(["stats", "stat", "mystats", "score"]))
async def stats_cmd(client: Client, message: Message):
    target = await resolve_target_user(client, message)
    if not target:
        return await message.reply_text("❌ User nahi mila.")

    ensure_user(target)
    u = get_user(target.id)
    if not u:
        return await message.reply_text("❌ Is user ka koi database record nahi hai.")

    user_exp = u["exp"] if "exp" in u.keys() else 0
    current_level = (user_exp // 500) + 1
    rem_exp = user_exp % 500

    total_fights = (u["fight_wins"] or 0) + (u["fight_losses"] or 0)
    winrate = ((u["fight_wins"] / total_fights) * 100) if total_fights else 0
    total_bets = (u["bet_wins"] or 0) + (u["bet_losses"] or 0)
    bet_winrate = (((u["bet_wins"] or 0) / total_bets) * 100) if total_bets else 0

    mention = get_mention(target)
    priv_status = "🔒 Private" if u["is_private"] else "🌐 Public"
    points_val = u["stars"] if "stars" in u.keys() and u["stars"] > 0 else u["points"]

    caption_html = (
        "<blockquote><emoji id=5895705279416241926>👤</emoji> <u><b>PLAYER PROFILE & STATS</b></u></blockquote>\n\n"
        "<blockquote expandable>"
        f"<emoji id=5974235702701853774>👤</emoji> <b>Player :</b> {mention} (<code>{target.id}</code>)\n"
        f"<emoji id=6066395745139824604>🎖️</emoji> <b>Rank :</b> Level {current_level} ({rem_exp}/500 EXP)\n"
        f"⭐ <b>Points / Stars :</b> <code>{points_val}</code>\n"
        f"🔥 <b>Streak :</b> <code>{u['streak']}</code> (Best: {u['best_streak']})\n"
        f"🛡️ <b>Privacy :</b> <code>{priv_status}</code>\n\n"
        f"<emoji id=5409132617750555920>🧩</emoji> <b>Puzzles Solved :</b> <code>{u['solved']}</code>\n"
        f"• 🟢 Easy: <code>{u['easy_solved'] or 0}</code> | 🟡 Med: <code>{u['medium_solved'] or 0}</code> | 🔴 Hard: <code>{u['hard_solved'] or 0}</code>\n\n"
        f"⚔️ <b>Jumble Fight :</b> <code>{u['fight_wins']}W - {u['fight_losses']}L</code> ({winrate:.1f}%)\n"
        f"💰 <b>Bet Fight :</b> <code>{u['bet_wins']}W - {u['bet_losses']}L</code> ({bet_winrate:.1f}%)</blockquote>"
    )

    slider = make_exp_slider_row(rem_exp, 500)
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

    await send_jumble_rich(client, message.chat.id, caption_html, buttons, slider_row=slider)


# 2. /leaderboard with ASCII Graph & Red Slider
@Client.on_message(filters.command(["leaderboard", "lb", "top"]))
async def leaderboard_cmd(client: Client, message: Message):
    top_users = get_top_players(limit=5)
    if not top_users:
        return await message.reply_text("📊 No players recorded in leaderboard yet.")

    max_score = top_users[0]["stars"] if top_users[0]["stars"] > 0 else 1
    graph_lines = []
    for idx, u in enumerate(top_users, start=1):
        name = (u["name"] or f"Player {idx}")[:10]
        stars = u["stars"]
        ratio = min(stars / max_score, 1.0)
        filled = int(round(ratio * 8))
        bar = "█" * filled + "░" * (8 - filled)
        graph_lines.append(f"#{idx} {name:<10} {bar} ⭐{stars}")

    chart_body = "\n".join(graph_lines)
    caption = (
        "<blockquote><emoji id=5895705279416241926>📊</emoji> <u><b>JUMBLE LEADERBOARD GRAPH</b></u></blockquote>\n\n"
        "<blockquote expandable>"
        "<b>Performance Chart :</b>\n"
        f"<code>{chart_body}</code>\n\n"
        "<emoji id=6066395745139824604>🎖️</emoji> <b>Formula :</b> 1 Level = 500 EXP\n"
        "<emoji id=5409132617750555920>⚡</emoji> <b>Boosters :</b> Multipliers affect solves in real-time</blockquote>"
    )

    buttons = [
        [
            types.RichMessageButton(
                text="👤 My Profile",
                style=enums.ButtonStyle.SUCCESS,
                callback_data=f"show_my_stats|{message.from_user.id}",
            ),
            types.RichMessageButton(
                text="🔄 Refresh",
                style=enums.ButtonStyle.PRIMARY,
                callback_data="refresh_leaderboard",
            ),
        ]
    ]

    await send_jumble_rich(client, message.chat.id, caption, buttons)


# 3. /settings with Toggle Buttons
@Client.on_message(filters.command(["settings", "setting", "jumblesettings"]))
async def settings_cmd(client: Client, message: Message):
    chat_id = message.chat.id
    settings = get_settings(chat_id)

    status = "🟢 Running" if settings.get("is_active", True) else "🔴 Stopped"
    auto_del = "Enabled" if settings.get("auto_delete", False) else "Disabled"
    diff = settings.get("default_diff", "easy").title()
    easy_t = settings.get("easy", 120)
    med_t = settings.get("medium", 300)
    hard_t = settings.get("hard", 600)

    caption = (
        "<blockquote><emoji id=5895705279416241926>⚙️</emoji> <u><b>𝐉ᴜᴍʙʟᴇ 𝐆ʀᴏᴜᴘ 𝐒ᴇᴛᴛɪɴɢs</b></u></blockquote>\n\n"
        "<blockquote expandable>"
        f"<b>Status :</b> {status}\n"
        f"🗑️ <b>Auto Delete :</b> {auto_del}\n"
        f"🎯 <b>Mode :</b> {diff}\n"
        f"⏱️ <b>Timers :</b> Easy: {easy_t}s | Med: {med_t}s | Hard: {hard_t}s</blockquote>"
    )

    buttons = [
        [
            types.RichMessageButton(
                text="🔄 Toggle Game State",
                style=enums.ButtonStyle.PRIMARY,
                callback_data=f"toggle_game|{chat_id}",
            ),
            types.RichMessageButton(
                text="🗑️ Toggle Auto-Del",
                style=enums.ButtonStyle.DANGER,
                callback_data=f"toggle_autodel|{chat_id}",
            ),
        ],
        [
            types.RichMessageButton(
                text="🎯 Change Difficulty",
                style=enums.ButtonStyle.SUCCESS,
                callback_data=f"change_diff|{chat_id}",
            )
        ],
    ]

    await send_jumble_rich(client, chat_id, caption, buttons)


# 4. /daily & /bonus with Red Slider
@Client.on_message(filters.command(["daily", "bonus"]))
async def daily_bonus_handler(client: Client, message: Message):
    user_id = message.from_user.id
    ensure_user(message.from_user)

    row = DB.execute("SELECT stars, last_daily, exp FROM users WHERE user_id=?", (user_id,)).fetchone()
    now_ts = datetime.utcnow().timestamp()
    last_daily = row["last_daily"] if row and "last_daily" in row.keys() else 0

    if last_daily and (now_ts - last_daily) < 86400:
        rem_sec = int(86400 - (now_ts - last_daily))
        h, m = divmod(rem_sec // 60, 60)
        return await message.reply_text(f"⏳ **Already claimed!** Return in `{h}h {m}m`.")

    DB.execute("UPDATE users SET stars = stars + 100, points = points + 100, last_daily = ? WHERE user_id = ?", (now_ts, user_id))
    DB.commit()

    curr_exp = (row["exp"] if row and "exp" in row.keys() else 0) % 500
    caption = (
        "<blockquote><emoji id=5895705279416241926>🎁</emoji> <u><b>DAILY BONUS CLAIMED</b></u></blockquote>\n\n"
        "<blockquote expandable>"
        "<emoji id=6066395745139824604>🎀</emoji> <b>Reward :</b> +100 Stars / Points ⭐\n"
        f"<emoji id=5974235702701853774>👤</emoji> <b>Player :</b> {message.from_user.mention}\n"
        "<emoji id=5409132617750555920>⚡</emoji> Next reward unlocks in 24 Hours!</blockquote>"
    )

    slider = make_exp_slider_row(curr_exp, 500)
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


# 5. /calculate & /audit
@Client.on_message(filters.command(["calculate", "audit"]))
async def calculate_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    ensure_user(message.from_user)

    row = DB.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    stars = row["stars"] if row and "stars" in row.keys() else 0
    easy_c = row["easy_solved"] if row and "easy_solved" in row.keys() else 0
    med_c = row["medium_solved"] if row and "medium_solved" in row.keys() else 0
    hard_c = row["hard_solved"] if row and "hard_solved" in row.keys() else 0

    caption = (
        "<blockquote><emoji id=5895705279416241926>📊</emoji> <u><b>POINTS BREAKDOWN & AUDIT</b></u></blockquote>\n\n"
        "<blockquote expandable>"
        f"👤 <b>Player :</b> {message.from_user.mention} (<code>{user_id}</code>)\n\n"
        f"🟢 <b>Easy Solved :</b> {easy_c} × 10 = +{easy_c * 10} pts\n"
        f"🟡 <b>Medium Solved :</b> {med_c} × 20 = +{med_c * 20} pts\n"
        f"🔴 <b>Hard Solved :</b> {hard_c} × 30 = +{hard_c * 30} pts\n\n"
        f"⭐ <b>Net Wallet Balance :</b> <code>{stars} Stars/Points</code></blockquote>"
    )

    await send_jumble_rich(client, message.chat.id, caption)


# 6. Admin Settings (/sethint, /setpoints, /setimer)
@Client.on_message(filters.command(["sethint", "setpoints", "setimer", "settimer"]))
async def admin_set_configs(client: Client, message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return await message.reply_text("❌ Only Authorized Admins can change settings.")

    args = message.command
    if len(args) < 3:
        return await message.reply_text(f"ℹ️ **Usage:** `/{args[0]} [easy/medium/hard] [value]`")

    diff = args[1].lower()
    if diff not in ["easy", "medium", "hard"]:
        return await message.reply_text("❌ Difficulty must be: `easy`, `medium`, or `hard`.")

    try:
        val = int(args[2])
    except ValueError:
        return await message.reply_text("❌ Value number hona chahiye.")

    cmd = args[0].lower()
    if cmd == "sethint":
        DB.execute(f"INSERT OR REPLACE INTO bot_config(key, value) VALUES('hints_{diff}', ?)", (val,))
        DB.commit()
        return await message.reply_text(f"✅ `{diff.title()}` hints set to: `{val}`")
    elif cmd == "setpoints":
        DB.execute(f"INSERT OR REPLACE INTO bot_config(key, value) VALUES('points_{diff}', ?)", (val,))
        DB.commit()
        return await message.reply_text(f"✅ `{diff.title()}` points reward set to: `{val}`")
    elif cmd in ["setimer", "settimer"]:
        set_settings(message.chat.id, diff, val)
        return await message.reply_text(f"✅ `{diff.title()}` round timer set to: `{val}s`")

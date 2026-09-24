from datetime import datetime
from pyrogram import Client, filters, enums, types
from pyrogram.types import Message, CallbackQuery
from database import DB, ensure_user, get_user, get_settings, set_settings, is_admin, get_top_players
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
    user_exp = user_dict.get("exp", 0)
    current_level = (user_exp // 500) + 1
    rem_exp = user_exp % 500

    total_fights = (user_dict.get("fight_wins") or 0) + (user_dict.get("fight_losses") or 0)
    winrate = ((user_dict.get("fight_wins", 0) / total_fights) * 100) if total_fights else 0
    total_bets = (user_dict.get("bet_wins") or 0) + (user_dict.get("bet_losses") or 0)
    bet_winrate = (((user_dict.get("bet_wins") or 0) / total_bets) * 100) if total_bets else 0

    mention = get_mention(target)
    priv_status = "🔒 Private" if user_dict.get("is_private") else "🌐 Public"
    points_val = user_dict.get("stars", 0) if user_dict.get("stars", 0) > 0 else user_dict.get("points", 0)

    caption_html = (
        "<blockquote>👤 <u><b>PLAYER PROFILE & STATS</b></u>\n\n"
        f"👤 <b>Player :</b> {mention} (<code>{target.id}</code>)\n"
        f"🎖️ <b>Rank :</b> Level {current_level} ({rem_exp}/500 EXP)\n"
        f"⭐ <b>Points / Stars :</b> <code>{points_val}</code>\n"
        f"🔥 <b>Streak :</b> <code>{user_dict.get('streak', 0)}</code> (Best: {user_dict.get('best_streak', 0)})\n"
        f"🛡️ <b>Privacy :</b> <code>{priv_status}</code>\n\n"
        f"🧩 <b>Puzzles Solved :</b> <code>{user_dict.get('solved', 0)}</code>\n"
        f"• 🟢 Easy: <code>{user_dict.get('easy_solved', 0)}</code> | 🟡 Med: <code>{user_dict.get('medium_solved', 0)}</code> | 🔴 Hard: <code>{user_dict.get('hard_solved', 0)}</code>\n\n"
        f"⚔️ <b>Jumble Fight :</b> <code>{user_dict.get('fight_wins', 0)}W - {user_dict.get('fight_losses', 0)}L</code> ({winrate:.1f}%)\n"
        f"💰 <b>Bet Fight :</b> <code>{user_dict.get('bet_wins', 0)}W - {user_dict.get('bet_losses', 0)}L</code> ({bet_winrate:.1f}%)</blockquote>"
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
        "🎖️ <b>Formula :</b> 1 Level = 500 EXP\n"
        "⚡ <b>Boosters :</b> Multipliers affect solves in real-time</blockquote>"
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


# 1. /stats command
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


# 3. /settings (Importing Panel logic from settings plugin)
@Client.on_message(filters.command(["settings", "setting", "jumblesettings"]))
async def settings_cmd(client: Client, message: Message):
    if not await is_admin_or_owner(message.chat, message.from_user.id):
        return await message.reply_text("❌ Sirf group admins hi settings access kar sakte hain.")

    try:
        from plugins.settings import build_settings_card
        caption, buttons = build_settings_card(message.chat.id, message.chat.title or "Group")
        await send_jumble_rich(client, message.chat.id, caption, buttons)
    except Exception as e:
        await message.reply_text(f"❌ Error loading settings: {e}")


# 4. /daily & /bonus
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

    DB.execute("UPDATE users SET stars = stars + 100, points = points + 100, last_daily = ? WHERE user_id = ?", (now_ts, user_id))
    DB.commit()

    curr_exp = (u_dict.get("exp", 0)) % 500
    caption = (
        "<blockquote>🎁 <u><b>DAILY BONUS CLAIMED</b></u>\n\n"
        "🎀 <b>Reward :</b> +100 Stars / Points ⭐\n"
        f"👤 <b>Player :</b> {message.from_user.mention}\n"
        "⚡ Next reward unlocks in 24 Hours!</blockquote>"
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


# 6. Admin Settings via Text Command
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


# ============================================================
# CALLBACKS FOR STATS, LEADERBOARD, POWER SHOP
# ============================================================

@Client.on_callback_query(filters.regex(r"^(refresh_leaderboard|show_my_stats|buy_shop)"))
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

    elif data.startswith("buy_shop"):
        await query.answer("🛍️ Power Shop jald hi live hoga!", show_alert=True)

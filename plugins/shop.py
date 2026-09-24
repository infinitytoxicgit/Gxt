import time
from pyrogram import Client, filters, enums, types
from pyrogram.types import CallbackQuery, Message
from database import DB, ensure_user, get_user, get_global_config
from helpers import get_mention, is_admin_or_owner
from utils.rich import send_jumble_rich, html_to_rich_blocks

def get_active_powers(user_id: int):
    now = time.time()
    rows = DB.execute("SELECT power_type, expires_at FROM user_powers WHERE user_id=? AND expires_at > ?", (user_id, now)).fetchall()
    return {r["power_type"]: r["expires_at"] for r in rows}

def format_power_bar(remaining_secs: float, total_duration: float = 3600):
    if remaining_secs <= 0:
        return "🔴 Expired"
    ratio = min(max(remaining_secs / total_duration, 0.0), 1.0)
    filled = int(round(ratio * 8))
    empty = 8 - filled
    mins = int(remaining_secs // 60)
    # Green progress if > 25%, Red progress if <= 25%
    color_bar = "🟩" * filled + "⬜" * empty if ratio > 0.25 else "🟥" * filled + "⬜" * empty
    return f"{color_bar} ({mins}m left)"

def build_shop_card(user_id: int, user_obj):
    u = get_user(user_id)
    u_dict = dict(u) if u else {}
    stars = u_dict.get("stars", 0) if u_dict.get("stars", 0) > 0 else u_dict.get("points", 0)

    p_stars_cost = int(get_global_config("shop_stars2x_price", 200))
    p_stars_dur = int(get_global_config("shop_stars2x_duration", 3600)) // 60

    p_exp_cost = int(get_global_config("shop_exp2x_price", 250))
    p_exp_dur = int(get_global_config("shop_exp2x_duration", 3600)) // 60

    active_powers = get_active_powers(user_id)
    now = time.time()

    stars_status = format_power_bar(active_powers["2x_stars"] - now, p_stars_dur * 60) if "2x_stars" in active_powers else "🔴 Inactive"
    exp_status = format_power_bar(active_powers["2x_exp"] - now, p_exp_dur * 60) if "2x_exp" in active_powers else "🔴 Inactive"

    caption = (
        "<blockquote>🛍️ <u><b>𝐉𝐔𝐌𝐁𝐋𝐄 𝐏𝐎𝐖𝐄𝐑 𝐒𝐇𝐎𝐏</b></u></blockquote>\n\n"
        f"👤 <b>Player :</b> {get_mention(user_obj)}\n"
        f"⭐ <b>Wallet Balance :</b> <code>{stars} Stars/Points</code>\n\n"
        "<blockquote>⚡ <b>ACTIVE BOOSTERS :</b>\n"
        f"⭐ <b>2x Stars Booster :</b> {stars_status}\n"
        f"⚡ <b>2x EXP Booster :</b> {exp_status}</blockquote>\n\n"
        "<i>Tap a card below to buy or rebuy to extend booster duration!</i>"
    )

    buttons = [
        [
            types.RichMessageButton(
                text=f"⭐ 2x Stars ({p_stars_cost}⭐ / {p_stars_dur}m)",
                style=enums.ButtonStyle.SUCCESS if "2x_stars" in active_powers else enums.ButtonStyle.PRIMARY,
                callback_data=f"buy_power|2x_stars|{user_id}",
            ),
        ],
        [
            types.RichMessageButton(
                text=f"⚡ 2x EXP ({p_exp_cost}⭐ / {p_exp_dur}m)",
                style=enums.ButtonStyle.SUCCESS if "2x_exp" in active_powers else enums.ButtonStyle.PRIMARY,
                callback_data=f"buy_power|2x_exp|{user_id}",
            ),
        ],
        [
            types.RichMessageButton(
                text="🔄 Refresh Shop",
                style=enums.ButtonStyle.PRIMARY,
                callback_data=f"shop_refresh|{user_id}",
            ),
            types.RichMessageButton(
                text="❌ Close",
                style=enums.ButtonStyle.DANGER,
                callback_data="shop_close",
            ),
        ]
    ]
    return caption, buttons


@Client.on_callback_query(filters.regex(r"^(buy_shop|buy_power|shop_refresh|shop_close)"))
async def shop_callback_handler(client: Client, query: CallbackQuery):
    data = query.data.split("|")
    action = data[0]
    user_id = query.from_user.id

    if action in ["buy_shop", "shop_refresh"]:
        target_id = int(data[2]) if len(data) > 2 else user_id
        if target_id != user_id:
            return await query.answer("❌ Yeh aapka shop session nahi hai!", show_alert=True)
        caption, buttons = build_shop_card(user_id, query.from_user)
        blocks = html_to_rich_blocks(caption)
        for r in buttons:
            blocks.append(types.InputRichBlockButtons(buttons=r))
        await query.answer()
        return await query.message.edit_rich_message(rich_message=types.InputRichMessage(blocks=blocks))

    elif action == "buy_power":
        power_type = data[1]
        target_id = int(data[2])
        if target_id != user_id:
            return await query.answer("❌ Only the player can purchase!", show_alert=True)

        price_key = "shop_stars2x_price" if power_type == "2x_stars" else "shop_exp2x_price"
        dur_key = "shop_stars2x_duration" if power_type == "2x_stars" else "shop_exp2x_duration"
        cost = int(get_global_config(price_key, 200))
        duration = int(get_global_config(dur_key, 3600))

        u = get_user(user_id)
        u_dict = dict(u) if u else {}
        balance = u_dict.get("stars", 0) if u_dict.get("stars", 0) > 0 else u_dict.get("points", 0)

        if balance < cost:
            return await query.answer(f"❌ Low balance! You need {cost} Stars/Points.", show_alert=True)

        # Deduct wallet
        DB.execute("UPDATE users SET stars = MAX(0, stars - ?), points = MAX(0, points - ?) WHERE user_id = ?", (cost, cost, user_id))

        now = time.time()
        # If already active, stack the duration (Rebuy feature)
        existing = DB.execute("SELECT expires_at FROM user_powers WHERE user_id=? AND power_type=?", (user_id, power_type)).fetchone()
        new_expires = (max(existing["expires_at"], now) + duration) if (existing and existing["expires_at"] > now) else (now + duration)

        DB.execute("""
            INSERT INTO user_powers(user_id, power_type, expires_at) VALUES(?, ?, ?)
            ON CONFLICT(user_id, power_type) DO UPDATE SET expires_at=excluded.expires_at
        """, (user_id, power_type, new_expires))
        DB.commit()

        await query.answer(f"✅ Booster Activated! Added {duration // 60}m duration.", show_alert=True)

        caption, buttons = build_shop_card(user_id, query.from_user)
        blocks = html_to_rich_blocks(caption)
        for r in buttons:
            blocks.append(types.InputRichBlockButtons(buttons=r))
        return await query.message.edit_rich_message(rich_message=types.InputRichMessage(blocks=blocks))

    elif action == "shop_close":
        await query.message.delete()
        return await query.answer("Closed!")


# Admin Commands to set Power Shop Prices and Durations
# Usage: /setshopprice stars 300
@Client.on_message(filters.command(["setshopprice", "setpowerprice"]))
async def set_power_price_cmd(client: Client, message: Message):
    if not await is_admin_or_owner(message.chat, message.from_user.id):
        return await message.reply_text("❌ Only Owner/Admin can change shop pricing.")
    if len(message.command) < 3:
        return await message.reply_text("ℹ️ **Usage:** `/setshopprice [stars/exp] [price]`")

    item = message.command[1].lower()
    try:
        val = int(message.command[2])
    except ValueError:
        return await message.reply_text("❌ Price must be integer.")

    key = "shop_stars2x_price" if "star" in item else "shop_exp2x_price"
    DB.execute("INSERT OR REPLACE INTO bot_config(key, value) VALUES(?, ?)", (key, val))
    DB.commit()
    await message.reply_text(f"✅ `{item.title()}` 2x Booster price set to `{val}` Stars!")


# Usage: /setpowerdur stars 60 (in minutes)
@Client.on_message(filters.command(["setpowerdur", "setshoptimer"]))
async def set_power_duration_cmd(client: Client, message: Message):
    if not await is_admin_or_owner(message.chat, message.from_user.id):
        return await message.reply_text("❌ Only Owner/Admin can change shop durations.")
    if len(message.command) < 3:
        return await message.reply_text("ℹ️ **Usage:** `/setpowerdur [stars/exp] [minutes]`")

    item = message.command[1].lower()
    try:
        mins = int(message.command[2])
    except ValueError:
        return await message.reply_text("❌ Duration must be integer minutes.")

    key = "shop_stars2x_duration" if "star" in item else "shop_exp2x_duration"
    DB.execute("INSERT OR REPLACE INTO bot_config(key, value) VALUES(?, ?)", (key, mins * 60))
    DB.commit()
    await message.reply_text(f"✅ `{item.title()}` 2x Booster validity set to `{mins}` minutes!")

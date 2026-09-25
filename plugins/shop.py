import time
from pyrogram import Client, filters, enums, types
from pyrogram.types import CallbackQuery, Message
from database import DB, ensure_user, get_user, get_global_config
from helpers import get_mention
from utils.rich import send_jumble_rich, edit_jumble_rich

# Ensure user_powers table exists
try:
    DB.execute("""
        CREATE TABLE IF NOT EXISTS user_powers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            power_type TEXT NOT NULL,
            expires_at REAL NOT NULL,
            UNIQUE(user_id, power_type)
        )
    """)
    DB.commit()
except Exception as e:
    print(f"[User Powers Init Error]: {e}")


def get_active_powers(user_id: int):
    now = time.time()
    try:
        rows = DB.execute("SELECT power_type, expires_at FROM user_powers WHERE user_id=? AND expires_at > ?", (user_id, now)).fetchall()
        return {r["power_type"]: r["expires_at"] for r in rows}
    except Exception:
        return {}


def format_power_bar(remaining_secs: float, total_duration: float = 3600):
    if remaining_secs <= 0:
        return "🔴 Expired"
    ratio = min(max(remaining_secs / total_duration, 0.0), 1.0)
    filled = int(round(ratio * 8))
    empty = 8 - filled
    mins = int(remaining_secs // 60)
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
        "<blockquote><i>Tap below to purchase or rebuy to stack booster validity!</i></blockquote>"
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


async def update_shop_rich_view(client: Client, chat_id: int, message_id: int, caption: str, buttons: list):
    try:
        await edit_jumble_rich(client, chat_id, message_id, caption, buttons)
    except Exception:
        try:
            await client.delete_messages(chat_id, message_id)
        except Exception:
            pass
        await send_jumble_rich(client, chat_id, caption, buttons)


# /shop Command (Works in Groups & DMs)
@Client.on_message(filters.command(["shop", "powershop", "store"], prefixes=["/", "!", "."]))
async def open_shop_cmd(client: Client, message: Message):
    ensure_user(message.from_user)
    caption, buttons = build_shop_card(message.from_user.id, message.from_user)
    await send_jumble_rich(client, message.chat.id, caption, buttons)


@Client.on_callback_query(filters.regex(r"^(buy_shop|buy_power|shop_refresh|shop_close|open_shop_direct)"))
async def shop_callback_handler(client: Client, query: CallbackQuery):
    data = query.data.split("|")
    action = data[0]
    user_id = query.from_user.id

    if action in ["buy_shop", "shop_refresh", "open_shop_direct"]:
        ensure_user(query.from_user)
        caption, buttons = build_shop_card(user_id, query.from_user)
        await query.answer()
        return await update_shop_rich_view(client, query.message.chat.id, query.message.id, caption, buttons)

    elif action == "buy_power":
        power_type = data[1]
        price_key = "shop_stars2x_price" if power_type == "2x_stars" else "shop_exp2x_price"
        dur_key = "shop_stars2x_duration" if power_type == "2x_stars" else "shop_exp2x_duration"
        cost = int(get_global_config(price_key, 200))
        duration = int(get_global_config(dur_key, 3600))

        u = get_user(user_id)
        u_dict = dict(u) if u else {}
        balance = u_dict.get("stars", 0) if u_dict.get("stars", 0) > 0 else u_dict.get("points", 0)

        if balance < cost:
            return await query.answer(f"❌ Low balance! You need {cost} Stars/Points.", show_alert=True)

        DB.execute("UPDATE users SET stars = MAX(0, stars - ?), points = MAX(0, points - ?) WHERE user_id = ?", (cost, cost, user_id))

        now = time.time()
        existing = DB.execute("SELECT expires_at FROM user_powers WHERE user_id=? AND power_type=?", (user_id, power_type)).fetchone()
        new_expires = (max(existing["expires_at"], now) + duration) if (existing and existing["expires_at"] > now) else (now + duration)

        DB.execute("""
            INSERT INTO user_powers(user_id, power_type, expires_at) VALUES(?, ?, ?)
            ON CONFLICT(user_id, power_type) DO UPDATE SET expires_at=excluded.expires_at
        """, (user_id, power_type, new_expires))
        DB.commit()

        await query.answer(f"✅ Booster Activated! Added {duration // 60}m.", show_alert=True)[span_5](start_span)[span_5](end_span)
        caption, buttons = build_shop_card(user_id, query.from_user)
        return await update_shop_rich_view(client, query.message.chat.id, query.message.id, caption, buttons)

    elif action == "shop_close":
        await query.message.delete()
        return await query.answer("Closed!")

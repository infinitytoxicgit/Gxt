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
        return "🔴 <b>INACTIVE</b>"
    ratio = min(max(remaining_secs / total_duration, 0.0), 1.0)
    filled = int(round(ratio * 8))
    empty = 8 - filled
    mins = int(remaining_secs // 60)
    color_bar = "🟩" * filled + "⬜" * empty if ratio > 0.25 else "🟥" * filled + "⬜" * empty
    return f"{color_bar} (<code>{mins}m left</code>) 🟢 <b>ACTIVE</b>"


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

    has_stars_active = "2x_stars" in active_powers
    has_exp_active = "2x_exp" in active_powers

    stars_status = format_power_bar(active_powers["2x_stars"] - now, p_stars_dur * 60) if has_stars_active else "🔴 <i>Inactive</i>"
    exp_status = format_power_bar(active_powers["2x_exp"] - now, p_exp_dur * 60) if has_exp_active else "🔴 <i>Inactive</i>"

    caption = (
        "<blockquote>⚡ <u><b>JUMBLE POWER STORE & BOOSTERS</b></u></blockquote>\n\n"
        f"👤 <b>Player :</b> {get_mention(user_obj)}\n"
        f"⭐ <b>Wallet Balance :</b> <code>{stars} Stars/Points</code>\n\n"
        "<blockquote>🔥 <b>ACTIVE BUFFS & BOOSTERS :</b>\n"
        f"⭐ <b>2x Stars Buff :</b> {stars_status}\n"
        f"⚡ <b>2x EXP Buff :</b> {exp_status}</blockquote>\n\n"
        "<blockquote>💡 <i>Re-purchasing active boosters will stack validity time!</i></blockquote>"
    )

    buttons = [
        [
            types.RichMessageButton(
                text=f"{'🟢' if has_stars_active else '⭐'} 2x Stars ({p_stars_cost}⭐ / {p_stars_dur}m)",
                style=enums.ButtonStyle.SUCCESS if has_stars_active else enums.ButtonStyle.PRIMARY,
                callback_data=f"buy_power|2x_stars|{user_id}",
            ),
        ],
        [
            types.RichMessageButton(
                text=f"{'🟢' if has_exp_active else '⚡'} 2x EXP ({p_exp_cost}⭐ / {p_exp_dur}m)",
                style=enums.ButtonStyle.SUCCESS if has_exp_active else enums.ButtonStyle.PRIMARY,
                callback_data=f"buy_power|2x_exp|{user_id}",
            ),
        ],
        [
            types.RichMessageButton(
                text="🔄 Refresh",
                style=enums.ButtonStyle.PRIMARY,
                callback_data=f"shop_refresh|{user_id}",
            ),
            types.RichMessageButton(
                text="❌ Close",
                style=enums.ButtonStyle.DANGER,
                callback_data=f"shop_close|{user_id}",
            ),
        ]
    ]
    return caption, buttons


async def update_shop_rich_view(client: Client, chat_id: int, message_id: int, caption: str, buttons: list):
    try:
        await edit_jumble_rich(client, chat_id, message_id, caption, rich_buttons_rows=buttons)
    except Exception:
        try:
            await client.delete_messages(chat_id, message_id)
        except Exception:
            pass
        await send_jumble_rich(client, chat_id, caption, rich_buttons_rows=buttons)


# /shop Command (Works in Groups & DMs with high priority)
@Client.on_message(filters.command(["shop", "powershop", "store"], prefixes=["/", "!", "."]), group=-1)
async def open_shop_cmd(client: Client, message: Message):
    if not message.from_user:
        return
    ensure_user(message.from_user)
    caption, buttons = build_shop_card(message.from_user.id, message.from_user)
    await send_jumble_rich(client, message.chat.id, caption, rich_buttons_rows=buttons)


@Client.on_callback_query(filters.regex(r"^(buy_shop|buy_power|shop_refresh|shop_close|open_shop_direct)"))
async def shop_callback_handler(client: Client, query: CallbackQuery):
    data = query.data.split("|")
    action = data[0]
    owner_id = int(data[2]) if len(data) > 2 else query.from_user.id
    user_id = query.from_user.id

    # Group security: Only card owner can interact
    if user_id != owner_id and action != "open_shop_direct":
        return await query.answer("⚠️ Yeh shop panel aapka nahi hai! /shop use karein.", show_alert=True)

    if action in ["buy_shop", "shop_refresh", "open_shop_direct"]:
        ensure_user(query.from_user)
        caption, buttons = build_shop_card(user_id, query.from_user)
        await query.answer("🔄 Shop Refreshed!")
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

        await query.answer(f"✅ Booster Activated! Added {duration // 60}m validity.", show_alert=True)
        caption, buttons = build_shop_card(user_id, query.from_user)
        return await update_shop_rich_view(client, query.message.chat.id, query.message.id, caption, buttons)

    elif action == "shop_close":
        try:
            await query.message.delete()
        except Exception:
            pass
        return await query.answer("Closed!")

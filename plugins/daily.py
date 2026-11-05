from datetime import datetime, timedelta
from pyrogram import filters, enums, types
from main import app
from database import DB, ensure_user
from helpers import is_owner, is_authed
from utils.rich import send_jumble_rich

# Settings table banayein agar exist na kare
DB.execute("""
    CREATE TABLE IF NOT EXISTS bot_settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
""")
DB.commit()

def get_setting(key: str, default: str) -> str:
    row = DB.execute("SELECT value FROM bot_settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row and "value" in row.keys() else (row[0] if row else default)

def set_setting(key: str, value: str):
    DB.execute("INSERT OR REPLACE INTO bot_settings (key, value) VALUES (?, ?)", (key, str(value)))
    DB.commit()


# --- COMMAND: /setdaily (Only Owner / Authorized Admins) ---
@app.on_message(filters.command("setdaily"))
async def set_daily_amount_handler(client, message):
    user_id = message.from_user.id if message.from_user else 0
    if not (is_owner(user_id) or is_authed(user_id)):
        return await message.reply_text("❌ Only Owner/Authorized Admins can set daily bonus.")

    if len(message.command) < 2 or not message.command[1].isdigit():
        return await message.reply_text("⚠️ Usage: <code>/setdaily &lt;amount&gt;</code>\nExample: <code>/setdaily 5000</code>")

    amount = int(message.command[1])
    set_setting("daily_reward", str(amount))
    await message.reply_text(
        f"✅ <b>Daily Bonus Updated!</b>\nAmount: <code>+{amount} Stars/Points</code>",
        parse_mode=enums.ParseMode.HTML
    )


# --- COMMAND: /daily (Har 24 Ghante me 1 baar) ---
@app.on_message(filters.command("daily"))
async def daily_handler(client, message):
    user_id = message.from_user.id
    ensure_user(user_id, message.from_user.first_name)

    # Database se configured daily amount uthana (default 100)
    daily_amount = int(get_setting("daily_reward", "100"))

    row = DB.execute("SELECT stars, last_daily FROM users WHERE user_id=?", (user_id,)).fetchone()
    last_daily = row["last_daily"] if row and "last_daily" in row.keys() else None

    now = datetime.utcnow()
    if last_daily:
        try:
            last_time = datetime.fromisoformat(last_daily)
            if now - last_time < timedelta(hours=24):
                remaining = timedelta(hours=24) - (now - last_time)
                hours, remainder = divmod(int(remaining.total_seconds()), 3600)
                minutes, _ = divmod(remainder, 60)
                return await message.reply_text(f"⏳ **Already claimed!** Return in `{hours}h {minutes}m`.")
        except Exception:
            pass

    DB.execute(
        "UPDATE users SET stars = stars + ?, last_daily = ? WHERE user_id = ?",
        (daily_amount, now.isoformat(), user_id)
    )
    DB.commit()

    caption = (
        "<blockquote><emoji id=5895705279416241926>🎁</emoji> <u><b>DAILY BONUS REWARD</b></u></blockquote>\n\n"
        "<blockquote expandable>"
        f"<emoji id=6066395745139824604>🎀</emoji> <b>Claimed :</b> +{daily_amount} Stars ⭐\n"
        "<emoji id=5974235702701853774>👤</emoji> <b>Player :</b> {user}\n"
        "<emoji id=5409132617750555920>⚡</emoji> Come back in 24 hours for next bonus!</blockquote>"
    ).format(user=message.from_user.mention)

    buttons = [
        [
            types.RichMessageButton(
                text="🛍️ Open Shop",
                style=enums.ButtonStyle.SUCCESS,
                callback_data=f"buy_shop|menu|{user_id}",
            )
        ]
    ]

    await send_jumble_rich(client, message.chat.id, caption, buttons)

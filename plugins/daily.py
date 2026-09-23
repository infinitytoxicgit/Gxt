from datetime import datetime, timedelta
from pyrogram import filters, enums, types
from main import app
from database import DB, ensure_user
from utils.rich import send_jumble_rich


@app.on_message(filters.command(["daily", "bonus"]))
async def daily_bonus_handler(client, message):
    user_id = message.from_user.id
    ensure_user(user_id, message.from_user.first_name)

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

    DB.execute("UPDATE users SET stars = stars + 100, last_daily = ? WHERE user_id = ?", (now.isoformat(), user_id))
    DB.commit()

    caption = (
        "<blockquote><emoji id=5895705279416241926>🎁</emoji> <u><b>DAILY BONUS REWARD</b></u></blockquote>\n\n"
        "<blockquote expandable>"
        "<emoji id=6066395745139824604>🎀</emoji> <b>Claimed :</b> +100 Stars ⭐\n"
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

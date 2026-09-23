from datetime import datetime, timedelta
from pyrogram import filters, enums, types
from Gxt import app
from Gxt.utils.database import get_user_data, add_stars, set_claim_time
from Gxt.utils.rich import send_jumble_rich


@app.on_message(filters.command(["daily", "bonus"]))
async def daily_bonus_handler(client, message):
    user_id = message.from_user.id
    user = await get_user_data(user_id)
    last_claim = user.get("last_claim")

    now = datetime.utcnow()
    if last_claim and now - last_claim < timedelta(hours=24):
        remaining = timedelta(hours=24) - (now - last_claim)
        hours, remainder = divmod(int(remaining.total_seconds()), 3600)
        minutes, _ = divmod(remainder, 60)
        return await message.reply_text(f"⏳ **Already claimed!** Return in `{hours}h {minutes}m`.")

    await add_stars(user_id, 100)
    await set_claim_time(user_id, now)

    caption = (
        "<blockquote><emoji id=5895705279416241926>🎁</emoji> <u><b>DAILY BONUS REWARD</b></u></blockquote>\n\n"
        "<blockquote expandable>"
        "<emoji id=6066395745139824604>🎀</emoji> <b>Claimed :</b> +100 Stars ⭐\n"
        "<emoji id=5974235702701853774>👤</emoji> <b>Player :</b> {user}\n"
        "<emoji id=5409132617750555920>⚡</emoji> Claim reset in next 24 Hours!</blockquote>"
    ).format(user=message.from_user.mention)

    buttons = [
        [
            types.RichMessageButton(
                text="🛍️ Go To Shop",
                style=enums.ButtonStyle.SUCCESS,
                callback_data=f"open_shop|{user_id}",
            )
        ]
    ]

    await send_jumble_rich(client, message.chat.id, caption, buttons)

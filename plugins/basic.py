import html
import time
from config import START_IMG, SUPPORT_GC, ADD_ME_URL, MUSIC_BOT_URL
from database import DB, ensure_user, get_user
from helpers import get_mention, is_group, is_authed, is_owner
from pyrogram import Client, filters, enums, types
from pyrogram.types import Message
from utils.rich import send_jumble_rich


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


@Client.on_message(filters.command(["stats", "stat", "mystats", "score"]))
async def stats_cmd(client: Client, message: Message):
    target = await resolve_target_user(client, message)
    if not target:
        return await message.reply_text("❌ User nahi mila.")

    ensure_user(target)
    u = get_user(target.id)
    if not u:
        return await message.reply_text("❌ Is user ka koi database record nahi hai.")

    # EXP & Level Calculation (500 EXP per level)
    user_exp = u.get("exp", 0) if isinstance(u, dict) and "exp" in u else (u["exp"] if "exp" in u.keys() else 0)
    current_level = (user_exp // 500) + 1
    rem_exp = user_exp % 500
    bar_fill = int((rem_exp / 500) * 10)
    exp_bar = "█" * bar_fill + "░" * (10 - bar_fill)

    # Winrates & Fights
    total_fights = (u["fight_wins"] or 0) + (u["fight_losses"] or 0)
    winrate = ((u["fight_wins"] / total_fights) * 100) if total_fights else 0
    total_bets = (u["bet_wins"] or 0) + (u["bet_losses"] or 0)
    bet_winrate = (((u["bet_wins"] or 0) / total_bets) * 100) if total_bets else 0

    mention = get_mention(target)
    priv_status = "🔒 Private" if u["is_private"] else "🌐 Public"
    points_val = u.get("points", 0) if isinstance(u, dict) and "points" in u else u["points"]

    caption_html = (
        "<blockquote><emoji id=5895705279416241926>👤</emoji> <u><b>PLAYER PROFILE & STATS</b></u></blockquote>\n\n"
        "<blockquote expandable>"
        f"<emoji id=5974235702701853774>👤</emoji> <b>Player :</b> {mention} (<code>{target.id}</code>)\n"
        f"<emoji id=6066395745139824604>🎖️</emoji> <b>Rank :</b> Level {current_level} ({rem_exp}/500 EXP)\n"
        f"📊 <b>EXP Bar :</b> <code>[{exp_bar}]</code>\n"
        f"⭐ <b>Points / Stars :</b> <code>{points_val}</code>\n"
        f"🔥 <b>Streak :</b> <code>{u['streak']}</code> (Best: {u['best_streak']})\n"
        f"🛡️ <b>Privacy :</b> <code>{priv_status}</code>\n\n"
        f"<emoji id=5409132617750555920>🧩</emoji> <b>Puzzles Solved :</b> <code>{u['solved']}</code>\n"
        f"• 🟢 Easy: <code>{u['easy_solved'] or 0}</code> | 🟡 Med: <code>{u['medium_solved'] or 0}</code> | 🔴 Hard: <code>{u['hard_solved'] or 0}</code>\n\n"
        f"⚔️ <b>Jumble Fight :</b> <code>{u['fight_wins']}W - {u['fight_losses']}L</code> ({winrate:.1f}%)\n"
        f"💰 <b>Bet Fight :</b> <code>{u['bet_wins']}W - {u['bet_losses']}L</code> ({bet_winrate:.1f}%)</blockquote>"
    )

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

    await send_jumble_rich(client, message.chat.id, caption_html, buttons)

import html
import time
from config import START_IMG, SUPPORT_GC, ADD_ME_URL, MUSIC_BOT_URL
from database import DB, ensure_user, get_user
from helpers import get_mention, is_group, is_authed, is_owner
from pyrogram import Client, filters
from pyrogram.enums import ChatType, ParseMode
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message

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

    total_fights = (u["fight_wins"] or 0) + (u["fight_losses"] or 0)
    winrate = ((u["fight_wins"] / total_fights) * 100) if total_fights else 0
    total_bets = (u["bet_wins"] or 0) + (u["bet_losses"] or 0)
    bet_winrate = (((u["bet_wins"] or 0) / total_bets) * 100) if total_bets else 0
    mention = get_mention(target)
    priv_status = "🔒 Private" if u["is_private"] else "🌐 Public"

    await message.reply_text(
        f"<blockquote>👤 {mention} (<code>{target.id}</code>)\n\n"
        f"⭐ <b>Total Points:</b> <code>{u['points']}</code>\n"
        f"🧩 <b>Total Solved:</b> <code>{u['solved']}</code>\n"
        f"• 🟢 Easy: <code>{u['easy_solved'] or 0}</code> | 🟡 Med: <code>{u['medium_solved'] or 0}</code> | 🔴 Hard: <code>{u['hard_solved'] or 0}</code>\n"
        f"🔥 <b>Current Streak:</b> <code>{u['streak']}</code> (Best: {u['best_streak']})\n"
        f"🛡️ <b>Privacy:</b> <code>{priv_status}</code>\n\n"
        f"⚔️ <b>Jumble Fight:</b> <code>{u['fight_wins']}W - {u['fight_losses']}L</code> ({winrate:.1f}%)\n"
        f"💰 <b>Bet Fight:</b> <code>{u['bet_wins']}W - {u['bet_losses']}L</code> ({bet_winrate:.1f}%)</blockquote>",
        parse_mode=ParseMode.HTML
    )

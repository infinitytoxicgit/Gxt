import asyncio
import time
from database import DB, get_settings, get_global_config, ensure_user, get_user
from helpers import clean_answer, get_mention, safe_delete_and_unpin, delete_after, LOCK, send_log_event
from plugins.fight import ACTIVE_FIGHTS, fight_next
from plugins.game_core import start_game
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message

ALL_BOT_COMMANDS = {
    "start", "help", "jumble", "jumblefight", "fight", "jumblebetfight", "betfight",
    "settings", "setting", "setpoints", "sethint", "setdaily", "setbonus", "daily", "bonus",
    "private", "public", "addword", "addwords", "delword", "delallword", "word", "words",
    "auth", "unauth", "authlist", "update", "gitpull", "stats", "score", "leaderboard", "lb",
    "backup", "log", "calculate"
}

@Client.on_message(filters.text & filters.group, group=1)
async def group_answer_handler(client: Client, message: Message):
    if not message.from_user or not message.text:
        return

    txt = message.text.strip()
    if txt.startswith(("/", "!", ".")):
        cmd = txt[1:].split()[0].split("@")[0].lower()
        if cmd in ALL_BOT_COMMANDS:
            return

    chat_id = message.chat.id
    user_id = message.from_user.id
    cleaned_input = clean_answer(txt)
    if not cleaned_input:
        return

    # 1. Fight Answer Check
    if chat_id in ACTIVE_FIGHTS:
        async with LOCK:
            game = ACTIVE_FIGHTS.get(chat_id)
            if not game or user_id not in game["players"]:
                return
            if time.time() <= game["expires"] and cleaned_input == clean_answer(game["word"]):
                if game.get("task") and not game["task"].done():
                    game["task"].cancel()
                game["scores"][user_id] += 1
                u_mention = get_mention(message.from_user)
                await message.reply_text(f"<blockquote>⚡ {u_mention} won Round {game['round']}!</blockquote>", parse_mode=ParseMode.HTML)
                await asyncio.sleep(2.5)
                asyncio.create_task(fight_next(client, chat_id))
                return
        return

    # 2. Normal Puzzle Check
    game = DB.execute("SELECT * FROM games WHERE chat_id=? AND solved=0", (chat_id,)).fetchone()
    if not game or time.time() > game["expires"]:
        return

    if cleaned_input == clean_answer(game["word"]):
        updated = DB.execute("UPDATE games SET solved=1 WHERE chat_id=? AND solved=0", (chat_id,))
        if updated.rowcount != 1:
            return
        DB.commit()

        ensure_user(message.from_user)
        u = get_user(user_id)
        settings = get_settings(chat_id)
        diff = game["difficulty"].lower()
        pts_reward = get_global_config(f"points_{diff}", 10)
        new_streak = u["streak"] + 1
        best = max(new_streak, u["best_streak"])

        diff_column = "medium_solved"
        if diff == "easy":
            diff_column = "easy_solved"
        elif diff == "hard":
            diff_column = "hard_solved"

        DB.execute(f"""
            UPDATE users
            SET points = points + ?, solved = solved + 1, {diff_column} = {diff_column} + 1,
                streak = ?, best_streak = ?
            WHERE user_id = ?
        """, (pts_reward, new_streak, best, user_id))

        DB.execute("INSERT INTO score_history (user_id, chat_id, points, timestamp) VALUES (?, ?, ?, ?)", (user_id, chat_id, pts_reward, time.time()))
        DB.commit()

        # Send Real-Time Log to Channel
        asyncio.create_task(send_log_event(client, message.from_user, message.chat, game["word"], txt, pts_reward, diff))

        if settings["auto_delete"] and game["message_id"]:
            await safe_delete_and_unpin(client, chat_id, game["message_id"])

        u_mention = get_mention(message.from_user)
        c_msg = await message.reply_text(
            f"<blockquote>🎉 <b>CORRECT!</b>\n\n👤 {u_mention}\n✅ <b>Word:</b> <code>{game['word'].upper()}</code>\n⭐ <b>+{pts_reward} pts</b> | Streak: <code>{new_streak}</code></blockquote>",
            parse_mode=ParseMode.HTML
        )
        if settings["auto_delete"]:
            asyncio.create_task(delete_after(c_msg, 4))

        await asyncio.sleep(3)
        if s := get_settings(chat_id):
            if chat_id not in ACTIVE_FIGHTS and s["is_active"]:
                asyncio.create_task(start_game(client, chat_id, s["default_diff"] or "medium", chat_id))

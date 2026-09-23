import asyncio
import time
from database import DB, get_settings, get_global_config, ensure_user, get_user
from helpers import clean_answer, get_mention, safe_delete_and_unpin, delete_after, LOCK, send_log_event
from plugins.fight import ACTIVE_FIGHTS, fight_next
from plugins.game_core import start_game
from pyrogram import Client, filters, enums, types
from pyrogram.types import Message
from utils.rich import send_jumble_rich, html_to_rich_blocks

ALL_BOT_COMMANDS = {
    "start", "help", "jumble", "jumblefight", "fight", "jumblebetfight", "betfight",
    "settings", "setting", "setpoints", "sethint", "setdaily", "setbonus", "daily", "bonus",
    "private", "public", "addword", "addwords", "delword", "delallword", "word", "words",
    "auth", "unauth", "authlist", "update", "gitpull", "stats", "score", "leaderboard", "lb",
    "backup", "log", "calculate", "shop", "store", "exp", "rank"
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

    now = time.time()

    # 1. Fight Answer Check
    if chat_id in ACTIVE_FIGHTS:
        async with LOCK:
            game = ACTIVE_FIGHTS.get(chat_id)
            if not game or user_id not in game["players"]:
                return
            if now <= game["expires"] and cleaned_input == clean_answer(game["word"]):
                if game.get("task") and not game["task"].done():
                    game["task"].cancel()
                game["scores"][user_id] += 1
                u_mention = get_mention(message.from_user)
                fight_caption = f"<blockquote><emoji id=5895705279416241926>⚡</emoji> <u><b>ROUND {game['round']} WON!</b></u>\n\n{u_mention} scored this round!</blockquote>"
                await send_jumble_rich(client, chat_id, fight_caption)
                await asyncio.sleep(2.5)
                asyncio.create_task(fight_next(client, chat_id))
                return
        return

    # 2. Normal Puzzle Check
    game = DB.execute("SELECT * FROM games WHERE chat_id=? AND solved=0", (chat_id,)).fetchone()
    if not game or now > game["expires"]:
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

        # Base Rewards
        base_pts = get_global_config(f"points_{diff}", 10)
        base_exp = get_global_config(f"exp_{diff}", 15)

        # Check Active Boosters
        p_boost_until = u["point_boost_until"] if "point_boost_until" in u.keys() else 0
        e_boost_until = u["exp_boost_until"] if "exp_boost_until" in u.keys() else 0

        has_p_boost = now < p_boost_until
        has_e_boost = now < e_boost_until

        pts_reward = base_pts * 2 if has_p_boost else base_pts
        exp_reward = base_exp * 2 if has_e_boost else base_exp

        # Level Calculation
        old_exp = u["exp"] if "exp" in u.keys() else 0
        new_exp = old_exp + exp_reward
        old_level = (old_exp // 500) + 1
        new_level = (new_exp // 500) + 1

        new_streak = u["streak"] + 1
        best = max(new_streak, u["best_streak"])

        diff_column = "medium_solved"
        if diff == "easy":
            diff_column = "easy_solved"
        elif diff == "hard":
            diff_column = "hard_solved"

        # Update User in DB
        DB.execute(f"""
            UPDATE users
            SET points = points + ?,
                stars = stars + ?,
                exp = exp + ?,
                solved = solved + 1,
                {diff_column} = {diff_column} + 1,
                streak = ?,
                best_streak = ?
            WHERE user_id = ?
        """, (pts_reward, pts_reward, exp_reward, new_streak, best, user_id))

        DB.execute(
            "INSERT INTO score_history (user_id, chat_id, points, timestamp) VALUES (?, ?, ?, ?)",
            (user_id, chat_id, pts_reward, now)
        )
        DB.commit()

        # Send Real-Time Log to Channel
        asyncio.create_task(send_log_event(client, message.from_user, message.chat, game["word"], txt, pts_reward, diff))

        if settings["auto_delete"] and game["message_id"]:
            await safe_delete_and_unpin(client, chat_id, game["message_id"])

        u_mention = get_mention(message.from_user)
        booster_badge = " (⚡ 2x Active)" if (has_p_boost or has_e_boost) else ""
        lvl_up_text = f"\n<emoji id=5895705279416241926>🎉</emoji> <b>LEVEL UP!</b> Reached <b>Level {new_level}</b>!" if new_level > old_level else ""

        ans_caption = (
            "<blockquote><emoji id=5895705279416241926>🎉</emoji> <u><b>CORRECT ANSWER!</b></u></blockquote>\n\n"
            "<blockquote expandable>"
            f"<emoji id=5974235702701853774>👤</emoji> <b>Solver :</b> {u_mention}\n"
            f"✅ <b>Word :</b> <code>{game['word'].upper()}</code>\n"
            f"⭐ <b>Gains :</b> +{pts_reward} Stars | +{exp_reward} EXP{booster_badge}\n"
            f"<emoji id=6066395745139824604>🔥</emoji> <b>Streak :</b> <code>{new_streak}</code> (Best: {best}){lvl_up_text}</blockquote>"
        )

        buttons = [
            [
                types.RichMessageButton(
                    text="🛍️ Power Shop",
                    style=enums.ButtonStyle.SUCCESS,
                    callback_data=f"buy_shop|menu|{user_id}",
                ),
                types.RichMessageButton(
                    text="👤 My Stats",
                    style=enums.ButtonStyle.PRIMARY,
                    callback_data=f"show_my_stats|{user_id}",
                ),
            ]
        ]

        c_msg = await send_jumble_rich(client, chat_id, ans_caption, buttons)
        if settings["auto_delete"] and c_msg:
            asyncio.create_task(delete_after(c_msg, 5))

        await asyncio.sleep(3)
        if s := get_settings(chat_id):
            if chat_id not in ACTIVE_FIGHTS and s["is_active"]:
                asyncio.create_task(start_game(client, chat_id, s["default_diff"] or "medium", chat_id))

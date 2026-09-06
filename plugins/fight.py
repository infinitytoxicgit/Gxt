import asyncio
import time
from collections import defaultdict
import random

from database import DB, get_settings, ensure_user, get_user
from helpers import LOCK, safe_delete_and_unpin, delete_after, get_mention, is_group, is_admin_or_owner
from image_gen import make_puzzle_image
from plugins.game_core import ACTIVE_FIGHTS, start_game
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from word_bank import WORDS, jumble_word

FIGHT_LOBBY = {}
REBET_LOBBY = {}

def fight_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("💡 𝐇ɪɴᴛ", callback_data="fight_hint")]])

async def fight_timeout_task(client: Client, chat_id: int, round_num: int, timer_duration: int):
    await asyncio.sleep(timer_duration)
    should_advance = False
    async with LOCK:
        game = ACTIVE_FIGHTS.get(chat_id)
        if game and game["round"] == round_num:
            word = game["word"]
            s = get_settings(chat_id)
            if s["auto_delete"] and game.get("msg_id"):
                await safe_delete_and_unpin(client, chat_id, game["msg_id"])
            try:
                t_msg = await client.send_message(
                    chat_id,
                    f"<blockquote>⏰ <b>𝐑ᴏᴜɴᴅ {round_num} 𝐓ɪᴍᴇᴏᴜᴛ!</b>\n"
                    f"❌ <b>Answer:</b> <code>{word.upper()}</code>\n"
                    f"🔄 <i>Next round starting...</i></blockquote>",
                    parse_mode=ParseMode.HTML
                )
                if s["auto_delete"]:
                    asyncio.create_task(delete_after(t_msg, 4))
            except Exception:
                pass
            should_advance = True

    if should_advance:
        await asyncio.sleep(2.5)
        asyncio.create_task(fight_next(client, chat_id))

async def fight_next(client: Client, chat_id: int):
    game = ACTIVE_FIGHTS.get(chat_id)
    if not game:
        return

    curr = asyncio.current_task()
    if game.get("task") and game["task"] is not curr and not game["task"].done():
        try:
            game["task"].cancel()
        except Exception:
            pass

    game["round"] += 1
    if game["round"] > 10:
        await finish_fight(client, chat_id)
        return

    diff = game["difficulty"]
    word = random.choice(WORDS[diff])
    jumbled = jumble_word(word)

    game["word"] = word
    game["expires"] = time.time() + game["timer"]
    game["round_hints"] = defaultdict(lambda: {"count": 0, "indices": []})

    fight_tag = "BET FIGHT" if game.get("is_bet") else "FIGHT"
    image = make_puzzle_image(jumbled, f"{fight_tag} {diff.upper()}", game["round"])
    title_header = "💰 <b>𝐉𝐔𝐌𝐁𝐋𝐄 𝐁𝐄𝐓 𝐅𝐈𝐆𝐇𝐓" if game.get("is_bet") else "⚔️ <b>𝐉𝐔𝐌𝐁𝐋𝐄 𝐅𝐈𝐆𝐇𝐓"
    extra_info = f"\n💵 <b>𝐁ᴇᴛ:</b> <code>{game.get('bet_amount')} pts</code>" if game.get("is_bet") else ""

    try:
        sent = await client.send_photo(
            chat_id,
            photo=image,
            caption=(
                f"<blockquote>{title_header} — 𝐑𝐎𝐔𝐍𝐃 {game['round']}/10</b>\n\n"
                f"🎯 <b>𝐃ɪғғɪᴄᴜʟᴛʏ:</b> <code>{diff.title()}</code>\n"
                f"⏱️ <b>𝐓ɪᴍᴇ:</b> <code>{game['timer']}s</code>{extra_info}\n"
                f"👥 <b>Players:</b> {game['mentions'][game['players'][0]]} 🆚 {game['mentions'][game['players'][1]]}</blockquote>"
            ),
            reply_markup=fight_keyboard(),
            parse_mode=ParseMode.HTML
        )
        game["msg_id"] = sent.id
        try:
            await sent.pin(disable_notification=True)
        except Exception:
            pass
    except Exception as e:
        print(f"Fight error: {e}")

    game["task"] = asyncio.create_task(fight_timeout_task(client, chat_id, game["round"], game["timer"]))

async def finish_fight(client: Client, chat_id: int):
    game = ACTIVE_FIGHTS.pop(chat_id, None)
    if not game:
        return

    curr = asyncio.current_task()
    if game.get("task") and game["task"] is not curr and not game["task"].done():
        try:
            game["task"].cancel()
        except Exception:
            pass

    s = get_settings(chat_id)
    if s["auto_delete"] and game.get("msg_id"):
        await safe_delete_and_unpin(client, chat_id, game["msg_id"])

    p1, p2 = game["players"]
    s1, s2 = game["scores"][p1], game["scores"][p2]
    is_bet = game.get("is_bet", False)
    bet_amt = game.get("bet_amount", 0)
    is_rebet = game.get("is_rebet", False)
    now = time.time()

    winner = p1 if s1 > s2 else (p2 if s2 > s1 else None)
    loser = p2 if winner == p1 else (p1 if winner == p2 else None)
    w_score = max(s1, s2)
    l_score = min(s1, s2)
    m1, m2 = game["mentions"][p1], game["mentions"][p2]
    end_kb = None

    if not is_bet:
        if winner:
            DB.execute("UPDATE users SET fight_wins=fight_wins+1 WHERE user_id=?", (winner,))
            DB.execute("UPDATE users SET fight_losses=fight_losses+1 WHERE user_id=?", (loser,))
            DB.commit()
        result = f"<blockquote>🏁 <b>𝐉𝐔𝐌𝐁𝐋𝐄 𝐅𝐈𝐆𝐇𝐓 𝐎𝐕𝐄𝐑!</b>\n\n👤 {m1} — <b>{s1} pts</b>\n👤 {m2} — <b>{s2} pts</b>\n\n"
        result += f"🏆 <b>Winner:</b> {game['mentions'][winner]} 🎉</blockquote>" if winner else "🤝 <b>Match Draw!</b></blockquote>"
    else:
        if winner:
            if is_rebet:
                total_pot = (bet_amt * 2) + 100
                DB.execute("UPDATE users SET points=points+?, bet_wins=bet_wins+1 WHERE user_id=?", (total_pot, winner))
                DB.execute("UPDATE users SET bet_losses=bet_losses+1 WHERE user_id=?", (loser,))
                DB.execute("INSERT INTO score_history (user_id, chat_id, points, timestamp) VALUES (?, ?, ?, ?)", (winner, chat_id, total_pot, now))
                DB.commit()
                result = (
                    f"<blockquote>💰 <b>COMEBACK RE-BET OVER!</b>\n\n"
                    f"🏆 <b>Winner:</b> {game['mentions'][winner]} (+{total_pot} pts)\n"
                    f"💀 <b>Loser:</b> {game['mentions'][loser]}</blockquote>"
                )
            else:
                total_pot = bet_amt * 2
                win_reward = int(total_pot * 0.75)
                loser_cashback = total_pot - win_reward
                rebet_stake = int(bet_amt * 0.25)

                DB.execute("UPDATE users SET points=points+?, bet_wins=bet_wins+1 WHERE user_id=?", (win_reward, winner))
                DB.execute("UPDATE users SET points=points+?, bet_losses=bet_losses+1 WHERE user_id=?", (loser_cashback, loser))
                DB.execute("INSERT INTO score_history (user_id, chat_id, points, timestamp) VALUES (?, ?, ?, ?)", (winner, chat_id, win_reward, now))
                DB.execute("INSERT INTO score_history (user_id, chat_id, points, timestamp) VALUES (?, ?, ?, ?)", (loser, chat_id, loser_cashback, now))
                DB.commit()

                REBET_LOBBY[chat_id] = {
                    "original_winner": winner,
                    "original_loser": loser,
                    "rebet_amount": rebet_stake,
                    "difficulty": game["difficulty"],
                    "timer": game["timer"],
                    "winner_mention": game['mentions'][winner],
                    "loser_mention": game['mentions'][loser]
                }
                end_kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"🔁 25% Re-Bet ({rebet_stake} pts) + 100 Bonus", callback_data="rebet_challenge")]])
                result = (
                    f"<blockquote>💰 <b>𝐉𝐔𝐌𝐁𝐋𝐄 𝐁𝐄𝐓 𝐅𝐈𝐆𝐇𝐓 𝐎𝐕𝐄𝐑!</b>\n\n"
                    f"🏆 <b>Winner (75%):</b> {game['mentions'][winner]} (+{win_reward} pts)\n"
                    f"🛡️ <b>Cashback (25%):</b> {game['mentions'][loser]} (+{loser_cashback} pts)</blockquote>"
                )
        else:
            DB.execute("UPDATE users SET points=points+? WHERE user_id=?", (bet_amt, p1))
            DB.execute("UPDATE users SET points=points+? WHERE user_id=?", (bet_amt, p2))
            DB.commit()
            result = f"<blockquote>🤝 <b>BET DRAW! Refunded {bet_amt} points each.</b></blockquote>"

    await client.send_message(chat_id, result, reply_markup=end_kb, parse_mode=ParseMode.HTML)
    await asyncio.sleep(3)
    if s["is_active"]:
        asyncio.create_task(start_game(client, chat_id, s["default_diff"] or "medium", chat_id))

@Client.on_message(filters.command(["jumblefight", "fight"]))
async def jumble_fight_cmd(client: Client, message: Message):
    if not is_group(message):
        return await message.reply_text("Group only command.")
    target_user = None
    if message.reply_to_message and message.reply_to_message.from_user:
        target_user = message.reply_to_message.from_user
    elif len(message.command) >= 2:
        arg = message.command[1]
        try:
            target_user = await client.get_users(int(arg) if arg.isdigit() else arg)
        except Exception:
            return await message.reply_text("User nahi mila.")

    if not target_user or target_user.id == message.from_user.id or target_user.is_bot:
        return await message.reply_text("Valid human user ko target karein.")

    ensure_user(message.from_user)
    ensure_user(target_user)

    key = message.chat.id
    if key in ACTIVE_FIGHTS:
        return await message.reply_text("Fight already running.")

    m1 = get_mention(message.from_user)
    m2 = get_mention(target_user)

    FIGHT_LOBBY[key] = {
        "p1": message.from_user.id,
        "p2": target_user.id,
        "p1_name": message.from_user.first_name,
        "p2_name": target_user.first_name,
        "m1": m1,
        "m2": m2,
        "difficulty": "medium",
        "timer": 60,
        "is_bet": False,
        "bet_amount": 0
    }

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🟢 Easy", callback_data="f_diff_easy"),
            InlineKeyboardButton("🟡 Medium", callback_data="f_diff_medium"),
            InlineKeyboardButton("🔴 Hard", callback_data="f_diff_hard")
        ],
        [
            InlineKeyboardButton("⏱️ 30s", callback_data="f_time_30"),
            InlineKeyboardButton("⏱️ 45s", callback_data="f_time_45"),
            InlineKeyboardButton("⏱️ 60s", callback_data="f_time_60")
        ],
        [
            InlineKeyboardButton("✅ Accept Challenge", callback_data="f_accept"),
            InlineKeyboardButton("❌ Decline", callback_data="f_decline")
        ]
    ])
    await message.reply_text(f"<blockquote>⚔️ {m1} challenged {m2}!</blockquote>", reply_markup=kb, parse_mode=ParseMode.HTML)

@Client.on_message(filters.command(["jumblebetfight", "betfight"]))
async def bet_fight_cmd(client: Client, message: Message):
    if not is_group(message):
        return await message.reply_text("Group only command.")
    parts = message.command[1:]
    target_user = None
    if message.reply_to_message and message.reply_to_message.from_user:
        target_user = message.reply_to_message.from_user

    amount = 0
    diff = "medium"
    for p in parts:
        if p.isdigit() and int(p) >= 100:
            amount = int(p)
        elif p.lower() in ("easy", "medium", "hard"):
            diff = p.lower()
        elif p.startswith("@") and not target_user:
            try:
                target_user = await client.get_users(p)
            except Exception:
                pass

    if not target_user or amount < 100:
        return await message.reply_text("Usage: <code>/betfight easy 500 @username</code> (Min: 100 pts)")

    ensure_user(message.from_user)
    ensure_user(target_user)
    u1, u2 = get_user(message.from_user.id), get_user(target_user.id)

    if u1["points"] < amount or u2["points"] < amount:
        return await message.reply_text("Dono players ke paas bet ke barabar points hone chahiye.")

    m1, m2 = get_mention(message.from_user), get_mention(target_user)
    FIGHT_LOBBY[message.chat.id] = {
        "p1": message.from_user.id,
        "p2": target_user.id,
        "p1_name": message.from_user.first_name,
        "p2_name": target_user.first_name,
        "m1": m1,
        "m2": m2,
        "difficulty": diff,
        "timer": 60,
        "is_bet": True,
        "bet_amount": amount,
        "is_rebet": False
    }

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Accept Bet", callback_data="f_accept"),
            InlineKeyboardButton("❌ Decline", callback_data="f_decline")
        ]
    ])
    await message.reply_text(f"<blockquote>💰 {m1} challenged {m2} for <b>{amount} points</b>!</blockquote>", reply_markup=kb, parse_mode=ParseMode.HTML)

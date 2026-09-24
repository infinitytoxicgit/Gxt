import asyncio
import os
import random
import time
from collections import defaultdict

from database import DB, get_settings, ensure_user, get_user
from helpers import LOCK, safe_delete_and_unpin, delete_after, get_mention, is_group
from image_gen import make_puzzle_image
from plugins.game_core import ACTIVE_FIGHTS, start_game
from pyrogram import Client, filters, enums, types
from pyrogram.types import Message, CallbackQuery
from utils.rich import send_jumble_rich, edit_jumble_rich, html_to_rich_blocks
from word_bank import WORDS, jumble_word

FIGHT_LOBBY = {}
REBET_LOBBY = {}


def build_fight_lobby_card(lobby_data):
    m1 = lobby_data["m1"]
    m2 = lobby_data["m2"]
    diff = lobby_data["difficulty"]
    timer = lobby_data["timer"]
    rounds = lobby_data["total_rounds"]
    is_bet = lobby_data["is_bet"]
    amt = lobby_data["bet_amount"]

    header = "💰 <u><b>HIGH STAKES BET FIGHT</b></u>" if is_bet else "⚔️ <u><b>JUMBLE FIGHT INVITATION</b></u>"
    bet_line = f"💵 <b>Bet Amount :</b> <code>{amt} Points / Stars</code>\n" if is_bet else ""

    caption = (
        f"<blockquote>{header}</blockquote>\n\n"
        f"<blockquote>👤 <b>Challenger :</b> {m1}\n"
        f"🎯 <b>Opponent :</b> {m2}\n"
        f"{bet_line}"
        f"🏆 <b>Total Rounds :</b> <code>{rounds} Rounds</code>\n"
        f"⏱️ <b>Round Timer :</b> <code>{timer}s</code> | <b>Mode:</b> <code>{diff.title()}</code></blockquote>\n\n"
        "<blockquote><i>Opponent tap Accept Challenge to duel!</i></blockquote>"
    )

    r_list = [10, 20, 30, 40, 50]
    rounds_btns = [
        types.RichMessageButton(
            text=f"{'🟢' if rounds == r else '🔴'} {r}R",
            style=enums.ButtonStyle.SUCCESS if rounds == r else enums.ButtonStyle.DANGER,
            callback_data=f"f_set_r|{r}",
        )
        for r in r_list
    ]

    buttons = [
        [
            types.RichMessageButton(text="🟢 Easy" if diff == "easy" else "🔴 Easy", style=enums.ButtonStyle.SUCCESS if diff == "easy" else enums.ButtonStyle.DANGER, callback_data="f_diff|easy"),
            types.RichMessageButton(text="🟢 Med" if diff == "medium" else "🔴 Med", style=enums.ButtonStyle.SUCCESS if diff == "medium" else enums.ButtonStyle.DANGER, callback_data="f_diff|medium"),
            types.RichMessageButton(text="🟢 Hard" if diff == "hard" else "🔴 Hard", style=enums.ButtonStyle.SUCCESS if diff == "hard" else enums.ButtonStyle.DANGER, callback_data="f_diff|hard"),
        ],
        [
            types.RichMessageButton(text="🟢 30s" if timer == 30 else "🔴 30s", style=enums.ButtonStyle.SUCCESS if timer == 30 else enums.ButtonStyle.DANGER, callback_data="f_time|30"),
            types.RichMessageButton(text="🟢 45s" if timer == 45 else "🔴 45s", style=enums.ButtonStyle.SUCCESS if timer == 45 else enums.ButtonStyle.DANGER, callback_data="f_time|45"),
            types.RichMessageButton(text="🟢 60s" if timer == 60 else "🔴 60s", style=enums.ButtonStyle.SUCCESS if timer == 60 else enums.ButtonStyle.DANGER, callback_data="f_time|60"),
        ],
        rounds_btns,
        [
            types.RichMessageButton(text="✅ Accept Challenge", style=enums.ButtonStyle.SUCCESS, callback_data="f_accept"),
            types.RichMessageButton(text="❌ Decline", style=enums.ButtonStyle.DANGER, callback_data="f_decline"),
        ],
    ]
    return caption, buttons


async def fight_timeout_task(client: Client, chat_id: int, round_num: int, timer_duration: int):
    await asyncio.sleep(timer_duration)
    should_advance = False
    async with LOCK:
        game = ACTIVE_FIGHTS.get(chat_id)
        if game and game["round"] == round_num:
            word = game["word"]
            s = dict(get_settings(chat_id)) if get_settings(chat_id) else {}
            if s.get("auto_delete") and game.get("msg_id"):
                await safe_delete_and_unpin(client, chat_id, game["msg_id"])
            try:
                caption = (
                    f"<blockquote>⏰ <u><b>ROUND {round_num} TIMEOUT!</b></u></blockquote>\n\n"
                    f"<blockquote>❌ <b>Answer was :</b> <code>{word.upper()}</code>\n"
                    f"🔄 <i>Next round starting in 2 seconds...</i></blockquote>"
                )
                t_msg = await send_jumble_rich(client, chat_id, caption)
                if s.get("auto_delete") and t_msg:
                    asyncio.create_task(delete_after(t_msg, 4))
            except Exception:
                pass
            should_advance = True

    if should_advance:
        await asyncio.sleep(2)
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
    total_r = game.get("total_rounds", 10)
    if game["round"] > total_r:
        await finish_fight(client, chat_id)
        return

    diff = game["difficulty"]
    word = random.choice(WORDS[diff])
    jumbled = jumble_word(word)

    game["word"] = word
    game["expires"] = time.time() + game["timer"]
    game["round_hints"] = defaultdict(lambda: {"count": 0, "indices": []})

    fight_tag = "BET FIGHT" if game.get("is_bet") else "FIGHT"
    image_path = make_puzzle_image(jumbled, f"{fight_tag} {diff.upper()}", game["round"])

    header_icon = "💰" if game.get("is_bet") else "⚔️"
    header_name = "𝐉𝐔𝐌𝐁𝐋𝐄 𝐁𝐄𝐓 𝐅𝐈𝐆𝐇𝐓" if game.get("is_bet") else "𝐉𝐔𝐌𝐁𝐋𝐄 𝐅𝐈𝐆𝐇𝐓"
    extra_info = f"\n💵 <b>Stake Pot:</b> <code>{game.get('bet_amount')} pts</code>" if game.get("is_bet") else ""

    caption = (
        f"<blockquote>{header_icon} <u><b>{header_name} — ROUND {game['round']}/{total_r}</b></u></blockquote>\n\n"
        f"<blockquote>🎯 <b>Difficulty :</b> <code>{diff.title()}</code> | ⏱️ <b>Time:</b> <code>{game['timer']}s</code>{extra_info}\n"
        f"👥 <b>Duelists :</b> {game['mentions'][game['players'][0]]} 🆚 {game['mentions'][game['players'][1]]}</blockquote>\n\n"
        "<blockquote>🔀 <i>Unscramble letters and type in chat to score!</i></blockquote>"
    )

    buttons = [
        [
            types.RichMessageButton(
                text="💡 𝐇ɪɴᴛ",
                style=enums.ButtonStyle.PRIMARY,
                callback_data="fight_hint",
            )
        ]
    ]

    try:
        sent = await send_jumble_rich(client, chat_id, caption, buttons, photo=image_path if os.path.isfile(str(image_path)) else None)
        game["msg_id"] = sent.id
        try:
            await sent.pin(disable_notification=True)
        except Exception:
            pass
    except Exception as e:
        print(f"Fight dispatch error: {e}")

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

    s = dict(get_settings(chat_id)) if get_settings(chat_id) else {}
    if s.get("auto_delete") and game.get("msg_id"):
        await safe_delete_and_unpin(client, chat_id, game["msg_id"])

    p1, p2 = game["players"]
    s1, s2 = game["scores"][p1], game["scores"][p2]
    is_bet = game.get("is_bet", False)
    bet_amt = game.get("bet_amount", 0)
    is_rebet = game.get("is_rebet", False)
    now = time.time()

    winner = p1 if s1 > s2 else (p2 if s2 > s1 else None)
    loser = p2 if winner == p1 else (p1 if winner == p2 else None)
    m1, m2 = game["mentions"][p1], game["mentions"][p2]
    end_buttons = None

    if not is_bet:
        if winner:
            DB.execute("UPDATE users SET fight_wins=fight_wins+1 WHERE user_id=?", (winner,))
            DB.execute("UPDATE users SET fight_losses=fight_losses+1 WHERE user_id=?", (loser,))
            DB.commit()

        win_text = f"🏆 <b>Winner :</b> {game['mentions'][winner]} 🎉" if winner else "🤝 <b>Match Draw!</b>"
        result_caption = (
            "<blockquote>🏁 <u><b>𝐉𝐔𝐌𝐁𝐋𝐄 𝐅𝐈𝐆𝐇𝐓 𝐎𝐕𝐄𝐑!</b></u></blockquote>\n\n"
            f"<blockquote>👤 {m1} — <b>{s1} pts</b>\n"
            f"👤 {m2} — <b>{s2} pts</b>\n\n"
            f"{win_text}</blockquote>"
        )
    else:
        if winner:
            if is_rebet:
                total_pot = (bet_amt * 2) + 100
                DB.execute("UPDATE users SET points=points+?, stars=stars+?, bet_wins=bet_wins+1 WHERE user_id=?", (total_pot, total_pot, winner))
                DB.execute("UPDATE users SET bet_losses=bet_losses+1 WHERE user_id=?", (loser,))
                DB.commit()
                result_caption = (
                    "<blockquote>💰 <u><b>COMEBACK RE-BET OVER!</b></u></blockquote>\n\n"
                    f"<blockquote>🏆 <b>Final Winner :</b> {game['mentions'][winner]} (+{total_pot} pts/stars)\n"
                    f"💀 <b>Loser :</b> {game['mentions'][loser]}</blockquote>"
                )
            else:
                total_pot = bet_amt * 2
                win_reward = int(total_pot * 0.75)
                loser_cashback = total_pot - win_reward
                rebet_stake = int(bet_amt * 0.25)

                DB.execute("UPDATE users SET points=points+?, stars=stars+?, bet_wins=bet_wins+1 WHERE user_id=?", (win_reward, win_reward, winner))
                DB.execute("UPDATE users SET points=points+?, stars=stars+?, bet_losses=bet_losses+1 WHERE user_id=?", (loser_cashback, loser_cashback, loser))
                DB.commit()

                REBET_LOBBY[chat_id] = {
                    "original_winner": winner,
                    "original_loser": loser,
                    "rebet_amount": rebet_stake,
                    "difficulty": game["difficulty"],
                    "timer": game["timer"],
                    "total_rounds": 10,
                    "winner_mention": game['mentions'][winner],
                    "loser_mention": game['mentions'][loser],
                }
                end_buttons = [
                    [
                        types.RichMessageButton(
                            text=f"🔁 25% Comeback Re-Bet ({rebet_stake} pts) + 100 Bonus",
                            style=enums.ButtonStyle.SUCCESS,
                            callback_data="rebet_challenge",
                        )
                    ]
                ]
                result_caption = (
                    "<blockquote>💰 <u><b>𝐉𝐔𝐌𝐁𝐋𝐄 𝐁𝐄𝐓 𝐅𝐈𝐆𝐇𝐓 𝐎𝐕𝐄𝐑!</b></u></blockquote>\n\n"
                    f"<blockquote>🏆 <b>Winner (75%) :</b> {game['mentions'][winner]} (+{win_reward} pts)\n"
                    f"🛡️ <b>Loser Cashback (25%) :</b> {game['mentions'][loser]} (+{loser_cashback} pts)</blockquote>\n\n"
                    "<blockquote><i>Loser can tap button below to trigger Comeback Duel!</i></blockquote>"
                )
        else:
            DB.execute("UPDATE users SET points=points+?, stars=stars+? WHERE user_id=?", (bet_amt, bet_amt, p1))
            DB.execute("UPDATE users SET points=points+?, stars=stars+? WHERE user_id=?", (bet_amt, bet_amt, p2))
            DB.commit()
            result_caption = f"<blockquote>🤝 <b>BET DRAW! Refunded {bet_amt} points each.</b></blockquote>"

    await send_jumble_rich(client, chat_id, result_caption, end_buttons)
    await asyncio.sleep(3)
    if s.get("is_active", 1):
        asyncio.create_task(start_game(client, chat_id, s.get("default_diff", "medium"), chat_id))


# ============================================================
# COMMANDS & INVITATION ROUTER
# ============================================================

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
        "total_rounds": 10,
        "is_bet": False,
        "bet_amount": 0,
    }

    caption, buttons = build_fight_lobby_card(FIGHT_LOBBY[key])
    await send_jumble_rich(client, message.chat.id, caption, buttons)


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
    u1_dict = dict(u1) if u1 else {}
    u2_dict = dict(u2) if u2 else {}

    points1 = u1_dict.get("stars", 0) if u1_dict.get("stars", 0) > 0 else u1_dict.get("points", 0)
    points2 = u2_dict.get("stars", 0) if u2_dict.get("stars", 0) > 0 else u2_dict.get("points", 0)

    if points1 < amount or points2 < amount:
        return await message.reply_text("Dono players ke paas bet ke barabar points/stars hone chahiye.")

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
        "total_rounds": 10,
        "is_bet": True,
        "bet_amount": amount,
        "is_rebet": False,
    }

    caption, buttons = build_fight_lobby_card(FIGHT_LOBBY[message.chat.id])
    await send_jumble_rich(client, message.chat.id, caption, buttons)


# ============================================================
# LOBBY CALLBACKS (Accept, Decline, Configure, Rebet)
# ============================================================

@Client.on_callback_query(filters.regex(r"^(f_|rebet_)"))
async def fight_callbacks_router(client: Client, query: CallbackQuery):
    chat_id = query.message.chat.id
    user_id = query.from_user.id
    data = query.data.split("|")
    action = data[0]

    # Rebet Challenge
    if action == "rebet_challenge":
        rebet = REBET_LOBBY.get(chat_id)
        if not rebet:
            return await query.answer("Re-bet session expire ho chuka hai.", show_alert=True)
        if user_id != rebet["original_loser"]:
            return await query.answer("Sirf loser hi comeback challenge kar sakta hai!", show_alert=True)

        loser_u = dict(get_user(user_id))
        pts = loser_u.get("stars", 0) if loser_u.get("stars", 0) > 0 else loser_u.get("points", 0)
        if pts < rebet["rebet_amount"]:
            return await query.answer("Balance kam hai re-bet ke liye!", show_alert=True)

        ACTIVE_FIGHTS[chat_id] = {
            "players": [rebet["original_winner"], rebet["original_loser"]],
            "names": {rebet["original_winner"]: "Winner", rebet["original_loser"]: "Loser"},
            "mentions": {rebet["original_winner"]: rebet["winner_mention"], rebet["original_loser"]: rebet["loser_mention"]},
            "round": 0,
            "total_rounds": 10,
            "scores": defaultdict(int),
            "word": None,
            "expires": None,
            "task": None,
            "difficulty": rebet["difficulty"],
            "timer": rebet["timer"],
            "msg_id": None,
            "is_bet": True,
            "bet_amount": rebet["rebet_amount"],
            "is_rebet": True,
        }
        del REBET_LOBBY[chat_id]
        await query.answer("Comeback Re-Bet Accepted!")
        await query.message.delete()
        asyncio.create_task(fight_next(client, chat_id))
        return

    lobby = FIGHT_LOBBY.get(chat_id)
    if not lobby:
        return await query.answer("Duel request expired ya valid nahi hai.", show_alert=True)

    if action == "f_accept":
        if user_id != lobby["p2"]:
            return await query.answer("Sirf challenged player accept kar sakta hai!", show_alert=True)

        if lobby["is_bet"]:
            DB.execute("UPDATE users SET points=points-?, stars=stars-? WHERE user_id=?", (lobby["bet_amount"], lobby["bet_amount"], lobby["p1"]))
            DB.execute("UPDATE users SET points=points-?, stars=stars-? WHERE user_id=?", (lobby["bet_amount"], lobby["bet_amount"], lobby["p2"]))
            DB.commit()

        ACTIVE_FIGHTS[chat_id] = {
            "players": [lobby["p1"], lobby["p2"]],
            "names": {lobby["p1"]: lobby["p1_name"], lobby["p2"]: lobby["p2_name"]},
            "mentions": {lobby["p1"]: lobby["m1"], lobby["p2"]: lobby["m2"]},
            "round": 0,
            "total_rounds": lobby["total_rounds"],
            "scores": defaultdict(int),
            "word": None,
            "expires": None,
            "task": None,
            "difficulty": lobby["difficulty"],
            "timer": lobby["timer"],
            "msg_id": None,
            "is_bet": lobby["is_bet"],
            "bet_amount": lobby["bet_amount"],
            "is_rebet": False,
        }
        del FIGHT_LOBBY[chat_id]
        await query.answer("Duel Accepted! Starting Round 1...")
        await query.message.delete()
        asyncio.create_task(fight_next(client, chat_id))
        return

    elif action == "f_decline":
        if user_id not in (lobby["p1"], lobby["p2"]):
            return await query.answer("Aap is duel me shamil nahi hain.", show_alert=True)
        del FIGHT_LOBBY[chat_id]
        await query.message.delete()
        return await query.answer("Challenge declined.")

    # Configurations: Sirf challenger ya opponent customize kar sakein
    if user_id not in (lobby["p1"], lobby["p2"]):
        return await query.answer("Sirf dono duelists settings adjust kar sakte hain!", show_alert=True)

    if action == "f_diff":
        lobby["difficulty"] = data[1]
    elif action == "f_time":
        lobby["timer"] = int(data[1])
    elif action == "f_set_r":
        lobby["total_rounds"] = int(data[1])

    await query.answer()
    caption, buttons = build_fight_lobby_card(lobby)
    await edit_jumble_rich(client, chat_id, query.message.id, caption, buttons)

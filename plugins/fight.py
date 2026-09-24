import asyncio
import os
import random
import time
from collections import defaultdict

from database import DB, get_settings, ensure_user, get_user, get_global_config
from helpers import LOCK, safe_delete_and_unpin, delete_after, get_mention, is_group
from image_gen import make_puzzle_image
from plugins.game_core import ACTIVE_FIGHTS, start_game
from pyrogram import Client, filters, enums, types
from pyrogram.types import Message, CallbackQuery
from utils.rich import send_jumble_rich, edit_jumble_rich
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
        f"🏆 <b>Match Length :</b> <code>{rounds} Rounds</code>\n"
        f"⏱️ <b>Round Timer :</b> <code>{timer}s</code> | <b>Mode :</b> <code>{diff.title()}</code></blockquote>\n\n"
        "<blockquote><i>Choose rounds & rules below, then tap Accept Challenge!</i></blockquote>"
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
                    f"🔄 <i>Next round starting in 1 second...</i></blockquote>"
                )
                t_msg = await send_jumble_rich(client, chat_id, caption)
                if s.get("auto_delete") and t_msg:
                    asyncio.create_task(delete_after(t_msg, 3))
            except Exception:
                pass
            should_advance = True

    if should_advance:
        await asyncio.sleep(1)
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
    hint_limit = int(get_global_config(f"hints_{diff}", 3))

    p1, p2 = game["players"]
    score_board = f"📊 <b>Score :</b> {game['mentions'][p1]} (<code>{game['scores'][p1]}</code>) vs {game['mentions'][p2]} (<code>{game['scores'][p2]}</code>)"

    caption = (
        f"<blockquote>{header_icon} <u><b>{header_name} — ROUND {game['round']}/{total_r}</b></u></blockquote>\n\n"
        f"<blockquote>🎯 <b>Difficulty :</b> <code>{diff.title()}</code> | ⏱️ <b>Time :</b> <code>{game['timer']}s</code>{extra_info}\n"
        f"💡 <b>Equal Hints :</b> <code>{hint_limit}/player</code>\n"
        f"{score_board}</blockquote>\n\n"
        "<blockquote>🔀 <i>Unscramble letters and send in chat to score!</i></blockquote>"
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
        sent = await send_jumble_rich(
            client,
            chat_id,
            caption,
            buttons,
            photo=image_path if (image_path and os.path.isfile(str(image_path))) else None
        )
        game["msg_id"] = sent.id
        try:
            await sent.pin(disable_notification=True)
        except Exception:
            pass
    except Exception as e:
        print(f"Fight dispatch error: {e}")

    game["task"] = asyncio.create_task(fight_timeout_task(client, chat_id, game["round"], game["timer"]))


async def resume_group_game_loop(client: Client, chat_id: int):
    ACTIVE_FIGHTS.pop(chat_id, None)
    await asyncio.sleep(2)

    raw_s = get_settings(chat_id)
    s = dict(raw_s) if raw_s else {}

    # Sirf us group ki saved settings trigger hongi
    if s.get("is_active", 1):
        diff = s.get("default_diff") or "medium"
        try:
            DB.execute("DELETE FROM games WHERE chat_id=?", (chat_id,))
            DB.commit()
            asyncio.create_task(start_game(client, chat_id, diff, chat_id))
        except Exception as e:
            print(f"[Auto-Loop Resume Error in {chat_id}]: {e}")


async def finish_fight(client: Client, chat_id: int):
    game = ACTIVE_FIGHTS.get(chat_id)
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
                DB.execute("INSERT INTO score_history (user_id, chat_id, points, timestamp) VALUES (?, ?, ?, ?)", (winner, chat_id, total_pot, now))
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
                DB.execute("INSERT INTO score_history (user_id, chat_id, points, timestamp) VALUES (?, ?, ?, ?)", (winner, chat_id, win_reward, now))
                DB.execute("INSERT INTO score_history (user_id, chat_id, points, timestamp) VALUES (?, ?, ?, ?)", (loser, chat_id, loser_cashback, now))
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
    # Agar rebet offer hua hai toh loser ke decision ka wait karenge, warna turant loop continue hoga
    if not (is_bet and winner and not is_rebet):
        asyncio.create_task(resume_group_game_loop(client, chat_id))


# ============================================================
# COMMANDS & INVITATION ROUTER
# ============================================================

@Client.on_message(filters.command(["jumblefight", "fight"]) & filters.group, group=0)
async def jumble_fight_cmd(client: Client, message: Message):
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


@Client.on_message(filters.command(["jumblebetfight", "betfight"]) & filters.group, group=0)
async def bet_fight_cmd(client: Client, message: Message):
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
# FIGHT SOLVE DETECTOR (In-Chat Text Answers)
# ============================================================

@Client.on_message(filters.text & filters.group, group=0)
async def fight_chat_answer_listener(client: Client, message: Message):
    if not message.text or message.text.startswith("/"):
        return

    chat_id = message.chat.id
    if chat_id not in ACTIVE_FIGHTS:
        return

    game = ACTIVE_FIGHTS[chat_id]
    user_id = message.from_user.id

    if user_id not in game["players"]:
        return

    if message.text.strip().lower() == game["word"].strip().lower():
        if game.get("task") and not game["task"].done():
            game["task"].cancel()

        game["scores"][user_id] += 1
        s = dict(get_settings(chat_id)) if get_settings(chat_id) else {}
        if s.get("auto_delete") and game.get("msg_id"):
            await safe_delete_and_unpin(client, chat_id, game["msg_id"])

        win_msg = await send_jumble_rich(
            client,
            chat_id,
            f"<blockquote>🎯 <b>ROUND {game['round']} SOLVED!</b>\n\n"
            f"👤 <b>Point Scorer :</b> {game['mentions'][user_id]}\n"
            f"✅ <b>Word was :</b> <code>{game['word'].upper()}</code>\n"
            f"🔄 <i>Next round in 1 second...</i></blockquote>"
        )
        if s.get("auto_delete") and win_msg:
            asyncio.create_task(delete_after(win_msg, 3))

        await asyncio.sleep(1)
        asyncio.create_task(fight_next(client, chat_id))


# ============================================================
# LOBBY & HINTS CALLBACKS
# ============================================================

@Client.on_callback_query(filters.regex(r"^(f_|rebet_|fight_hint)"))
async def fight_callbacks_router(client: Client, query: CallbackQuery):
    chat_id = query.message.chat.id
    user_id = query.from_user.id
    data = query.data.split("|")
    action = data[0]

    # 1. Equal Hint Handling during Fight
    if action == "fight_hint":
        game = ACTIVE_FIGHTS.get(chat_id)
        if not game:
            return await query.answer("Duel expired ya active nahi hai.", show_alert=True)
        if user_id not in game["players"]:
            return await query.answer("Sirf dono duelists hi hint le sakte hain!", show_alert=True)

        diff = game["difficulty"]
        hint_limit = int(get_global_config(f"hints_{diff}", 3))
        user_hint = game["round_hints"][user_id]

        if user_hint["count"] >= hint_limit:
            return await query.answer(f"❌ Is round ke aapke {hint_limit} hints pure ho gaye!", show_alert=True)

        word = game["word"]
        avail = [i for i in range(len(word)) if i not in user_hint["indices"]]
        if not avail:
            return await query.answer("Aur clues nahi hain!", show_alert=True)

        chosen = random.choice(avail)
        user_hint["indices"].append(chosen)
        user_hint["count"] += 1

        letter = word[chosen].upper()
        return await query.answer(f"💡 Clue #{chosen + 1} is: '{letter}' ({hint_limit - user_hint['count']} hints left)", show_alert=True)

    # 2. Loser triggers Comeback Challenge (Needs Winner's Acceptance)
    if action == "rebet_challenge":
        rebet = REBET_LOBBY.get(chat_id)
        if not rebet:
            return await query.answer("Re-bet session expire ho chuka hai.", show_alert=True)
        if user_id != rebet["original_loser"]:
            return await query.answer("Sirf loser hi comeback challenge bhej sakta hai!", show_alert=True)

        loser_u = dict(get_user(user_id))
        pts = loser_u.get("stars", 0) if loser_u.get("stars", 0) > 0 else loser_u.get("points", 0)
        if pts < rebet["rebet_amount"]:
            return await query.answer("Balance kam hai re-bet ke liye!", show_alert=True)

        await query.answer("Comeback Request Sent! Waiting for Winner to accept...")

        invitation_caption = (
            "<blockquote>🔥 <u><b>COMEBACK RE-BET DUEL OFFERED!</b></u></blockquote>\n\n"
            f"<blockquote>👤 <b>Challenger (Loser):</b> {rebet['loser_mention']}\n"
            f"👑 <b>Target (Winner):</b> {rebet['winner_mention']}\n"
            f"💵 <b>Stake :</b> <code>{rebet['rebet_amount']} pts</code> (+100 Bonus Pot)\n"
            f"🏆 <b>Rounds :</b> <code>10 Rounds</code></blockquote>\n\n"
            f"<blockquote>⚠️ {rebet['winner_mention']}, kya aap yeh challenge accept karte hain?</blockquote>"
        )

        buttons = [
            [
                types.RichMessageButton(
                    text="✅ Accept Comeback",
                    style=enums.ButtonStyle.SUCCESS,
                    callback_data="rebet_accept"
                ),
                types.RichMessageButton(
                    text="❌ Decline",
                    style=enums.ButtonStyle.DANGER,
                    callback_data="rebet_decline"
                )
            ]
        ]
        await edit_jumble_rich(client, chat_id, query.message.id, invitation_caption, buttons)
        return

    # 3. Winner accepts Comeback Challenge
    if action == "rebet_accept":
        rebet = REBET_LOBBY.get(chat_id)
        if not rebet:
            return await query.answer("Request expire ho chuki hai.", show_alert=True)
        if user_id != rebet["original_winner"]:
            return await query.answer("Sirf winner hi challenge accept kar sakta hai!", show_alert=True)

        winner_u = dict(get_user(user_id))
        pts = winner_u.get("stars", 0) if winner_u.get("stars", 0) > 0 else winner_u.get("points", 0)
        if pts < rebet["rebet_amount"]:
            return await query.answer("Aapka balance kam hai!", show_alert=True)

        # Deduct stake from both
        DB.execute("UPDATE users SET points=points-?, stars=stars-? WHERE user_id=?", (rebet["rebet_amount"], rebet["rebet_amount"], rebet["original_winner"]))
        DB.execute("UPDATE users SET points=points-?, stars=stars-? WHERE user_id=?", (rebet["rebet_amount"], rebet["rebet_amount"], rebet["original_loser"]))
        DB.commit()

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
        await query.answer("Comeback Duel Accepted! Starting...")
        await query.message.delete()
        asyncio.create_task(fight_next(client, chat_id))
        return

    # 4. Winner declines Comeback Challenge
    if action == "rebet_decline":
        rebet = REBET_LOBBY.get(chat_id)
        if not rebet:
            return await query.answer("Request expire ho chuki hai.", show_alert=True)
        if user_id not in (rebet["original_winner"], rebet["original_loser"]):
            return await query.answer("Aap is match me shamil nahi hain.", show_alert=True)

        del REBET_LOBBY[chat_id]
        await query.message.delete()
        await query.answer("Comeback duel declined.")
        asyncio.create_task(resume_group_game_loop(client, chat_id))
        return

    # Regular Lobby Handling
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

    if user_id not in (lobby["p1"], lobby["p2"]):
        return await query.answer("Sirf duelists settings adjust kar sakte hain!", show_alert=True)

    if action == "f_diff":
        lobby["difficulty"] = data[1]
    elif action == "f_time":
        lobby["timer"] = int(data[1])
    elif action == "f_set_r":
        lobby["total_rounds"] = int(data[1])

    await query.answer()
    caption, buttons = build_fight_lobby_card(lobby)
    await edit_jumble_rich(client, chat_id, query.message.id, caption, buttons)

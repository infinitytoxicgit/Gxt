import asyncio
import os
import random
import time
from collections import defaultdict

from database import DB, get_settings, ensure_user, get_user, get_global_config
from helpers import (
    safe_delete_and_unpin, 
    delete_after, 
    get_mention, 
    is_group, 
    ACTIVE_FIGHTS
)
from image_gen import make_puzzle_image
from plugins.game_core import start_game
from pyrogram import Client, filters, enums, types
from pyrogram.types import Message, CallbackQuery
from utils.rich import send_jumble_rich, edit_jumble_rich
from word_bank import WORDS, jumble_word

FIGHT_LOBBY = {}
REBET_LOBBY = {}


def get_user_balance(user_id: int) -> int:
    u = get_user(user_id)
    if not u:
        return 0
    u_dict = dict(u)
    return int(u_dict.get("stars", 0) if u_dict.get("stars", 0) > 0 else u_dict.get("points", 0))


def deduct_user_stars(user_id: int, amount: int):
    DB.execute(
        "UPDATE users SET stars = MAX(0, stars - ?), points = MAX(0, points - ?) WHERE user_id = ?",
        (amount, amount, user_id)
    )
    DB.commit()


def add_user_stars(user_id: int, amount: int):
    DB.execute(
        "UPDATE users SET stars = stars + ?, points = points + ? WHERE user_id = ?",
        (amount, amount, user_id)
    )
    DB.commit()


def build_fight_lobby_card(lobby_data):
    m1 = lobby_data["m1"]
    m2 = lobby_data["m2"]
    diff = lobby_data["difficulty"]
    timer = lobby_data["timer"]
    rounds = lobby_data["total_rounds"]
    is_bet = lobby_data["is_bet"]
    amt = lobby_data["bet_amount"]

    header = "💰 <u><b>HIGH STAKES BET FIGHT</b></u>" if is_bet else "⚔️ <u><b>JUMBLE FIGHT INVITATION</b></u>"
    bet_line = f"💵 <b>Bet Stake :</b> <code>{amt} Stars (Deducted on Accept)</code>\n" if is_bet else ""

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


async def fight_timeout_task(client: Client, chat_id: int, current_round: int, round_token: int, timer_duration: int):
    try:
        await asyncio.sleep(timer_duration)
    except asyncio.CancelledError:
        return

    game = ACTIVE_FIGHTS.get(chat_id)
    if not game:
        return

    # Check whether this round was already solved or token mismatched
    if game.get("round") != current_round or game.get("round_token") != round_token or game.get("is_solved"):
        return

    game["is_solved"] = True
    word = game.get("word", "")

    s = dict(get_settings(chat_id)) if get_settings(chat_id) else {}
    if s.get("auto_delete") and game.get("msg_id"):
        await safe_delete_and_unpin(client, chat_id, game["msg_id"])

    try:
        caption = (
            f"<blockquote>⏰ <u><b>ROUND {current_round} TIMEOUT!</b></u></blockquote>\n\n"
            f"<blockquote>❌ <b>Nobody solved it! Answer was :</b> <code>{word.upper()}</code>\n"
            f"🔄 <i>Next round starting in 3 seconds...</i></blockquote>"
        )
        t_msg = await send_jumble_rich(client, chat_id, caption)
        if s.get("auto_delete") and t_msg:
            asyncio.create_task(delete_after(t_msg, 4))
    except Exception as e:
        print(f"[Timeout Broadcast Error]: {e}")

    await asyncio.sleep(3)
    # Direct reliable advance
    asyncio.create_task(fight_next(client, chat_id))


async def fight_next(client: Client, chat_id: int):
    game = ACTIVE_FIGHTS.get(chat_id)
    if not game:
        return

    # Cancel previous timer task cleanly
    if game.get("timer_task") and not game["timer_task"].done():
        try:
            game["timer_task"].cancel()
        except Exception:
            pass

    game["round"] += 1
    total_r = game.get("total_rounds", 10)
    if game["round"] > total_r:
        asyncio.create_task(finish_fight(client, chat_id))
        return

    diff = game["difficulty"]
    word = random.choice(WORDS[diff])
    jumbled = jumble_word(word)

    token = random.randint(100000, 999999)
    game["round_token"] = token
    game["word"] = word
    game["is_solved"] = False
    game["expires"] = time.time() + game["timer"]
    game["round_hints"] = defaultdict(lambda: {"count": 0, "indices": []})

    round_num = game["round"]
    timer_val = game["timer"]

    fight_tag = "BET FIGHT" if game.get("is_bet") else "FIGHT"
    try:
        image_path = make_puzzle_image(jumbled, f"{fight_tag} {diff.upper()}", round_num)
    except Exception as img_err:
        print(f"Image error: {img_err}")
        image_path = None

    header_icon = "💰" if game.get("is_bet") else "⚔️"
    header_name = "𝐉𝐔𝐌𝐁𝐋𝐄 𝐁𝐄𝐓 𝐅𝐈𝐆𝐇𝐓" if game.get("is_bet") else "𝐉𝐔𝐌𝐁𝐋𝐄 𝐅𝐈𝐆𝐇𝐓"
    extra_info = f"\n💵 <b>Stake Pot:</b> <code>{game.get('bet_amount')} Stars</code>" if game.get("is_bet") else ""
    hint_limit = int(get_global_config(f"hints_{diff}", 3))

    p1, p2 = game["players"]
    score_board = f"📊 <b>Score :</b> {game['mentions'][p1]} (<code>{game['scores'][p1]}</code>) vs {game['mentions'][p2]} (<code>{game['scores'][p2]}</code>)"

    caption = (
        f"<blockquote>{header_icon} <u><b>{header_name} — ROUND {round_num}/{total_r}</b></u></blockquote>\n\n"
        f"<blockquote>🎯 <b>Difficulty :</b> <code>{diff.title()}</code> | ⏱️ <b>Time :</b> <code>{timer_val}s</code>{extra_info}\n"
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
        if sent:
            game["msg_id"] = sent.id
            try:
                await sent.pin(disable_notification=True)
            except Exception:
                pass
    except Exception as e:
        print(f"Fight dispatch error: {e}")

    # Launch next round countdown timer
    game["timer_task"] = asyncio.create_task(fight_timeout_task(client, chat_id, round_num, token, timer_val))


async def resume_group_game_loop(client: Client, chat_id: int):
    ACTIVE_FIGHTS.pop(chat_id, None)

    raw_s = get_settings(chat_id)
    s = dict(raw_s) if raw_s else {}

    if s.get("is_active", 1):
        diff = s.get("default_diff") or "medium"
        round_t = s.get(diff, 120)

        resume_caption = (
            "<blockquote>🔄 <u><b>RESUMING GROUP GAME LOOP</b></u></blockquote>\n\n"
            f"<blockquote>⚙️ Group Settings Applied:\n"
            f"🎯 <b>Mode :</b> <code>{diff.title()}</code> | ⏱️ <b>Timer :</b> <code>{round_t}s</code>\n\n"
            f"🚀 <i>Spawning next puzzle in 3 seconds...</i></blockquote>"
        )
        try:
            r_msg = await send_jumble_rich(client, chat_id, resume_caption)
            if r_msg:
                asyncio.create_task(delete_after(r_msg, 4))
        except Exception:
            pass

        await asyncio.sleep(4)
        try:
            DB.execute("DELETE FROM games WHERE chat_id=?", (chat_id,))
            DB.commit()
            asyncio.create_task(start_game(client, chat_id, diff, chat_id))
        except Exception as e:
            print(f"[Auto-Loop Resume Error in {chat_id}]: {e}")


async def finish_fight(client: Client, chat_id: int):
    game = ACTIVE_FIGHTS.pop(chat_id, None)
    if not game:
        return

    if game.get("timer_task") and not game["timer_task"].done():
        try:
            game["timer_task"].cancel()
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
                add_user_stars(winner, total_pot)
                DB.execute("UPDATE users SET bet_wins=bet_wins+1 WHERE user_id=?", (winner,))
                DB.execute("UPDATE users SET bet_losses=bet_losses+1 WHERE user_id=?", (loser,))
                DB.execute("INSERT INTO score_history (user_id, chat_id, points, timestamp) VALUES (?, ?, ?, ?)", (winner, chat_id, total_pot, now))
                DB.commit()
                result_caption = (
                    "<blockquote>💰 <u><b>COMEBACK RE-BET OVER!</b></u></blockquote>\n\n"
                    f"<blockquote>🏆 <b>Final Winner :</b> {game['mentions'][winner]} (+{total_pot} Stars)\n"
                    f"💀 <b>Loser :</b> {game['mentions'][loser]}</blockquote>"
                )
            else:
                total_pot = bet_amt * 2
                win_reward = int(total_pot * 0.75)
                loser_cashback = total_pot - win_reward
                rebet_stake = int(bet_amt * 0.25)

                add_user_stars(winner, win_reward)
                add_user_stars(loser, loser_cashback)
                DB.execute("UPDATE users SET bet_wins=bet_wins+1 WHERE user_id=?", (winner,))
                DB.execute("UPDATE users SET bet_losses=bet_losses+1 WHERE user_id=?", (loser,))
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
                            text=f"🔁 25% Comeback Re-Bet ({rebet_stake} Stars) + 100 Bonus",
                            style=enums.ButtonStyle.SUCCESS,
                            callback_data="rebet_challenge",
                        )
                    ]
                ]
                result_caption = (
                    "<blockquote>💰 <u><b>𝐉𝐔𝐌𝐁𝐋𝐄 𝐁𝐄𝐓 𝐅𝐈𝐆𝐇𝐓 𝐎𝐕𝐄𝐑!</b></u></blockquote>\n\n"
                    f"<blockquote>🏆 <b>Winner (75%) :</b> {game['mentions'][winner]} (+{win_reward} Stars)\n"
                    f"🛡️ <b>Loser Cashback (25%) :</b> {game['mentions'][loser]} (+{loser_cashback} Stars)</blockquote>\n\n"
                    "<blockquote><i>Loser can tap button below to trigger Comeback Duel!</i></blockquote>"
                )
        else:
            add_user_stars(p1, bet_amt)
            add_user_stars(p2, bet_amt)
            result_caption = f"<blockquote>🤝 <b>BET DRAW! Refunded {bet_amt} Stars each.</b></blockquote>"

    await send_jumble_rich(client, chat_id, result_caption, end_buttons)
    if not (is_bet and winner and not is_rebet):
        asyncio.create_task(resume_group_game_loop(client, chat_id))


# ============================================================
# COMMANDS & INVITATION ROUTER (STRICT VALIDATION)
# ============================================================

async def resolve_group_target_user(client: Client, message: Message):
    target_user = None
    if message.reply_to_message and message.reply_to_message.from_user:
        target_user = message.reply_to_message.from_user
    else:
        for arg in message.command[1:]:
            clean_arg = arg.strip()
            if clean_arg.startswith("@") or clean_arg.isdigit():
                try:
                    target_user = await client.get_users(int(clean_arg) if clean_arg.isdigit() else clean_arg)
                    break
                except Exception:
                    pass

    if not target_user:
        return None, "❌ Target player mention ya reply karke tag karein!"

    if target_user.id == message.from_user.id:
        return None, "❌ Aap khud ke sath fight/bet nahi laga sakte!"

    if target_user.is_bot:
        return None, "❌ Bot ke sath fight/bet allowed nahi hai!"

    try:
        chat_member = await client.get_chat_member(message.chat.id, target_user.id)
        if chat_member.status in (enums.ChatMemberStatus.BANNED, enums.ChatMemberStatus.LEFT):
            return None, "❌ Target player is group ka active member nahi hai!"
    except Exception:
        return None, "❌ Yeh player is group me present nahi hai!"

    return target_user, None


@Client.on_message(filters.command(["jumblefight", "fight"]) & filters.group, group=0)
async def jumble_fight_cmd(client: Client, message: Message):
    target_user, err = await resolve_group_target_user(client, message)
    if err:
        return await message.reply_text(err)

    ensure_user(message.from_user)
    ensure_user(target_user)

    key = message.chat.id
    if key in ACTIVE_FIGHTS:
        return await message.reply_text("❌ Is group me fight already chal rahi hai.")

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
    target_user, err = await resolve_group_target_user(client, message)
    if err:
        return await message.reply_text(err)

    amount = 0
    diff = "medium"
    for p in message.command[1:]:
        if p.isdigit() and int(p) >= 100:
            amount = int(p)
        elif p.lower() in ("easy", "medium", "hard"):
            diff = p.lower()

    if amount < 100:
        return await message.reply_text("❌ Minimum bet 100 Stars hai!\nExample: <code>/betfight easy 200 @username</code>")

    ensure_user(message.from_user)
    ensure_user(target_user)

    bal1 = get_user_balance(message.from_user.id)
    bal2 = get_user_balance(target_user.id)

    if bal1 < amount:
        return await message.reply_text(f"❌ Aapke paas kaafi Stars nahi hain! Current Balance: {bal1}")
    if bal2 < amount:
        return await message.reply_text(f"❌ {target_user.first_name} ke paas {amount} Stars nahi hain! Uska Balance: {bal2}")

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

    game = ACTIVE_FIGHTS.get(chat_id)
    if not game or game.get("is_solved"):
        return

    user_id = message.from_user.id
    if user_id not in game["players"]:
        return

    # Check correct answer match
    if message.text.strip().lower() == str(game.get("word", "")).strip().lower():
        game["is_solved"] = True

        if game.get("timer_task") and not game["timer_task"].done():
            try:
                game["timer_task"].cancel()
            except Exception:
                pass

        game["scores"][user_id] += 1

        s = dict(get_settings(chat_id)) if get_settings(chat_id) else {}
        if s.get("auto_delete") and game.get("msg_id"):
            await safe_delete_and_unpin(client, chat_id, game["msg_id"])

        win_msg = await send_jumble_rich(
            client,
            chat_id,
            f"<blockquote>🎯 <b>ROUND {game['round']} SOLVED!</b>\n\n"
            f"👤 <b>Point Scorer :</b> {game['mentions'][user_id]}\n"
            f"✅ <b>Word was :</b> <code>{str(game.get('word', '')).upper()}</code>\n"
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

    if action == "rebet_challenge":
        rebet = REBET_LOBBY.get(chat_id)
        if not rebet:
            return await query.answer("Re-bet session expire ho chuka hai.", show_alert=True)
        if user_id != rebet["original_loser"]:
            return await query.answer("Sirf loser hi comeback challenge bhej sakta hai!", show_alert=True)

        bal = get_user_balance(user_id)
        if bal < rebet["rebet_amount"]:
            return await query.answer(f"Stars balance kam hai! Required: {rebet['rebet_amount']}", show_alert=True)

        await query.answer("Comeback Request Sent! Waiting for Winner to accept...")

        invitation_caption = (
            "<blockquote>🔥 <u><b>COMEBACK RE-BET DUEL OFFERED!</b></u></blockquote>\n\n"
            f"<blockquote>👤 <b>Challenger (Loser):</b> {rebet['loser_mention']}\n"
            f"👑 <b>Target (Winner):</b> {rebet['winner_mention']}\n"
            f"💵 <b>Stake :</b> <code>{rebet['rebet_amount']} Stars</code> (+100 Bonus Pot)\n"
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

    if action == "rebet_accept":
        rebet = REBET_LOBBY.get(chat_id)
        if not rebet:
            return await query.answer("Request expire ho chuki hai.", show_alert=True)
        if user_id != rebet["original_winner"]:
            return await query.answer("Sirf winner hi challenge accept kar sakta hai!", show_alert=True)

        p1_bal = get_user_balance(rebet["original_winner"])
        p2_bal = get_user_balance(rebet["original_loser"])
        req_amt = rebet["rebet_amount"]

        if p1_bal < req_amt or p2_bal < req_amt:
            return await query.answer("Kisi ek player ke paas sufficient stars nahi hain!", show_alert=True)

        deduct_user_stars(rebet["original_winner"], req_amt)
        deduct_user_stars(rebet["original_loser"], req_amt)

        old_g = DB.execute("SELECT message_id FROM games WHERE chat_id=?", (chat_id,)).fetchone()
        if old_g and old_g["message_id"]:
            asyncio.create_task(safe_delete_and_unpin(client, chat_id, old_g["message_id"]))
        DB.execute("DELETE FROM games WHERE chat_id=?", (chat_id,))
        DB.commit()

        ACTIVE_FIGHTS[chat_id] = {
            "players": [rebet["original_winner"], rebet["original_loser"]],
            "names": {rebet["original_winner"]: "Winner", rebet["original_loser"]: "Loser"},
            "mentions": {rebet["original_winner"]: rebet["winner_mention"], rebet["original_loser"]: rebet["loser_mention"]},
            "round": 0,
            "round_token": 0,
            "is_solved": False,
            "timer_task": None,
            "total_rounds": 10,
            "scores": defaultdict(int),
            "word": None,
            "expires": None,
            "difficulty": rebet["difficulty"],
            "timer": rebet["timer"],
            "msg_id": None,
            "is_bet": True,
            "bet_amount": req_amt,
            "is_rebet": True,
        }
        del REBET_LOBBY[chat_id]
        await query.answer(f"Comeback Duel Accepted! {req_amt} Stars Deducted.")
        await query.message.delete()
        asyncio.create_task(fight_next(client, chat_id))
        return

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

    lobby = FIGHT_LOBBY.get(chat_id)
    if not lobby:
        return await query.answer("Duel request expired ya valid nahi hai.", show_alert=True)

    if action == "f_accept":
        if user_id != lobby["p2"]:
            return await query.answer("Sirf challenged player accept kar sakta hai!", show_alert=True)

        if lobby["is_bet"]:
            amt = lobby["bet_amount"]
            b1 = get_user_balance(lobby["p1"])
            b2 = get_user_balance(lobby["p2"])
            if b1 < amt or b2 < amt:
                return await query.answer(f"Balance check failed! Dono ke paas {amt} Stars hone chahiye.", show_alert=True)

            deduct_user_stars(lobby["p1"], amt)
            deduct_user_stars(lobby["p2"], amt)

        old_g = DB.execute("SELECT message_id FROM games WHERE chat_id=?", (chat_id,)).fetchone()
        if old_g and old_g["message_id"]:
            asyncio.create_task(safe_delete_and_unpin(client, chat_id, old_g["message_id"]))
        DB.execute("DELETE FROM games WHERE chat_id=?", (chat_id,))
        DB.commit()

        ACTIVE_FIGHTS[chat_id] = {
            "players": [lobby["p1"], lobby["p2"]],
            "names": {lobby["p1"]: lobby["p1_name"], lobby["p2"]: lobby["p2_name"]},
            "mentions": {lobby["p1"]: lobby["m1"], lobby["p2"]: lobby["m2"]},
            "round": 0,
            "round_token": 0,
            "is_solved": False,
            "timer_task": None,
            "total_rounds": lobby["total_rounds"],
            "scores": defaultdict(int),
            "word": None,
            "expires": None,
            "difficulty": lobby["difficulty"],
            "timer": lobby["timer"],
            "msg_id": None,
            "is_bet": lobby["is_bet"],
            "bet_amount": lobby["bet_amount"],
            "is_rebet": False,
        }
        del FIGHT_LOBBY[chat_id]
        status_txt = f"Duel Accepted! {lobby['bet_amount']} Stars deducted." if lobby["is_bet"] else "Duel Accepted! Starting..."
        await query.answer(status_txt)
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

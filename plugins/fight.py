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
from pyrogram.types import Message
from utils.rich import send_jumble_rich, html_to_rich_blocks
from word_bank import WORDS, jumble_word

FIGHT_LOBBY = {}
REBET_LOBBY = {}


def fight_rich_buttons():
    return [
        [
            types.RichMessageButton(
                text="💡 𝐇ɪɴᴛ",
                style=enums.ButtonStyle.PRIMARY,
                callback_data="fight_hint",
            )
        ]
    ]


async def fight_timeout_task(client: Client, chat_id: int, round_num: int, timer_duration: int):
    await asyncio.sleep(timer_duration)
    should_advance = False
    async with LOCK:
        game = ACTIVE_FIGHTS.get(chat_id)
        if game and game["round"] == round_num:
            word = game["word"]
            s = get_settings(chat_id)
            settings_dict = dict(s) if s else {}
            if settings_dict.get("auto_delete") and game.get("msg_id"):
                await safe_delete_and_unpin(client, chat_id, game["msg_id"])
            try:
                caption = (
                    f"<blockquote><emoji id=5895705279416241926>⏰</emoji> <u><b>𝐑𝐎𝐔𝐍𝐃 {round_num} 𝐓𝐈𝐌𝐄𝐎𝐔𝐓!</b></u></blockquote>\n\n"
                    f"<blockquote expandable>"
                    f"❌ <b>Answer :</b> <code>{word.upper()}</code>\n"
                    f"<emoji id=5974235702701853774>🔄</emoji> <i>Next round starting immediately...</i></blockquote>"
                )
                t_msg = await send_jumble_rich(client, chat_id, caption)
                if settings_dict.get("auto_delete") and t_msg:
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
    image_path = make_puzzle_image(jumbled, f"{fight_tag} {diff.upper()}", game["round"])

    header_icon = "💰" if game.get("is_bet") else "⚔️"
    header_name = "𝐉𝐔𝐌𝐁𝐋𝐄 𝐁𝐄𝐓 𝐅𝐈𝐆𝐇𝐓" if game.get("is_bet") else "𝐉𝐔𝐌𝐁𝐋𝐄 𝐅𝐈𝐆𝐇𝐓"
    extra_info = f"\n💵 <b>𝐁ᴇᴛ:</b> <code>{game.get('bet_amount')} pts</code>" if game.get("is_bet") else ""

    caption = (
        f"<blockquote><emoji id=5895705279416241926>{header_icon}</emoji> <u><b>{header_name} — 𝐑𝐎𝐔𝐍𝐃 {game['round']}/10</b></u></blockquote>\n\n"
        f"<blockquote expandable>"
        f"<emoji id=6066395745139824604>🎯</emoji> <b>𝐃ɪғғɪᴄᴜʟᴛʏ:</b> <code>{diff.title()}</code>\n"
        f"<emoji id=5974235702701853774>⏱️</emoji> <b>𝐓ɪᴍᴇ:</b> <code>{game['timer']}s</code>{extra_info}\n"
        f"<emoji id=5409132617750555920>👥</emoji> <b>Versus:</b> {game['mentions'][game['players'][0]]} 🆚 {game['mentions'][game['players'][1]]}</blockquote>"
    )

    blocks = []
    if image_path and os.path.isfile(str(image_path)):
        try:
            blocks.append(types.InputRichBlockPhoto(photo=types.InputMediaPhoto(str(image_path))))
        except Exception:
            pass

    blocks.extend(html_to_rich_blocks(caption))
    blocks.append(types.InputRichBlockButtons(buttons=fight_rich_buttons()[0]))

    try:
        sent = await client.send_rich_message(
            chat_id=chat_id,
            rich_message=types.InputRichMessage(blocks=blocks)
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
    settings_dict = dict(s) if s else {}
    if settings_dict.get("auto_delete") and game.get("msg_id"):
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

        win_text = f"🏆 <b>Winner:</b> {game['mentions'][winner]} 🎉" if winner else "🤝 <b>Match Draw!</b>"
        result_caption = (
            "<blockquote><emoji id=5895705279416241926>🏁</emoji> <u><b>𝐉𝐔𝐌𝐁𝐋𝐄 𝐅𝐈𝐆𝐇𝐓 𝐎𝐕𝐄𝐑!</b></u></blockquote>\n\n"
            "<blockquote expandable>"
            f"👤 {m1} — <b>{s1} pts</b>\n"
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
                    "<blockquote><emoji id=5895705279416241926>💰</emoji> <u><b>COMEBACK RE-BET OVER!</b></u></blockquote>\n\n"
                    "<blockquote expandable>"
                    f"🏆 <b>Winner:</b> {game['mentions'][winner]} (+{total_pot} pts/stars)\n"
                    f"💀 <b>Loser:</b> {game['mentions'][loser]}</blockquote>"
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
                    "winner_mention": game['mentions'][winner],
                    "loser_mention": game['mentions'][loser]
                }
                end_buttons = [
                    [
                        types.RichMessageButton(
                            text=f"🔁 25% Re-Bet ({rebet_stake} pts) + 100 Bonus",
                            style=enums.ButtonStyle.SUCCESS,
                            callback_data="rebet_challenge",
                        )
                    ]
                ]
                result_caption = (
                    "<blockquote><emoji id=5895705279416241926>💰</emoji> <u><b>𝐉𝐔𝐌𝐁𝐋𝐄 𝐁𝐄𝐓 𝐅𝐈𝐆𝐇𝐓 𝐎𝐕𝐄𝐑!</b></u></blockquote>\n\n"
                    "<blockquote expandable>"
                    f"🏆 <b>Winner (75%):</b> {game['mentions'][winner]} (+{win_reward} pts)\n"
                    f"🛡️ <b>Cashback (25%):</b> {game['mentions'][loser]} (+{loser_cashback} pts)</blockquote>"
                )
        else:
            DB.execute("UPDATE users SET points=points+?, stars=stars+? WHERE user_id=?", (bet_amt, bet_amt, p1))
            DB.execute("UPDATE users SET points=points+?, stars=stars+? WHERE user_id=?", (bet_amt, bet_amt, p2))
            DB.commit()
            result_caption = f"<blockquote><emoji id=5895705279416241926>🤝</emoji> <b>BET DRAW! Refunded {bet_amt} points each.</b></blockquote>"

    await send_jumble_rich(client, chat_id, result_caption, end_buttons)
    await asyncio.sleep(3)
    if settings_dict.get("is_active"):
        asyncio.create_task(start_game(client, chat_id, settings_dict.get("default_diff", "medium"), chat_id))


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

    caption = (
        "<blockquote><emoji id=5895705279416241926>⚔️</emoji> <u><b>JUMBLE FIGHT INVITATION</b></u></blockquote>\n\n"
        "<blockquote expandable>"
        f"<emoji id=5974235702701853774>👤</emoji> <b>Challenger :</b> {m1}\n"
        f"<emoji id=6066395745139824604>🎯</emoji> <b>Opponent :</b> {m2}\n\n"
        "Configure difficulty & timer below, then accept to duel!</blockquote>"
    )

    buttons = [
        [
            types.RichMessageButton(
                text="🟢 Easy",
                style=enums.ButtonStyle.SUCCESS,
                callback_data="f_diff_easy",
            ),
            types.RichMessageButton(
                text="🟡 Medium",
                style=enums.ButtonStyle.PRIMARY,
                callback_data="f_diff_medium",
            ),
            types.RichMessageButton(
                text="🔴 Hard",
                style=enums.ButtonStyle.DANGER,
                callback_data="f_diff_hard",
            ),
        ],
        [
            types.RichMessageButton(
                text="⏱️ 30s",
                style=enums.ButtonStyle.DEFAULT,
                callback_data="f_time_30",
            ),
            types.RichMessageButton(
                text="⏱️ 45s",
                style=enums.ButtonStyle.DEFAULT,
                callback_data="f_time_45",
            ),
            types.RichMessageButton(
                text="⏱️ 60s",
                style=enums.ButtonStyle.DEFAULT,
                callback_data="f_time_60",
            ),
        ],
        [
            types.RichMessageButton(
                text="✅ Accept Challenge",
                style=enums.ButtonStyle.SUCCESS,
                callback_data="f_accept",
            ),
            types.RichMessageButton(
                text="❌ Decline",
                style=enums.ButtonStyle.DANGER,
                callback_data="f_decline",
            ),
        ],
    ]

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
        "is_bet": True,
        "bet_amount": amount,
        "is_rebet": False
    }

    caption = (
        "<blockquote><emoji id=5895705279416241926>💰</emoji> <u><b>HIGH STAKES BET FIGHT</b></u></blockquote>\n\n"
        "<blockquote expandable>"
        f"<emoji id=5974235702701853774>👤</emoji> <b>Challenger :</b> {m1}\n"
        f"<emoji id=6066395745139824604>🎯</emoji> <b>Opponent :</b> {m2}\n"
        f"💵 <b>Bet Amount :</b> <code>{amount} Points / Stars</code>\n"
        f"🎯 <b>Difficulty :</b> <code>{diff.title()}</code></blockquote>"
    )

    buttons = [
        [
            types.RichMessageButton(
                text="✅ Accept Bet",
                style=enums.ButtonStyle.SUCCESS,
                callback_data="f_accept",
            ),
            types.RichMessageButton(
                text="❌ Decline",
                style=enums.ButtonStyle.DANGER,
                callback_data="f_decline",
            ),
        ]
    ]

    await send_jumble_rich(client, message.chat.id, caption, buttons)

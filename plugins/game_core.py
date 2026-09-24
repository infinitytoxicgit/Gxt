import asyncio
import io
import os
import random
import time
from database import DB, get_settings, get_global_config, ensure_user
from helpers import safe_delete_and_unpin, delete_after, is_admin_or_owner
from image_gen import make_puzzle_image
from pyrogram import Client, filters, enums, types
from pyrogram.types import CallbackQuery, Message
from word_bank import choose_word, jumble_word
from utils.rich import html_to_rich_blocks

ACTIVE_FIGHTS = {}


def rich_game_buttons(puzzle_id: int):
    return [
        types.InputRichBlockButtons(
            buttons=[
                types.RichMessageButton(
                    text="💡 𝐇ɪɴᴛ",
                    style=enums.ButtonStyle.PRIMARY,
                    callback_data=f"game_hint|{puzzle_id}",
                ),
                types.RichMessageButton(
                    text="⏭️ 𝐒ᴋɪᴘ",
                    style=enums.ButtonStyle.DANGER,
                    callback_data=f"game_skip|{puzzle_id}",
                ),
            ]
        ),
        types.InputRichBlockButtons(
            buttons=[
                types.RichMessageButton(
                    text="🆕 𝐍ᴇᴡ 𝐖ᴏʀᴅ",
                    style=enums.ButtonStyle.SUCCESS,
                    callback_data="game_newword",
                ),
            ]
        ),
    ]


async def start_game(client: Client, chat_id: int, difficulty: str, message_or_chat):
    if chat_id in ACTIVE_FIGHTS:
        return

    raw_settings = get_settings(chat_id)
    settings = dict(raw_settings) if raw_settings else {}
    if not settings.get("is_active", 1):
        return

    old_game = DB.execute("SELECT message_id FROM games WHERE chat_id=?", (chat_id,)).fetchone()
    if old_game and settings.get("auto_delete") and old_game["message_id"]:
        await safe_delete_and_unpin(client, chat_id, old_game["message_id"])

    DB.execute("DELETE FROM games WHERE chat_id=?", (chat_id,))

    word = choose_word(chat_id, difficulty)
    jumbled = jumble_word(word)
    puzzle_id = random.randint(10000, 99999)
    now = time.time()
    timer_val = int(settings.get(difficulty, 120))
    reward_pts = int(get_global_config(f"points_{difficulty}", 10))
    reward_exp = int(get_global_config(f"exp_{difficulty}", 15))
    hint_limit = int(get_global_config(f"hints_{difficulty}", 3))
    expires = now + timer_val

    DB.execute("""
        INSERT INTO games(chat_id, difficulty, word, puzzle_id, started, expires, message_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (chat_id, difficulty, word, puzzle_id, now, expires, 0))
    DB.commit()

    image_obj = make_puzzle_image(jumbled, difficulty, puzzle_id)

    # Clean Non-Expandable Blockquote
    caption_html = (
        f"<blockquote>🧩 <b>𝐉ᴜᴍʙʟᴇ #{puzzle_id}</b>\n\n"
        f"🎯 <b>Difficulty :</b> <code>{difficulty.title()}</code>\n"
        f"⏱️ <b>Time :</b> <code>{timer_val // 60}m {timer_val % 60}s</code>\n"
        f"⭐ <b>Reward :</b> <code>+{reward_pts} Points</code>\n"
        f"⚡ <b>EXP :</b> <code>+{reward_exp} EXP</code>\n"
        f"💡 <b>Hints :</b> <code>{hint_limit}/word</code></blockquote>\n\n"
        f"<blockquote>🔀 <i>Unscramble the letters & type in chat!</i></blockquote>"
    )

    blocks = []
    if image_obj:
        try:
            if isinstance(image_obj, str) and os.path.isfile(image_obj):
                blocks.append(types.InputRichBlockPhoto(photo=types.InputMediaPhoto(image_obj)))
            elif hasattr(image_obj, "read"):
                tmp_path = f"tmp_puzzle_{puzzle_id}.png"
                if hasattr(image_obj, "seek"):
                    image_obj.seek(0)
                with open(tmp_path, "wb") as f:
                    f.write(image_obj.read())
                blocks.append(types.InputRichBlockPhoto(photo=types.InputMediaPhoto(tmp_path)))
        except Exception as err:
            print(f"Photo Block Error: {err}")

    blocks.extend(html_to_rich_blocks(caption_html))
    blocks.extend(rich_game_buttons(puzzle_id))

    try:
        sent = await client.send_rich_message(
            chat_id=chat_id,
            rich_message=types.InputRichMessage(blocks=blocks)
        )
        DB.execute("UPDATE games SET message_id=? WHERE chat_id=?", (sent.id, chat_id))
        DB.commit()
        try:
            await sent.pin(disable_notification=True)
        except Exception:
            pass
    except Exception as e:
        print(f"Error sending rich puzzle: {e}")

    asyncio.create_task(expire_game(client, chat_id, puzzle_id, expires))


async def expire_game(client: Client, chat_id: int, puzzle_id: int, expires: float):
    await asyncio.sleep(max(0, expires - time.time()))
    if chat_id in ACTIVE_FIGHTS:
        return

    row = DB.execute("SELECT * FROM games WHERE chat_id=? AND puzzle_id=?", (chat_id, puzzle_id)).fetchone()
    if not row or row["solved"]:
        return

    DB.execute("UPDATE games SET solved=1 WHERE chat_id=?", (chat_id,))
    DB.commit()

    raw_s = get_settings(chat_id)
    s = dict(raw_s) if raw_s else {}
    if s.get("auto_delete") and row["message_id"]:
        await safe_delete_and_unpin(client, chat_id, row["message_id"])

    try:
        expire_caption = (
            f"<blockquote>⏰ <b>Time's Up!</b>\n\n"
            f"❌ <b>Nobody solved it.</b>\n"
            f"✅ <b>Answer was:</b> <code>{row['word'].upper()}</code>\n\n"
            f"🔄 <i>Next puzzle starting in 3 seconds...</i></blockquote>"
        )
        exp_blocks = html_to_rich_blocks(expire_caption)
        exp_msg = await client.send_rich_message(
            chat_id=chat_id,
            rich_message=types.InputRichMessage(blocks=exp_blocks)
        )
        if s.get("auto_delete") and exp_msg:
            asyncio.create_task(delete_after(exp_msg, 4))
    except Exception:
        pass

    await asyncio.sleep(3)
    s = dict(get_settings(chat_id)) if get_settings(chat_id) else {}
    if chat_id not in ACTIVE_FIGHTS and s.get("is_active", 1):
        next_diff = s.get("default_diff") or "medium"
        asyncio.create_task(start_game(client, chat_id, next_diff, chat_id))


# ============================================================
# SOLVE DETECTOR (2x Boosters, Timeframe Tracking & Fast Spawning)
# ============================================================

@Client.on_message(filters.text & filters.group, group=1)
async def check_answer_handler(client: Client, message: Message):
    if not message.text or message.text.startswith("/"):
        return

    chat_id = message.chat.id
    if chat_id in ACTIVE_FIGHTS:
        return

    game = DB.execute("SELECT * FROM games WHERE chat_id=? AND solved=0", (chat_id,)).fetchone()
    if not game:
        return

    user_ans = message.text.strip().lower()
    correct_word = game["word"].strip().lower()

    if user_ans == correct_word:
        DB.execute("UPDATE games SET solved=1 WHERE chat_id=?", (chat_id,))
        DB.commit()

        user = message.from_user
        ensure_user(user)

        diff = game["difficulty"]
        base_pts = int(get_global_config(f"points_{diff}", 10))
        base_exp = int(get_global_config(f"exp_{diff}", 15))

        # Check Active Power-up Boosters
        now = time.time()
        active_powers = DB.execute(
            "SELECT power_type FROM user_powers WHERE user_id=? AND expires_at > ?",
            (user.id, now)
        ).fetchall()
        power_types = [p["power_type"] for p in active_powers]

        has_2x_stars = "2x_stars" in power_types
        has_2x_exp = "2x_exp" in power_types

        reward_pts = base_pts * 2 if has_2x_stars else base_pts
        reward_exp = base_exp * 2 if has_2x_exp else base_exp

        # User stats update
        diff_col = f"{diff}_solved"
        DB.execute(f"""
            UPDATE users SET 
                solved = solved + 1,
                {diff_col} = {diff_col} + 1,
                points = points + ?,
                stars = stars + ?,
                exp = exp + ?,
                streak = streak + 1,
                best_streak = MAX(best_streak, streak + 1)
            WHERE user_id = ?
        """, (reward_pts, reward_pts, reward_exp, user.id))

        # Solve history update for 24h, weekly, monthly, and yearly leaderboards
        DB.execute(
            "INSERT INTO solve_history (user_id, chat_id, points, timestamp) VALUES (?, ?, ?, ?)",
            (user.id, chat_id, reward_pts, now)
        )
        DB.commit()

        booster_badge = ""
        if has_2x_stars or has_2x_exp:
            badges = []
            if has_2x_stars:
                badges.append("⭐ 2x Stars")
            if has_2x_exp:
                badges.append("⚡ 2x EXP")
            booster_badge = f"\n🔥 <b>Active Boosters:</b> {' | '.join(badges)}"

        win_caption = (
            f"<blockquote>🎉 <b>PUZZLE SOLVED!</b>\n\n"
            f"👤 <b>Solver :</b> {user.mention}\n"
            f"✅ <b>Word :</b> <code>{correct_word.upper()}</code>\n"
            f"⭐ <b>Stars Earned :</b> <code>+{reward_pts}</code>\n"
            f"⚡ <b>EXP Gained :</b> <code>+{reward_exp}</code>"
            f"{booster_badge}\n\n"
            f"🔄 <i>Next puzzle starting in 2 seconds...</i></blockquote>"
        )

        raw_s = get_settings(chat_id)
        s = dict(raw_s) if raw_s else {}
        if s.get("auto_delete") and game["message_id"]:
            await safe_delete_and_unpin(client, chat_id, game["message_id"])

        win_blocks = html_to_rich_blocks(win_caption)
        win_msg = await client.send_rich_message(
            chat_id=chat_id,
            rich_message=types.InputRichMessage(blocks=win_blocks)
        )
        if s.get("auto_delete") and win_msg:
            asyncio.create_task(delete_after(win_msg, 5))

        await asyncio.sleep(2)
        if s.get("is_active", 1):
            next_diff = s.get("default_diff") or "medium"
            asyncio.create_task(start_game(client, chat_id, next_diff, chat_id))


# ============================================================
# BUTTON CALLBACKS (HINT / SKIP / NEW WORD)
# ============================================================

@Client.on_callback_query(filters.regex(r"^(game_hint|game_skip|game_newword|hint|skip|newword)"))
async def puzzle_buttons_listener(client: Client, query: CallbackQuery):
    chat_id = query.message.chat.id
    user_id = query.from_user.id
    data = query.data.split("|")
    action = data[0]

    # 1. HINT
    if action in ["game_hint", "hint"]:
        ensure_user(query.from_user)
        game = DB.execute("SELECT * FROM games WHERE chat_id=? AND solved=0", (chat_id,)).fetchone()
        if not game:
            return await query.answer("❌ Active puzzle nahi mila!", show_alert=True)

        puzzle_id = game["puzzle_id"]
        word = game["word"]
        difficulty = game["difficulty"]

        hint_limit = int(get_global_config(f"hints_{difficulty}", 3))
        hint_row = DB.execute("SELECT * FROM puzzle_hints WHERE chat_id=? AND puzzle_id=? AND user_id=?", (chat_id, puzzle_id, user_id)).fetchone()
        hints_used = hint_row["hints_used"] if hint_row else 0
        revealed_indices = [int(i) for i in hint_row["revealed_indices"].split(",") if i] if hint_row else []

        if hints_used >= hint_limit:
            return await query.answer(f"❌ Is puzzle ke aapke {hint_limit} hints pure ho gaye!", show_alert=True)

        avail = [i for i in range(len(word)) if i not in revealed_indices]
        if not avail:
            return await query.answer("❌ Saare letters already open hain!", show_alert=True)

        idx = random.choice(avail)
        revealed_indices.append(idx)
        hints_used += 1

        DB.execute("""
            INSERT INTO puzzle_hints(chat_id, puzzle_id, user_id, hints_used, revealed_indices)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(chat_id, puzzle_id, user_id) DO UPDATE SET
                hints_used=excluded.hints_used,
                revealed_indices=excluded.revealed_indices
        """, (chat_id, puzzle_id, user_id, hints_used, ",".join(map(str, revealed_indices))))
        DB.commit()

        letter = word[idx].upper()
        return await query.answer(f"💡 Letter #{idx + 1} is: '{letter}' ({hint_limit - hints_used} hints left)", show_alert=True)

    # 2. SKIP (Admins / Owner Only)
    elif action in ["game_skip", "skip"]:
        is_adm = await is_admin_or_owner(query.message.chat, user_id)
        if not is_adm:
            return await query.answer("❌ Sirf Group Admins hi puzzle skip kar sakte hain!", show_alert=True)

        game = DB.execute("SELECT * FROM games WHERE chat_id=? AND solved=0", (chat_id,)).fetchone()
        if not game:
            return await query.answer("❌ Koi active puzzle nahi hai!", show_alert=True)

        DB.execute("UPDATE games SET solved=1 WHERE chat_id=?", (chat_id,))
        DB.commit()

        raw_s = get_settings(chat_id)
        s = dict(raw_s) if raw_s else {}
        if s.get("auto_delete") and game["message_id"]:
            await safe_delete_and_unpin(client, chat_id, game["message_id"])

        await query.answer("⏭️ Puzzle skipped successfully!")

        skip_caption = (
            f"<blockquote>⏭️ <b>Puzzle Skipped by Admin!</b>\n\n"
            f"✅ <b>Word was:</b> <code>{game['word'].upper()}</code>\n"
            f"🔄 <i>Next puzzle starting in 3 seconds...</i></blockquote>"
        )
        exp_blocks = html_to_rich_blocks(skip_caption)
        msg = await client.send_rich_message(
            chat_id=chat_id,
            rich_message=types.InputRichMessage(blocks=exp_blocks)
        )
        if s.get("auto_delete") and msg:
            asyncio.create_task(delete_after(msg, 4))

        await asyncio.sleep(3)
        if s.get("is_active", 1):
            next_diff = s.get("default_diff") or "medium"
            asyncio.create_task(start_game(client, chat_id, next_diff, chat_id))

    # 3. NEW WORD
    elif action in ["game_newword", "newword"]:
        game = DB.execute("SELECT * FROM games WHERE chat_id=? AND solved=0", (chat_id,)).fetchone()
        if game and time.time() <= game["expires"]:
            return await query.answer("❌ Current puzzle chal raha hai! Pehle solve ya skip karein.", show_alert=True)

        await query.answer("🧩 Naya puzzle shuru kiya ja raha hai...")
        raw_s = get_settings(chat_id)
        s = dict(raw_s) if raw_s else {}
        next_diff = s.get("default_diff") or "medium"
        asyncio.create_task(start_game(client, chat_id, next_diff, chat_id))

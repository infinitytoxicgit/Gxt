import asyncio
import io
import os
import random
import time
from database import DB, get_settings, get_global_config, ensure_user, is_admin
from helpers import safe_delete_and_unpin, delete_after
from image_gen import make_puzzle_image
from pyrogram import Client, filters, enums, types
from pyrogram.types import CallbackQuery
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
                    callback_data="game_skip",
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
    timer_val = settings.get(difficulty, 120)
    reward_pts = get_global_config(f"points_{difficulty}", 10)
    reward_exp = get_global_config(f"exp_{difficulty}", 15)
    hint_limit = get_global_config(f"hints_{difficulty}", 3)
    expires = now + timer_val

    DB.execute("""
        INSERT INTO games(chat_id, difficulty, word, puzzle_id, started, expires, message_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (chat_id, difficulty, word, puzzle_id, now, expires, 0))
    DB.commit()

    # Image generate karna (File path ya BytesIO)
    image_obj = make_puzzle_image(jumbled, difficulty, puzzle_id)

    caption_html = (
        f"<blockquote><emoji id=5895705279416241926>🧩</emoji> <u><b>𝐉ᴜᴍʙʟᴇ #{puzzle_id}</b></u></blockquote>\n\n"
        f"<blockquote expandable>"
        f"<emoji id=6066395745139824604>🎯</emoji> <b>𝐃ɪғғɪᴄᴜʟᴛʏ:</b> <code>{difficulty.title()}</code>\n"
        f"<emoji id=5974235702701853774>⏱️</emoji> <b>𝐓ɪᴍᴇ:</b> <code>{timer_val // 60}m {timer_val % 60}s</code>\n"
        f"⭐ <b>𝐑ᴇᴡᴀʀᴅ:</b> <code>+{reward_pts} Points</code>\n"
        f"<emoji id=5409132617750555920>⚡</emoji> <b>𝐄𝐗𝐏:</b> <code>+{reward_exp} EXP</code>\n"
        f"💡 <b>𝐇ɪɴᴛs:</b> <code>{hint_limit}/word</code></blockquote>\n\n"
        f"<blockquote>🔀 <i>𝐔ɴsᴄʀᴀᴍʙʟᴇ ᴛʜᴇ ʟᴇᴛᴛᴇʀs & ᴛʏᴘᴇ ɪɴ ᴄʜᴀᴛ!</i></blockquote>"
    )

    blocks = []
    
    # 1. Photo attach logic (Robust for path and buffer)
    if image_obj:
        try:
            if isinstance(image_obj, str) and os.path.isfile(image_obj):
                blocks.append(types.InputRichBlockPhoto(photo=types.InputMediaPhoto(image_obj)))
            elif hasattr(image_obj, "read"):
                # Agar buffer ho toh temporarily save karke block me daalna
                tmp_path = f"tmp_puzzle_{puzzle_id}.png"
                if hasattr(image_obj, "seek"):
                    image_obj.seek(0)
                with open(tmp_path, "wb") as f:
                    f.write(image_obj.read())
                blocks.append(types.InputRichBlockPhoto(photo=types.InputMediaPhoto(tmp_path)))
        except Exception as err:
            print(f"Photo Block Error: {err}")

    # 2. Text aur Rich Buttons attach karna
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
            f"<blockquote><emoji id=5895705279416241926>⏰</emoji> <u><b>𝐓ɪᴍᴇ's 𝐔ᴘ!</b></u></blockquote>\n\n"
            f"<blockquote expandable>"
            f"❌ <b>𝐍ᴏʙᴏᴅʏ sᴏʟᴠᴇᴅ ɪᴛ.</b>\n"
            f"✅ <b>𝐀ɴsᴡᴇʀ:</b> <code>{row['word'].upper()}</code>\n\n"
            f"<emoji id=5974235702701853774>🔄</emoji> <i>𝐍ᴇxᴛ ᴘᴜᴢᴢʟᴇ sᴛᴀʀᴛɪɴɢ ɪɴ 3 sᴇᴄᴏɴᴅs...</i></blockquote>"
        )
        exp_blocks = html_to_rich_blocks(expire_caption)
        exp_msg = await client.send_rich_message(
            chat_id=chat_id,
            rich_message=types.InputRichMessage(blocks=exp_blocks)
        )
        if s.get("auto_delete"):
            asyncio.create_task(delete_after(exp_msg, 4))
    except Exception:
        pass

    await asyncio.sleep(3)
    s = dict(get_settings(chat_id)) if get_settings(chat_id) else {}
    if chat_id not in ACTIVE_FIGHTS and s.get("is_active", 1):
        next_diff = s.get("default_diff") or "medium"
        asyncio.create_task(start_game(client, chat_id, next_diff, chat_id))


# ============================================================
# BUTTON CALLBACK HANDLERS (HINT, SKIP, NEW WORD)
# ============================================================

@Client.on_callback_query(filters.regex(r"^(game_hint|game_skip|game_newword|hint|skip|newword)"))
async def puzzle_buttons_listener(client: Client, query: CallbackQuery):
    chat_id = query.message.chat.id
    user_id = query.from_user.id
    data = query.data

    # 1. HINT BUTTON
    if data.startswith("game_hint") or data == "hint":
        ensure_user(query.from_user)
        game = DB.execute("SELECT * FROM games WHERE chat_id=? AND solved=0", (chat_id,)).fetchone()
        if not game:
            return await query.answer("❌ Active puzzle nahi mila!", show_alert=True)

        puzzle_id = game["puzzle_id"]
        word = game["word"]
        difficulty = game["difficulty"]

        hint_limit = get_global_config(f"hints_{difficulty}", 3)
        hint_row = DB.execute("SELECT * FROM puzzle_hints WHERE chat_id=? AND puzzle_id=? AND user_id=?", (chat_id, puzzle_id, user_id)).fetchone()
        hints_used = hint_row["hints_used"] if hint_row else 0
        revealed_indices = [int(i) for i in hint_row["revealed_indices"].split(",") if i] if hint_row else []

        if hints_used >= hint_limit:
            return await query.answer(f"❌ Is puzzle ke {hint_limit} hints pure ho chuke hain!", show_alert=True)

        avail = [i for i in range(len(word)) if i not in revealed_indices]
        if not avail:
            return await query.answer("❌ Saare letters already reveal ho chuke hain.", show_alert=True)

        chosen = random.choice(avail)
        revealed_indices.append(chosen)
        hints_used += 1

        DB.execute("""
            INSERT INTO puzzle_hints(chat_id, puzzle_id, user_id, hints_used, revealed_indices)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(chat_id, puzzle_id, user_id) DO UPDATE SET
                hints_used=excluded.hints_used,
                revealed_indices=excluded.revealed_indices
        """, (chat_id, puzzle_id, user_id, hints_used, ",".join(map(str, revealed_indices))))
        DB.commit()

        letter = word[chosen].upper()
        return await query.answer(f"💡 Letter #{chosen + 1} is '{letter}'\nHints Left: {hint_limit - hints_used}/{hint_limit}", show_alert=True)

    # 2. SKIP BUTTON
    elif data == "game_skip" or data == "skip":
        if not await is_admin(chat_id, user_id):
            return await query.answer("❌ Sirf group admins skip kar sakte hain!", show_alert=True)

        game = DB.execute("SELECT * FROM games WHERE chat_id=? AND solved=0", (chat_id,)).fetchone()
        if not game:
            return await query.answer("Active puzzle nahi hai!", show_alert=True)

        DB.execute("UPDATE games SET solved=1 WHERE chat_id=?", (chat_id,))
        DB.commit()

        raw_s = get_settings(chat_id)
        s = dict(raw_s) if raw_s else {}
        if s.get("auto_delete") and game["message_id"]:
            await safe_delete_and_unpin(client, chat_id, game["message_id"])

        await query.answer("⏭️ Puzzle skipped!")
        
        skip_caption = (
            f"<blockquote><emoji id=5895705279416241926>⏭️</emoji> <u><b>𝐒ᴋɪᴘᴘᴇᴅ!</b></u></blockquote>\n\n"
            f"<blockquote expandable>"
            f"✅ <b>Word was :</b> <code>{game['word'].upper()}</code>\n"
            f"<emoji id=5974235702701853774>🔄</emoji> <i>Next puzzle starting in 3 seconds...</i></blockquote>"
        )
        blocks = html_to_rich_blocks(skip_caption)
        msg = await client.send_rich_message(
            chat_id=chat_id,
            rich_message=types.InputRichMessage(blocks=blocks)
        )
        if s.get("auto_delete") and msg:
            asyncio.create_task(delete_after(msg, 4))

        await asyncio.sleep(3)
        if s.get("is_active", 1):
            next_diff = s.get("default_diff") or "medium"
            asyncio.create_task(start_game(client, chat_id, next_diff, chat_id))

    # 3. NEW WORD BUTTON
    elif data == "game_newword" or data == "newword":
        game = DB.execute("SELECT * FROM games WHERE chat_id=? AND solved=0", (chat_id,)).fetchone()
        if game and time.time() <= game["expires"]:
            return await query.answer("❌ Current puzzle abhi active hai, pehle ise solve ya skip karein!", show_alert=True)

        await query.answer("🧩 Loading new word...")
        raw_s = get_settings(chat_id)
        s = dict(raw_s) if raw_s else {}
        next_diff = s.get("default_diff") or "medium"
        asyncio.create_task(start_game(client, chat_id, next_diff, chat_id))

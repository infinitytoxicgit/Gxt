import asyncio
import os
import random
import time
from database import DB, get_settings, get_global_config, ensure_user
from helpers import safe_delete_and_unpin, delete_after
from image_gen import make_puzzle_image
from pyrogram import Client, enums, types
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
                    callback_data="hint",
                ),
                types.RichMessageButton(
                    text="⏭️ 𝐒ᴋɪᴘ",
                    style=enums.ButtonStyle.DANGER,
                    callback_data="skip",
                ),
            ]
        ),
        types.InputRichBlockButtons(
            buttons=[
                types.RichMessageButton(
                    text="🆕 𝐍ᴇᴡ 𝐖ᴏʀᴅ",
                    style=enums.ButtonStyle.SUCCESS,
                    callback_data="newword",
                ),
            ]
        ),
    ]


async def start_game(client: Client, chat_id: int, difficulty: str, message_or_chat):
    if chat_id in ACTIVE_FIGHTS:
        return

    settings = get_settings(chat_id)
    if not settings["is_active"]:
        return

    old_game = DB.execute("SELECT message_id FROM games WHERE chat_id=?", (chat_id,)).fetchone()
    if old_game and settings["auto_delete"] and old_game["message_id"]:
        await safe_delete_and_unpin(client, chat_id, old_game["message_id"])

    DB.execute("DELETE FROM games WHERE chat_id=?", (chat_id,))

    word = choose_word(chat_id, difficulty)
    jumbled = jumble_word(word)
    puzzle_id = random.randint(10000, 99999)
    now = time.time()
    timer_val = settings[difficulty]
    reward_pts = get_global_config(f"points_{difficulty}", 10)
    reward_exp = get_global_config(f"exp_{difficulty}", 15)
    hint_limit = get_global_config(f"hints_{difficulty}", 3)
    expires = now + timer_val

    DB.execute("""
        INSERT INTO games(chat_id, difficulty, word, puzzle_id, started, expires, message_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (chat_id, difficulty, word, puzzle_id, now, expires, 0))
    DB.commit()

    image_path = make_puzzle_image(jumbled, difficulty, puzzle_id)

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
    if image_path and os.path.isfile(str(image_path)):
        try:
            blocks.append(types.InputRichBlockPhoto(photo=types.InputMediaPhoto(str(image_path))))
        except Exception:
            pass

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

    s = get_settings(chat_id)
    if s["auto_delete"] and row["message_id"]:
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
        if s["auto_delete"]:
            asyncio.create_task(delete_after(exp_msg, 4))
    except Exception:
        pass

    await asyncio.sleep(3)
    s = get_settings(chat_id)
    if chat_id not in ACTIVE_FIGHTS and s["is_active"]:
        next_diff = s["default_diff"] or "medium"
        asyncio.create_task(start_game(client, chat_id, next_diff, chat_id))

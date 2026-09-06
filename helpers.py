import asyncio
import html
from config import OWNER_ID, LOG_CHANNEL
from database import DB, get_global_config
from pyrogram import Client
from pyrogram.enums import ChatType, ChatMemberStatus, ParseMode
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

LOCK = asyncio.Lock()

def is_owner(user_id):
    return int(user_id) == int(OWNER_ID) if user_id else False

def is_authed(user_id):
    if not user_id:
        return False
    if is_owner(user_id):
        return True
    row = DB.execute("SELECT user_id FROM auth_users WHERE user_id=?", (int(user_id),)).fetchone()
    return bool(row)

async def is_admin_or_owner(chat, user_id):
    if is_owner(user_id):
        return True
    if chat.type in (ChatType.PRIVATE,):
        return True
    try:
        member = await chat.get_member(user_id)
        return member.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)
    except Exception:
        return False

def is_group(message: Message):
    return message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)

def get_mention(user_obj=None, user_id=None, first_name=None, username=None):
    if user_obj:
        u_id = user_obj.id
        f_name = user_obj.first_name or "Player"
        u_name = user_obj.username
    else:
        u_id = user_id
        f_name = first_name or "Player"
        u_name = username

    clean_name = html.escape(str(f_name))
    if u_name:
        return f"<a href='https://t.me/{u_name}'>{clean_name}</a>"
    return f"<a href='tg://openmessage?user_id={u_id}'>{clean_name}</a>"

def clean_answer(text):
    return "".join(c.lower() for c in str(text) if c.isalnum())

async def delete_after(msg: Message, delay: int = 5):
    await asyncio.sleep(delay)
    try:
        await msg.delete()
    except Exception:
        pass

async def safe_delete_and_unpin(client, chat_id: int, message_id: int):
    if not message_id:
        return
    try:
        await client.unpin_chat_message(chat_id, message_id)
    except Exception:
        pass
    try:
        await client.delete_messages(chat_id, message_id)
    except Exception:
        pass

async def send_log_event(client: Client, user, chat, word: str, raw_guess: str, points: int, diff: str):
    if not get_global_config("logging_enabled", 1):
        return

    chat_title = html.escape(chat.title or "Unknown Group")
    user_mention = get_mention(user)

    buttons = []
    # Row 1: Profile link via tg://openmessage
    buttons.append([InlineKeyboardButton(f"👤 {user.first_name} ({user.id})", url=f"tg://openmessage?user_id={user.id}")])

    # Row 2: Public or Private group link
    group_row = []
    if chat.username:
        group_row.append(InlineKeyboardButton("🌐 Public Group", url=f"https://t.me/{chat.username}"))
    try:
        invite_link = await client.export_chat_invite_link(chat.id)
        group_row.append(InlineKeyboardButton("🔒 Private Link", url=invite_link))
    except Exception:
        pass

    if group_row:
        buttons.append(group_row)

    log_text = (
        "<blockquote>📝 <b>𝐉𝐔𝐌𝐁𝐋𝐄 𝐆𝐔𝐄𝐒𝐒 𝐋𝐎𝐆</b>\n\n"
        f"👤 <b>User:</b> {user_mention} (<code>{user.id}</code>)\n"
        f"👥 <b>Group:</b> <b>{chat_title}</b> (<code>{chat.id}</code>)\n"
        f"🧩 <b>Correct Word:</b> <code>{word.upper()}</code>\n"
        f"💬 <b>Guessed Text:</b> <code>{raw_guess}</code>\n"
        f"🎯 <b>Difficulty:</b> <code>{diff.title()}</code>\n"
        f"⭐ <b>Points Awarded:</b> <code>+{points} pts</code></blockquote>"
    )

    try:
        await client.send_message(
            chat_id=LOG_CHANNEL,
            text=log_text,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        print(f"Log Error: {e}")

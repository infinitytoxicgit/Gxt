import asyncio
import html
import time
from config import OWNER_ID, LOG_CHANNEL
from database import DB, get_global_config
from pyrogram import Client
from pyrogram.enums import ChatType, ChatMemberStatus, ParseMode
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

LOCK = asyncio.Lock()

# Central shared state across all game loops, plugins, and duel systems
ACTIVE_FIGHTS = {}


def is_owner(user_id):
    try:
        return int(user_id) == int(OWNER_ID) if user_id else False
    except Exception:
        return False


def is_authed(user_id):
    if not user_id:
        return False
    if is_owner(user_id):
        return True
    try:
        row = DB.execute("SELECT user_id FROM auth_users WHERE user_id=?", (int(user_id),)).fetchone()
        return bool(row)
    except Exception:
        return False


async def is_admin_or_owner(chat, user_id, client=None):
    if not user_id:
        return False

    if is_owner(user_id) or is_authed(user_id):
        return True

    if isinstance(chat, (int, str)):
        chat_id = chat
        is_priv = False
    else:
        chat_id = getattr(chat, "id", None)
        is_priv = (getattr(chat, "type", None) == ChatType.PRIVATE)

    if is_priv:
        return True

    if not chat_id:
        return False

    try:
        if client:
            member = await client.get_chat_member(chat_id, user_id)
            return member.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)
        elif hasattr(chat, "get_chat_member"):
            member = await chat.get_chat_member(user_id)
            return member.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)
    except Exception:
        pass

    return False


def is_group(message: Message):
    if not message or not message.chat:
        return False
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
    return f"<a href='tg://user?id={u_id}'>{clean_name}</a>"


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


async def safe_pin_and_clean(client, chat_id: int, message_id: int):
    if not message_id:
        return
    try:
        pin_res = await client.pin_chat_message(chat_id, message_id, disable_notification=True)
        if pin_res and hasattr(pin_res, "id") and pin_res.id != message_id:
            try:
                await client.delete_messages(chat_id, pin_res.id)
            except Exception:
                pass
    except Exception:
        pass


def _fetch_user_full_stats(user_id: int):
    data = {
        "balance": 0,
        "total_solved": 0,
        "easy_solved": 0,
        "med_solved": 0,
        "hard_solved": 0
    }
    try:
        u = DB.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        if u:
            u_dict = dict(u) if hasattr(u, "keys") else {}
            # Fallback if tuple
            if not u_dict and isinstance(u, (list, tuple)):
                data["balance"] = u[2] if len(u) > 2 else 0
            else:
                data["balance"] = u_dict.get("stars", 0) if u_dict.get("stars", 0) > 0 else u_dict.get("points", 0)
                data["total_solved"] = u_dict.get("correct", 0)
                data["easy_solved"] = u_dict.get("easy_correct", 0)
                data["med_solved"] = u_dict.get("medium_correct", 0)
                data["hard_solved"] = u_dict.get("hard_correct", 0)
    except Exception:
        pass
    return data


# ============================================================
# 1. PUZZLE SOLVED LOG (A-to-Z Stats, Balance Transition & Mode)
# ============================================================
async def send_log_event(client: Client, user, chat, word: str, raw_guess: str, points: int, diff: str, old_balance: int = None):
    if not LOG_CHANNEL or not get_global_config("logging_enabled", 1):
        return

    try:
        u_stats = _fetch_user_full_stats(user.id)
        current_bal = u_stats["balance"]
        
        if old_balance is None:
            old_balance = max(0, current_bal - points)
        new_balance = old_balance + points

        chat_title = html.escape(getattr(chat, "title", "Direct Message") or "Chat")
        chat_id = getattr(chat, "id", 0)
        user_mention = get_mention(user)

        buttons = [
            [InlineKeyboardButton(f"👤 {user.first_name} ({user.id})", url=f"tg://user?id={user.id}")],
        ]
        if getattr(chat, "username", None):
            buttons.append([InlineKeyboardButton("🏰 Group Chat", url=f"https://t.me/{chat.username}")])

        diff_emoji = "🟢" if diff.lower() == "easy" else "🟡" if diff.lower() == "medium" else "🔴"

        log_text = (
            "<blockquote>🧩 <u><b>JUMBLE PUZZLE SOLVED LOG</b></u></blockquote>\n\n"
            f"👤 <b>Player :</b> {user_mention} (<code>{user.id}</code>)\n"
            f"🏰 <b>Chat :</b> <b>{chat_title}</b> (<code>{chat_id}</code>)\n\n"
            "<blockquote>🎯 <b>PUZZLE METRICS :</b>\n"
            f"• <b>Solved Word :</b> <code>{word.upper()}</code>\n"
            f"• <b>Answer Input :</b> <code>{raw_guess}</code>\n"
            f"• <b>Difficulty :</b> {diff_emoji} <b>{diff.upper()}</b>\n"
            f"• <b>Reward :</b> <b>+{points} pts/stars</b></blockquote>\n\n"
            "<blockquote>💰 <b>LIVE BALANCE TRACKER :</b>\n"
            f"• <b>Transition :</b> <code>{old_balance:,}</code> <b>+</b> <code>{points:,}</code> ➔ <code>{new_balance:,} pts</code></blockquote>\n\n"
            "<blockquote>📊 <b>PLAYER CAREER STATS :</b>\n"
            f"• <b>Total Solved :</b> <code>{u_stats['total_solved'] + 1}</code>\n"
            f"• <b>Easy :</b> <code>{u_stats['easy_solved']}</code> | <b>Medium :</b> <code>{u_stats['med_solved']}</code> | <b>Hard :</b> <code>{u_stats['hard_solved']}</code></blockquote>"
        )

        await client.send_message(
            chat_id=int(LOG_CHANNEL),
            text=log_text,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        print(f"[Puzzle Log Event Error]: {e}")


# ============================================================
# 2. DAILY BONUS CLAIM LOG (Every 24h DM Claim)
# ============================================================
async def send_daily_claim_log(client: Client, user, reward: int, old_balance: int = None):
    if not LOG_CHANNEL or not get_global_config("logging_enabled", 1):
        return

    try:
        u_stats = _fetch_user_full_stats(user.id)
        current_bal = u_stats["balance"]
        if old_balance is None:
            old_balance = max(0, current_bal - reward)
        new_balance = old_balance + reward

        user_mention = get_mention(user)

        log_text = (
            "<blockquote>🎁 <u><b>DAILY BONUS CLAIM LOG</b></u></blockquote>\n\n"
            f"👤 <b>Player :</b> {user_mention} (<code>{user.id}</code>)\n"
            f"🕒 <b>Claim Time :</b> <code>{time.strftime('%Y-%m-%d %H:%M:%S')}</code>\n\n"
            "<blockquote>💰 <b>WALLET UPDATE :</b>\n"
            f"• <b>Daily Bonus :</b> <b>+{reward} pts/stars</b>\n"
            f"• <b>Transition :</b> <code>{old_balance:,}</code> <b>+</b> <code>{reward:,}</code> ➔ <code>{new_balance:,} pts</code></blockquote>"
        )

        buttons = [[InlineKeyboardButton(f"👤 {user.first_name}", url=f"tg://user?id={user.id}")]]
        await client.send_message(
            chat_id=int(LOG_CHANNEL),
            text=log_text,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        print(f"[Daily Claim Log Error]: {e}")


# ============================================================
# 3. GROUP ADDITION / ADMIN BONUS CLAIM LOG
# ============================================================
async def send_group_bonus_log(client: Client, user, chat, reward: int, old_balance: int = None):
    if not LOG_CHANNEL or not get_global_config("logging_enabled", 1):
        return

    try:
        u_stats = _fetch_user_full_stats(user.id)
        current_bal = u_stats["balance"]
        if old_balance is None:
            old_balance = max(0, current_bal - reward)
        new_balance = old_balance + reward

        chat_title = html.escape(getattr(chat, "title", "Group") or "Group")
        chat_id = getattr(chat, "id", 0)
        user_mention = get_mention(user)

        buttons = [
            [InlineKeyboardButton(f"👤 {user.first_name} ({user.id})", url=f"tg://user?id={user.id}")],
        ]
        if getattr(chat, "username", None):
            buttons.append([InlineKeyboardButton("🏰 Target Group", url=f"https://t.me/{chat.username}")])

        log_text = (
            "<blockquote>🎉 <u><b>GROUP ADDITION BONUS CLAIM LOG</b></u></blockquote>\n\n"
            f"👤 <b>Claimed By :</b> {user_mention} (<code>{user.id}</code>)\n"
            f"🏰 <b>Added In Group :</b> <b>{chat_title}</b> (<code>{chat_id}</code>)\n"
            f"🕒 <b>Timestamp :</b> <code>{time.strftime('%Y-%m-%d %H:%M:%S')}</code>\n\n"
            "<blockquote>💰 <b>BONUS TRANSACTION :</b>\n"
            f"• <b>Group Admin Reward :</b> <b>+{reward} pts/stars</b>\n"
            f"• <b>Live Transition :</b> <code>{old_balance:,}</code> <b>+</b> <code>{reward:,}</code> ➔ <code>{new_balance:,} pts</code></blockquote>"
        )

        await client.send_message(
            chat_id=int(LOG_CHANNEL),
            text=log_text,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        print(f"[Group Bonus Log Error]: {e}")

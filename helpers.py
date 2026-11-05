import asyncio
import html
import time
from config import OWNER_ID, LOG_CHANNEL
from database import DB, get_global_config, get_settings
from pyrogram import Client
from pyrogram.enums import ChatType, ChatMemberStatus, ParseMode, MessageServiceType
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
        await client.delete_messages(chat_id, [message_id])
    except Exception:
        pass


async def safe_pin_and_clean(client, chat_id: int, message_id: int):
    """Naya puzzle pin karega aur turant generate huye pin alert ko delete karega."""
    if not message_id or chat_id > 0:
        return

    # Auto Delete status check
    try:
        raw_s = get_settings(chat_id)
        s = dict(raw_s) if raw_s else {}
        auto_del = bool(s.get("auto_delete", 0))
    except Exception:
        auto_del = False

    try:
        await client.pin_chat_message(chat_id, message_id, disable_notification=True, both_sides=True)
    except Exception as e:
        print(f"[Pin Error]: {e}")
        return

    # Agar auto_delete ON hai tabhi service pin alert delete hoga
    if auto_del:
        await asyncio.sleep(0.4)
        try:
            await client.delete_messages(chat_id, [message_id + 1, message_id + 2])
        except Exception:
            pass

        try:
            service_ids = []
            async for m in client.get_chat_history(chat_id, limit=5):
                if getattr(m, "pinned_message", None) or getattr(m, "service", None) == MessageServiceType.PINNED_MESSAGE:
                    service_ids.append(m.id)
            if service_ids:
                await client.delete_messages(chat_id, service_ids)
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
            if not u_dict and isinstance(u, (list, tuple)):
                data["balance"] = u[2] if len(u) > 2 else 0
            else:
                data["balance"] = u_dict.get("stars", 0) if u_dict.get("stars", 0) > 0 else u_dict.get("points", 0)
                data["total_solved"] = u_dict.get("solved", u_dict.get("correct", 0))
                data["easy_solved"] = u_dict.get("easy_solved", u_dict.get("easy_correct", 0))
                data["med_solved"] = u_dict.get("medium_solved", u_dict.get("medium_correct", 0))
                data["hard_solved"] = u_dict.get("hard_solved", u_dict.get("hard_correct", 0))
    except Exception as e:
        print(f"[Fetch User Stats Error]: {e}")
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

        easy_cnt = u_stats["easy_solved"]
        med_cnt = u_stats["med_solved"]
        hard_cnt = u_stats["hard_solved"]
        total_cnt = u_stats["total_solved"]

        d_lower = str(diff).lower()
        if d_lower == "easy":
            easy_cnt = max(1, easy_cnt)
        elif d_lower == "hard":
            hard_cnt = max(1, hard_cnt)
        else:
            med_cnt = max(1, med_cnt)

        total_cnt = max(total_cnt, easy_cnt + med_cnt + hard_cnt)

        chat_title = html.escape(getattr(chat, "title", "Direct Message") or "Chat")
        chat_id = getattr(chat, "id", 0)
        user_mention = get_mention(user)

        buttons = [
            [InlineKeyboardButton(f"👤 {user.first_name} ({user.id})", url=f"tg://user?id={user.id}")],
        ]
        if getattr(chat, "username", None):
            buttons.append([InlineKeyboardButton("🏰 Group Chat", url=f"https://t.me/{chat.username}")])

        diff_emoji = "🟢" if d_lower == "easy" else "🟡" if d_lower == "medium" else "🔴"

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
            f"• <b>Total Solved :</b> <code>{total_cnt}</code>\n"
            f"• <b>Easy :</b> <code>{easy_cnt}</code> | <b>Medium :</b> <code>{med_cnt}</code> | <b>Hard :</b> <code>{hard_cnt}</code></blockquote>"
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

        buttons = [
            [InlineKeyboardButton(f"👤 {user.first_name} ({user.id})", url=f"tg://user?id={user.id}")],
        ]
        if getattr(user, "username", None):
            buttons.append([InlineKeyboardButton("🔗 Open Telegram Profile", url=f"https://t.me/{user.username}")])

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
        if getattr(user, "username", None):
            buttons.append([InlineKeyboardButton("🔗 Claimer Profile", url=f"https://t.me/{user.username}")])
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


# ============================================================
# 4. BALANCE AUDIT LOG (/addstar & /deductstar)
# ============================================================
async def send_balance_modify_log(client: Client, admin_user, target_user, action: str, amount: int, old_balance: int, new_balance: int):
    """
    Owner ya Auth Admin dwara kisi user ke balance me add ya deduct hone par Channel par audit log send karega.
    """
    if not LOG_CHANNEL or not get_global_config("logging_enabled", 1):
        return

    try:
        is_add = action.lower() == "add"
        action_title = "STARS / POINTS ADDED" if is_add else "STARS / POINTS DEDUCTED"
        tag_emoji = "➕" if is_add else "🔻"
        sym = "+" if is_add else "-"

        admin_mention = get_mention(admin_user)
        target_mention = get_mention(target_user)

        log_text = (
            f"<blockquote>{tag_emoji} <u><b>ADMIN AUDIT: {action_title}</b></u></blockquote>\n\n"
            f"👮 <b>Executed By :</b> {admin_mention} (<code>{admin_user.id}</code>)\n"
            f"👤 <b>Target User :</b> {target_mention} (<code>{target_user.id}</code>)\n"
            f"🕒 <b>Timestamp :</b> <code>{time.strftime('%Y-%m-%d %H:%M:%S')}</code>\n\n"
            "<blockquote>💰 <b>TRANSACTION DETAILS :</b>\n"
            f"• <b>Action :</b> <code>{action.upper()}</code>\n"
            f"• <b>Amount :</b> <b>{sym}{amount:,} Stars/Points</b>\n"
            f"• <b>Balance Shift :</b> <code>{old_balance:,}</code> ➔ <code>{new_balance:,} Stars</code></blockquote>"
        )

        buttons = [
            [
                InlineKeyboardButton(f"👮 Admin ({admin_user.id})", url=f"tg://user?id={admin_user.id}"),
                InlineKeyboardButton(f"👤 Target ({target_user.id})", url=f"tg://user?id={target_user.id}")
            ]
        ]
        if getattr(target_user, "username", None):
            buttons.append([InlineKeyboardButton("🔗 Target Profile Link", url=f"https://t.me/{target_user.username}")])

        await client.send_message(
            chat_id=int(LOG_CHANNEL),
            text=log_text,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        print(f"[Balance Modify Log Error]: {e}")

import html
import time
from config import START_IMG, SUPPORT_GC, ADD_ME_URL, MUSIC_BOT_URL
from database import DB, ensure_user, get_user
from helpers import get_mention, is_group, is_authed, is_owner
from pyrogram import Client, filters
from pyrogram.enums import ChatType, ParseMode
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message

@Client.on_message(filters.command("start"))
async def start_cmd(_, message: Message):
    ensure_user(message.from_user)
    text = (
        "<blockquote>🧩 <b>𝐖ᴇʟᴄᴏᴍᴇ 𝐓ᴏ 𝐀ᴅᴠᴀɴᴄᴇᴅ 𝐉ᴜᴍʙʟᴇ 𝐁ᴏᴛ!</b></blockquote>\n\n"
        "<blockquote>🎮 <b>𝐆ᴀᴍᴇ 𝐂ᴏᴍᴍᴀɴᴅs:</b>\n"
        "• <code>/jumble</code> — 𝐒ᴛᴀʀᴛ 𝐀ᴜᴛᴏ-ʟᴏᴏᴘ 𝐉ᴜᴍʙʟᴇ 𝐆ᴀᴍᴇ\n"
        "• <code>/jumblefight @user</code> — 1v1 𝐁ᴀᴛᴛʟᴇ 𝐌ᴏᴅᴇ\n"
        "• <code>/jumblebetfight [mode] [amount] @user</code> — 1v1 𝐁ᴇᴛ 𝐁ᴀᴛᴛʟᴇ\n"
        "• <code>/settings</code> — 𝐀ᴅᴍɪɴ 𝐏ᴀɴᴇʟ</blockquote>\n\n"
        "<blockquote>🎁 <b>𝐅ʀᴇᴇ 𝐏ᴏɪɴᴛs:</b>\n"
        "• <code>/daily</code> — 𝐂ʟᴀɪᴍ 𝐃ᴀɪʟʏ 𝐁ᴏɴᴜs (DM)\n"
        "• <code>/bonus</code> — 𝐂ʟᴀɪᴍ 𝐆ʀᴏᴜᴘ 𝐀ᴅᴅɪᴛɪᴏɴ 𝐁ᴏɴᴜs</blockquote>\n\n"
        "<blockquote>📊 <b>𝐒ᴛᴀᴛs & 𝐑ᴀɴᴋɪɴɢs:</b>\n"
        "• <code>/stats</code> — 𝐘ᴏᴜʀ 𝐏ᴇʀғᴏʀᴍᴀɴᴄᴇ\n"
        "• <code>/leaderboard</code> — 𝐓ᴏᴘ 𝐑ᴀɴᴋs</blockquote>"
    )
    dm_markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💬 𝐒ᴜᴘᴘᴏʀᴛ", url=SUPPORT_GC),
            InlineKeyboardButton("➕ 𝐀ᴅᴅ 𝐌ᴇ", url=ADD_ME_URL)
        ],
        [InlineKeyboardButton("˹ 𓆩ℛᴏ֟፝ᴏʜɪ ꭙ 𝐌ᴜ֟፝sɪᴄ𓆪˼ ♪", url=MUSIC_BOT_URL)]
    ])
    if message.chat.type in (ChatType.PRIVATE,):
        try:
            await message.reply_photo(photo=START_IMG, caption=text, reply_markup=dm_markup, parse_mode=ParseMode.HTML)
        except Exception:
            await message.reply_text(text, reply_markup=dm_markup, parse_mode=ParseMode.HTML)
    else:
        await message.reply_text(text, reply_markup=dm_markup, parse_mode=ParseMode.HTML)

@Client.on_message(filters.command("help"))
async def help_cmd(_, message: Message):
    is_user_auth = is_authed(message.from_user.id) if message.from_user else False
    text = (
        "<blockquote>🧩 <b>𝐉ᴜᴍʙʟᴇ 𝐂ᴏᴍᴍᴀɴᴅs 𝐆ᴜɪᴅᴇ</b>\n\n"
        "• <code>/jumble</code> — 𝐒ᴛᴀʀᴛ ᴀᴜᴛᴏ-ʟᴏᴏᴘɪɴɢ ᴊᴜᴍʙʟᴇ ɢᴀᴍᴇ\n"
        "• <code>/jumblefight @user</code> — 1v1 ʙᴀᴛᴛʟᴇ ᴍᴀᴛᴄʜ\n"
        "• <code>/jumblebetfight [mode] [amount] @user</code> — 1v1 ʙᴇᴛ ᴍᴀᴛᴄʜ\n"
        "• <code>/settings</code> — 𝐀ᴅᴍɪɴ sᴛᴀʀᴛ/sᴛᴏᴘ & ɢᴀᴍᴇ sᴇᴛᴛɪɴɢs\n"
        "• <code>/daily</code> — 𝐂ʟᴀɪᴍ ᴅᴀɪʟʏ ᴘᴏɪɴᴛs (𝐃𝐌 ᴏɴʟʏ)\n"
        "• <code>/bonus</code> — 𝐂ʟᴀɪᴍ ɢʀᴏᴜᴘ ᴀᴅᴍɪɴ ʀᴇᴡᴀʀᴅ\n"
        "• <code>/leaderboard</code> — 𝐓ᴏᴘ ᴘʟᴀʏᴇʀs ʀᴀɴᴋɪɴɢ\n"
        "• <code>/stats</code> — 𝐏ᴇʀsᴏɴᴀʟ sᴄᴏʀᴇ ᴄᴀʀᴅ</blockquote>"
    )
    if is_user_auth:
        text += (
            "\n\n<blockquote>🔐 <b>𝐀ᴜᴛʜ 𝐂ᴏᴍᴍᴀɴᴅs:</b>\n"
            "• <code>/word</code> — 𝐕ɪᴇᴡ ᴡᴏʀᴅ ʙᴀɴᴋ\n"
            "• <code>/addword [easy|med|hard] [words]</code> — 𝐀ᴅᴅ ᴡᴏʀᴅs\n"
            "• <code>/delword [diff] [word]</code> — 𝐃ᴇʟᴇᴛᴇ ᴡᴏʀᴅ\n"
            "• <code>/addstar [user] [pts]</code> — 𝐀ᴅᴅ ᴘᴏɪɴᴛs\n"
            "• <code>/deductstar [user] [pts]</code> — 𝐃ᴇᴅᴜᴄᴛ ᴘᴏɪɴᴛs</blockquote>"
        )
    if message.from_user and is_owner(message.from_user.id):
        text += (
            "\n\n<blockquote>👑 <b>𝐎ᴡɴᴇʀ 𝐂ᴏᴍᴍᴀɴᴅs:</b>\n"
            "• <code>/auth @user</code> | <code>/unauth @user</code>\n"
            "• <code>/backup</code> — 𝐃ᴏᴡɴʟᴏᴀᴅ 𝐃𝐚𝐭𝐚𝐛𝐚𝐬𝐞</blockquote>"
        )
    await message.reply_text(text, parse_mode=ParseMode.HTML)

@Client.on_message(filters.command(["stats", "stat", "mystats", "score"]))
async def stats_cmd(_, message: Message):
    if not message.from_user:
        return
    ensure_user(message.from_user)
    u = get_user(message.from_user.id)
    total_fights = u["fight_wins"] + u["fight_losses"]
    winrate = ((u["fight_wins"] / total_fights) * 100) if total_fights else 0
    total_bets = (u["bet_wins"] or 0) + (u["bet_losses"] or 0)
    bet_winrate = (((u["bet_wins"] or 0) / total_bets) * 100) if total_bets else 0
    mention = get_mention(message.from_user)
    priv_status = "🔒 Private" if u["is_private"] else "🌐 Public"

    await message.reply_text(
        f"<blockquote>👤 {mention} (<code>{message.from_user.id}</code>)\n\n"
        f"⭐ <b>𝐏ᴏɪɴᴛs:</b> <code>{u['points']}</code>\n"
        f"🧩 <b>𝐒ᴏʟᴠᴇᴅ:</b> <code>{u['solved']}</code>\n"
        f"🔥 <b>𝐒ᴛʀᴇᴀᴋ:</b> <code>{u['streak']}</code> (Best: {u['best_streak']})\n"
        f"🛡️ <b>𝐏ʀɪᴠᴀᴄʏ:</b> <code>{priv_status}</code>\n\n"
        f"⚔️ <b>𝐉ᴜᴍʙʟᴇ 𝐅ɪɢʜᴛ:</b> <code>{u['fight_wins']}W - {u['fight_losses']}L</code> ({winrate:.1f}%)\n"
        f"💰 <b>𝐁ᴇᴛ 𝐅ɪɢʜᴛ:</b> <code>{u['bet_wins']}W - {u['bet_losses']}L</code> ({bet_winrate:.1f}%)</blockquote>",
        parse_mode=ParseMode.HTML
    )

def format_lb_entry(user_id, name, username, is_private):
    clean_name = html.escape(str(name or "Player"))
    if is_private:
        return f"<b>{clean_name}</b>"
    if username:
        return f"<a href='https://t.me/{username}'>{clean_name}</a> (<code>{user_id}</code>)"
    return f"<a href='tg://openmessage?user_id={user_id}'>{clean_name}</a> (<code>{user_id}</code>)"

def build_leaderboard_text_and_kb(scope_type, chat_id):
    now = time.time()
    medals = ["🥇", "🥈", "🥉"]

    if scope_type == "daily":
        since = now - 86400
        title = "📅 <b>𝐃𝐀𝐈𝐋𝐘 𝐆𝐑𝐎𝐔𝐏 𝐋𝐄𝐀𝐃𝐄𝐑𝐁𝐎𝐀𝐑𝐃 (24h)</b>"
        rows = DB.execute("""
            SELECT h.user_id, u.name, u.username, u.is_private, SUM(h.points) as total_pts
            FROM score_history h
            LEFT JOIN users u ON h.user_id = u.user_id
            WHERE h.chat_id = ? AND h.timestamp >= ?
            GROUP BY h.user_id
            HAVING total_pts > 0
            ORDER BY total_pts DESC
            LIMIT 10
        """, (chat_id, since)).fetchall()
    elif scope_type == "weekly":
        since = now - (86400 * 7)
        title = "🗓️ <b>𝐖𝐄𝐄𝐊𝐋𝐘 𝐆𝐑𝐎𝐔𝐏 𝐋𝐄𝐀𝐃𝐄𝐑𝐁𝐎𝐀𝐑𝐃 (7 Days)</b>"
        rows = DB.execute("""
            SELECT h.user_id, u.name, u.username, u.is_private, SUM(h.points) as total_pts
            FROM score_history h
            LEFT JOIN users u ON h.user_id = u.user_id
            WHERE h.chat_id = ? AND h.timestamp >= ?
            GROUP BY h.user_id
            HAVING total_pts > 0
            ORDER BY total_pts DESC
            LIMIT 10
        """, (chat_id, since)).fetchall()
    elif scope_type == "monthly":
        since = now - (86400 * 30)
        title = "📆 <b>𝐌𝐎𝐍𝐓𝐇𝐋𝐘 𝐆𝐋𝐎𝐁𝐀𝐋 𝐋𝐄𝐀𝐃𝐄𝐑𝐁𝐎𝐀𝐑𝐃 (30 Days)</b>"
        rows = DB.execute("""
            SELECT h.user_id, u.name, u.username, u.is_private, SUM(h.points) as total_pts
            FROM score_history h
            LEFT JOIN users u ON h.user_id = u.user_id
            WHERE h.timestamp >= ?
            GROUP BY h.user_id
            HAVING total_pts > 0
            ORDER BY total_pts DESC
            LIMIT 10
        """, (since,)).fetchall()
    else:
        title = "🌍 <b>𝐆𝐋𝐎𝐁𝐀𝐋 𝐀𝐋𝐋-𝐓𝐈𝐌𝐄 𝐋𝐄𝐀𝐃𝐄𝐑𝐁𝐎𝐀𝐑𝐃</b>"
        rows = DB.execute("""
            SELECT user_id, name, username, is_private, points as total_pts
            FROM users
            WHERE points > 0
            ORDER BY points DESC
            LIMIT 10
        """).fetchall()

    text = f"<blockquote>{title}\n\n"
    if not rows:
        text += "<i>Abhi tak koi score record nahi hua hai.</i>"
    else:
        for i, u in enumerate(rows, 1):
            medal = medals[i - 1] if i <= 3 else f"<code>{i}.</code>"
            user_entry = format_lb_entry(u['user_id'], u['name'], u['username'], u['is_private'])
            text += f"{medal} {user_entry} — ⭐ <b>{u['total_pts']} pts</b>\n"
    text += "</blockquote>"

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"{'✅ ' if scope_type=='daily' else ''}📅 𝐃ᴀɪʟʏ (GC)", callback_data=f"lb_daily_{chat_id}"),
            InlineKeyboardButton(f"{'✅ ' if scope_type=='weekly' else ''}🗓️ 𝐖ᴇᴇᴋʟʏ (GC)", callback_data=f"lb_weekly_{chat_id}")
        ],
        [
            InlineKeyboardButton(f"{'✅ ' if scope_type=='monthly' else ''}📆 𝐌ᴏɴᴛʜʟʏ (Global)", callback_data=f"lb_monthly_{chat_id}"),
            InlineKeyboardButton(f"{'✅ ' if scope_type=='global' else ''}🌍 𝐆ʟᴏʙᴀʟ", callback_data=f"lb_global_{chat_id}")
        ],
        [InlineKeyboardButton("❌ 𝐂ʟᴏsᴇ", callback_data="close_panel")]
    ])
    return text, kb

@Client.on_message(filters.command(["leaderboard", "top", "rank", "lb"]))
async def leaderboard_cmd(_, message: Message):
    chat_id = message.chat.id
    scope = "daily" if is_group(message) else "global"
    text, kb = build_leaderboard_text_and_kb(scope, chat_id)
    await message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)

@Client.on_message(filters.command("private"))
async def private_cmd(_, message: Message):
    if not message.from_user:
        return
    ensure_user(message.from_user)
    DB.execute("UPDATE users SET is_private=1 WHERE user_id=?", (message.from_user.id,))
    DB.commit()
    await message.reply_text("<blockquote>🔒 <b>Privacy Enabled!</b> Aapka User ID aur link hide ho chuka hai.</blockquote>", parse_mode=ParseMode.HTML)

@Client.on_message(filters.command("public"))
async def public_cmd(_, message: Message):
    if not message.from_user:
        return
    ensure_user(message.from_user)
    DB.execute("UPDATE users SET is_private=0 WHERE user_id=?", (message.from_user.id,))
    DB.commit()
    await message.reply_text("<blockquote>🌐 <b>Public Mode Enabled!</b> Leaderboard par aapki ID display hogi.</blockquote>", parse_mode=ParseMode.HTML)

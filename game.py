import asyncio
import html
import io
import os
import random
import re
import sqlite3
import subprocess
import sys
import time
from collections import defaultdict

from PIL import Image, ImageDraw, ImageFont
from pyrogram import Client, filters
from pyrogram.enums import ChatType, ChatMemberStatus, ParseMode
from pyrogram.errors import MessageNotModified, RPCError, ChannelInvalid, ChannelPrivate, PeerIdInvalid, UserIsBlocked
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    Message,
    ChatMemberUpdated
)

# ============================================================
# CONFIG & HARDCODED CREDENTIALS
# ============================================================

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

API_ID = 35218869
API_HASH = "80baadcfd00a39a0ff1f5f529d23156f"
OWNER_ID = 8564072723
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")
LOGGER_GROUP_ID = -1003515360437

START_IMG = "https://graph.org/file/7c0c03d68308f0c5dad42-ddb933df03f0ff0632.jpg"
SUPPORT_GC = "https://t.me/Roohi_Soul_Gc"
ADD_ME_URL = "https://t.me/Jumbles_Words_Bot?startgroup=true"
MUSIC_BOT_URL = "https://t.me/Roohi_Queen_Bot?start=_tgr_yN-6yUs4ZmRh"

app = Client(
    "advanced_jumble_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

DB = sqlite3.connect("jumble_game.db", check_same_thread=False)
DB.row_factory = sqlite3.Row
LOCK = asyncio.Lock()

# ============================================================
# WORD BANK
# ============================================================

DEFAULT_EASY = """
apple banana orange mango table chair house water school friend family
happy garden flower animal window bottle mobile computer summer winter
river music movie player football cricket doctor teacher market village
country morning evening coffee bread pizza camera phone pencil paper
train bus road car earth world light night star cloud rain green blue
black white tiger lion horse rabbit monkey fish bird tree fruit
""".split()

DEFAULT_MEDIUM = """
adventure beautiful knowledge education important dangerous different
experience friendship happiness technology information internet
mountain waterfall sunshine keyboard hospital university restaurant
football cricket championship tournament engineer scientist medicine
history geography language computer network application database
security password community discussion entertainment television
photography creativity imagination discovery opportunity challenge
journey traveler vacation airport railway newspaper magazine
""".split()

DEFAULT_HARD = """
extraordinary responsibility communication determination independence
international transformation understanding environment intelligence
architecture investigation recommendation administration opportunity
entrepreneurship cryptocurrency cybersecurity authentication
programming mathematics biotechnology astrophysics psychology
philosophy civilization transportation infrastructure globalization
misunderstanding pronunciation encyclopedia experimentation
electromagnetism thermodynamics interoperability decentralization
""".split()

DEFAULT_EVENT = """
supernova quantum singularity kaleidoscope cryptocurrency metamorphic
photosynthesis transcendence bioluminescent counterrevolutionary
electroencephalography compartmentalization
""".split()

# ============================================================
# DATABASE SETUP & MIGRATIONS
# ============================================================

DB.executescript("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    name TEXT,
    points INTEGER DEFAULT 0,
    solved INTEGER DEFAULT 0,
    best_streak INTEGER DEFAULT 0,
    streak INTEGER DEFAULT 0,
    fight_wins INTEGER DEFAULT 0,
    fight_losses INTEGER DEFAULT 0,
    bet_wins INTEGER DEFAULT 0,
    bet_losses INTEGER DEFAULT 0,
    is_private INTEGER DEFAULT 0,
    last_daily REAL DEFAULT 0,
    exp INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1,
    point_card_exp REAL DEFAULT 0,
    level_card_exp REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS auth_users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    name TEXT,
    added_at REAL
);

CREATE TABLE IF NOT EXISTS custom_words (
    difficulty TEXT,
    word TEXT,
    PRIMARY KEY(difficulty, word)
);

CREATE TABLE IF NOT EXISTS event_words (
    word TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS events_bank (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    word TEXT,
    hint TEXT,
    reward_stars INTEGER,
    reward_exp INTEGER,
    interval_hrs INTEGER,
    target_type TEXT,
    next_run REAL,
    is_active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS settings (
    chat_id INTEGER PRIMARY KEY,
    easy INTEGER DEFAULT 120,
    medium INTEGER DEFAULT 300,
    hard INTEGER DEFAULT 600,
    default_diff TEXT DEFAULT 'medium',
    is_active INTEGER DEFAULT 1,
    auto_delete INTEGER DEFAULT 0,
    event_active INTEGER DEFAULT 1,
    logging_enabled INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS bot_config (
    key TEXT PRIMARY KEY,
    value INTEGER
);

CREATE TABLE IF NOT EXISTS group_adders (
    chat_id INTEGER PRIMARY KEY,
    user_id INTEGER,
    added_at REAL
);

CREATE TABLE IF NOT EXISTS group_bonus (
    chat_id INTEGER PRIMARY KEY,
    user_id INTEGER,
    claimed_at REAL
);

CREATE TABLE IF NOT EXISTS games (
    chat_id INTEGER PRIMARY KEY,
    difficulty TEXT,
    word TEXT,
    puzzle_id INTEGER,
    started REAL,
    expires REAL,
    message_id INTEGER,
    solved INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS event_games (
    chat_id INTEGER PRIMARY KEY,
    event_id INTEGER,
    word TEXT,
    hint TEXT,
    puzzle_id INTEGER,
    started REAL,
    expires REAL,
    message_id INTEGER,
    solved INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS used_words (
    chat_id INTEGER,
    difficulty TEXT,
    word TEXT,
    PRIMARY KEY(chat_id, difficulty, word)
);

CREATE TABLE IF NOT EXISTS puzzle_hints (
    chat_id INTEGER,
    puzzle_id INTEGER,
    user_id INTEGER,
    hints_used INTEGER DEFAULT 0,
    revealed_indices TEXT DEFAULT '',
    PRIMARY KEY(chat_id, puzzle_id, user_id)
);

CREATE TABLE IF NOT EXISTS score_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    chat_id INTEGER,
    points INTEGER,
    tag TEXT DEFAULT 'normal',
    timestamp REAL
);
""")
DB.commit()

def run_migrations():
    defaults = {
        "points_easy": 10,
        "points_medium": 20,
        "points_hard": 30,
        "exp_easy": 15,
        "exp_medium": 30,
        "exp_hard": 50,
        "hints_easy": 3,
        "hints_medium": 3,
        "hints_hard": 3,
        "daily_points": 50,
        "bonus_points": 100,
        "card_point_price": 500,
        "card_point_hrs": 3,
        "card_point_req_lvl": 1,
        "card_level_price": 600,
        "card_level_hrs": 3,
        "card_level_req_lvl": 2,
        "global_exp_per_lvl": 500,
        "shop_exp_cost": 1000,
        "shop_exp_reward": 500
    }
    for k, v in defaults.items():
        DB.execute("INSERT OR IGNORE INTO bot_config (key, value) VALUES (?, ?)", (k, v))

    settings_cols = [c[1] for c in DB.execute("PRAGMA table_info(settings)").fetchall()]
    if "logging_enabled" not in settings_cols:
        DB.execute("ALTER TABLE settings ADD COLUMN logging_enabled INTEGER DEFAULT 1")
    if "event_active" not in settings_cols:
        DB.execute("ALTER TABLE settings ADD COLUMN event_active INTEGER DEFAULT 1")

    history_cols = [c[1] for c in DB.execute("PRAGMA table_info(score_history)").fetchall()]
    if "tag" not in history_cols:
        DB.execute("ALTER TABLE score_history ADD COLUMN tag TEXT DEFAULT 'normal'")

    for ew in DEFAULT_EVENT:
        DB.execute("INSERT OR IGNORE INTO event_words (word) VALUES (?)", (ew.lower().strip(),))

    DB.commit()

run_migrations()

WORDS = {
    "easy": list(set(w.lower() for w in DEFAULT_EASY if len(w) >= 3)),
    "medium": list(set(w.lower() for w in DEFAULT_MEDIUM if len(w) >= 3)),
    "hard": list(set(w.lower() for w in DEFAULT_HARD if len(w) >= 3))
}

custom_rows = DB.execute("SELECT difficulty, word FROM custom_words").fetchall()
for row in custom_rows:
    diff = row["difficulty"].lower()
    w = row["word"].lower().strip()
    if diff in WORDS and w not in WORDS[diff]:
        WORDS[diff].append(w)

EVENT_WORDS = [row["word"] for row in DB.execute("SELECT word FROM event_words").fetchall()]
EVENT_WIZARD = {}

# ============================================================
# HELPERS & SYSTEM UTILS
# ============================================================

def ensure_user(user):
    if not user:
        return
    DB.execute("""
        INSERT INTO users(user_id, username, name)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            username=excluded.username,
            name=excluded.name
    """, (
        user.id,
        user.username or "",
        user.first_name or "Player"
    ))
    DB.commit()

def get_user(user_id):
    return DB.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()

def is_owner(user_id):
    if not user_id:
        return False
    return int(user_id) == int(OWNER_ID)

def is_authed(user_id):
    if not user_id:
        return False
    if is_owner(user_id):
        return True
    row = DB.execute("SELECT user_id FROM auth_users WHERE user_id=?", (int(user_id),)).fetchone()
    return bool(row)

def get_global_config(key, default_val):
    row = DB.execute("SELECT value FROM bot_config WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default_val

def set_global_config(key, val):
    DB.execute("""
        INSERT INTO bot_config (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
    """, (key, val))
    DB.commit()

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

def get_settings(chat_id):
    row = DB.execute("SELECT * FROM settings WHERE chat_id=?", (chat_id,)).fetchone()
    if not row:
        DB.execute("""
            INSERT INTO settings(chat_id, easy, medium, hard, default_diff, is_active, auto_delete, event_active, logging_enabled)
            VALUES (?, 120, 300, 600, 'medium', 1, 0, 1, 1)
            ON CONFLICT(chat_id) DO NOTHING
        """, (chat_id,))
        DB.commit()
        row = DB.execute("SELECT * FROM settings WHERE chat_id=?", (chat_id,)).fetchone()
    return row

def is_group(message):
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

def calculate_level(exp: int) -> int:
    step = get_global_config("global_exp_per_lvl", 500)
    return max(1, (exp // step) + 1)

def format_duration(seconds: float) -> str:
    if seconds <= 0:
        return "Expired"
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    if hrs > 0:
        return f"{hrs}h {mins}m"
    return f"{mins}m"

def jumble_word(word):
    letters = list(word)
    for _ in range(50):
        random.shuffle(letters)
        result = "".join(letters)
        if result != word and result[::-1] != word:
            return result.upper()
    return "".join(letters).upper()

def choose_word(chat_id, difficulty):
    pool = WORDS.get(difficulty, [])[:]
    used = {
        row["word"]
        for row in DB.execute(
            "SELECT word FROM used_words WHERE chat_id=? AND difficulty=?",
            (chat_id, difficulty)
        ).fetchall()
    }
    available = [w for w in pool if w not in used]

    if not available:
        DB.execute("DELETE FROM used_words WHERE chat_id=? AND difficulty=?", (chat_id, difficulty))
        DB.commit()
        available = pool

    if not available:
        return "JUMBLE"

    word = random.choice(available)
    DB.execute("INSERT OR IGNORE INTO used_words(chat_id, difficulty, word) VALUES (?, ?, ?)", (chat_id, difficulty, word))
    DB.commit()
    return word

def get_font(size):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"
    ]
    for path in paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()

def make_puzzle_image(jumbled, mode_tag, puzzle_id, exp_val=0, is_event=False):
    bg_color = "#20122e" if is_event else "#10131a"
    accent = "#ff007f" if is_event else "#00e5ff"
    
    img = Image.new("RGB", (1200, 650), bg_color)
    draw = ImageDraw.Draw(img)

    title_font = get_font(55)
    small_font = get_font(35)

    text_len = len(jumbled)
    if text_len <= 7:
        display_text = "   ".join(jumbled)
        word_font = get_font(85)
    elif text_len <= 11:
        display_text = "  ".join(jumbled)
        word_font = get_font(65)
    elif text_len <= 15:
        display_text = " ".join(jumbled)
        word_font = get_font(50)
    else:
        display_text = " ".join(jumbled)
        word_font = get_font(38)

    title_str = "🌟 EVENT MYSTERY PUZZLE" if is_event else "🧩 JUMBLE WORD"
    draw.text((600, 70), title_str, anchor="mm", font=title_font, fill="white")
    draw.text((600, 300), display_text, anchor="mm", font=word_font, fill=accent)
    
    exp_suffix = f"  •  +{exp_val} EXP" if exp_val > 0 else ""
    draw.text((600, 480), f"{mode_tag.upper()}{exp_suffix}  •  #{puzzle_id}", anchor="mm", font=small_font, fill="#ffffff")
    draw.text((600, 545), "Unscramble the letters to earn Stars & EXP!", anchor="mm", font=small_font, fill="#aaaaaa")

    bio = io.BytesIO()
    bio.name = f"puzzle_{puzzle_id}_{random.randint(100, 999)}.png"
    img.save(bio, "PNG")
    bio.seek(0)
    return bio

async def delete_after(msg: Message, delay: int = 5):
    await asyncio.sleep(delay)
    try:
        await msg.delete()
    except Exception:
        pass

async def safe_delete_and_unpin(chat_id: int, message_id: int):
    if not message_id:
        return
    try:
        await app.unpin_chat_message(chat_id, message_id)
    except Exception:
        pass
    try:
        await app.delete_messages(chat_id, message_id)
    except Exception:
        pass

# ============================================================
# LOGGING SYSTEM (LOGGER GROUP)
# ============================================================

async def send_log_notification(chat_obj, user_obj, word, pts_gained, exp_gained, total_points, total_exp, level, is_event=False):
    s = get_settings(chat_obj.id)
    if not s["logging_enabled"]:
        return

    chat_title = chat_obj.title if hasattr(chat_obj, "title") and chat_obj.title else "Private DM"
    chat_username = getattr(chat_obj, "username", None)
    
    gc_link = None
    if chat_username:
        gc_link = f"https://t.me/{chat_username}"
    else:
        try:
            invite = await app.export_chat_invite_link(chat_obj.id)
            gc_link = invite
        except Exception:
            gc_link = None

    user_link = f"https://t.me/{user_obj.username}" if user_obj.username else f"tg://openmessage?user_id={user_obj.id}"

    btn_row = [
        InlineKeyboardButton("👤 User Profile", url=user_link)
    ]
    if gc_link:
        btn_row.append(InlineKeyboardButton("👥 Group Link", url=gc_link))

    kb = InlineKeyboardMarkup([btn_row])

    tag_str = "🌟 EVENT PUZZLE SOLVED" if is_event else "🧩 JUMBLE WORD SOLVED"
    log_text = (
        f"<blockquote>📢 <b>{tag_str}</b>\n\n"
        f"👤 <b>Player:</b> {get_mention(user_obj)} (<code>{user_obj.id}</code>)\n"
        f"🏷️ <b>Username:</b> @{user_obj.username if user_obj.username else 'None'}\n"
        f"👥 <b>Chat / Group:</b> <code>{html.escape(chat_title)}</code> (<code>{chat_obj.id}</code>)\n\n"
        f"✅ <b>Word:</b> <code>{word.upper()}</code>\n"
        f"⭐ <b>Stars Gained:</b> <code>+{pts_gained}</code> (Total: <code>{total_points}</code>)\n"
        f"⚡ <b>EXP Gained:</b> <code>+{exp_gained}</code> (Total: <code>{total_exp}</code> | Level <code>{level}</code>)\n"
        f"⏰ <b>Time:</b> <code>{time.strftime('%Y-%m-%d %H:%M:%S')}</code></blockquote>"
    )

    try:
        await app.send_message(LOGGER_GROUP_ID, log_text, reply_markup=kb, parse_mode=ParseMode.HTML)
    except Exception as e:
        print(f"Error sending log to logger group: {e}")

# ============================================================
# BOT ADDED TO GROUP LISTENER
# ============================================================

@app.on_chat_member_updated()
async def bot_added_handler(_, update: ChatMemberUpdated):
    if update.new_chat_member and update.new_chat_member.user and update.new_chat_member.user.is_self:
        if update.from_user and not update.from_user.is_bot:
            chat_id = update.chat.id
            user_id = update.from_user.id
            ensure_user(update.from_user)
            DB.execute("""
                INSERT INTO group_adders (chat_id, user_id, added_at)
                VALUES (?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET user_id=excluded.user_id, added_at=excluded.added_at
            """, (chat_id, user_id, time.time()))
            DB.commit()

# ============================================================
# NORMAL GAME CORE
# ============================================================

def normal_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💡 𝐇ɪɴᴛ", callback_data="hint"),
            InlineKeyboardButton("⏭️ 𝐒ᴋɪᴘ", callback_data="skip")
        ],
        [
            InlineKeyboardButton("🆕 𝐍ᴇᴡ 𝐖ᴏʀᴅ", callback_data="newword"),
            InlineKeyboardButton("🛍️ 𝐒ʜᴏᴘ", callback_data="open_shop_btn")
        ]
    ])

async def start_game(chat_id, difficulty, message_or_chat):
    if chat_id in JUMBLE_FIGHT:
        return

    settings = get_settings(chat_id)
    if not settings["is_active"]:
        return

    old_game = DB.execute("SELECT message_id FROM games WHERE chat_id=?", (chat_id,)).fetchone()
    if old_game and settings["auto_delete"] and old_game["message_id"]:
        await safe_delete_and_unpin(chat_id, old_game["message_id"])

    DB.execute("DELETE FROM games WHERE chat_id=?", (chat_id,))

    word = choose_word(chat_id, difficulty)
    jumbled = jumble_word(word)
    puzzle_id = random.randint(10000, 99999)
    now = time.time()
    timer_val = settings[difficulty]
    reward_pts = get_global_config(f"points_{difficulty}", 10)
    reward_exp = get_global_config(f"exp_{difficulty}", 30)
    hint_limit = get_global_config(f"hints_{difficulty}", 3)
    expires = now + timer_val

    DB.execute("""
        INSERT INTO games(chat_id, difficulty, word, puzzle_id, started, expires, message_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (chat_id, difficulty, word, puzzle_id, now, expires, 0))
    DB.commit()

    image = make_puzzle_image(jumbled, difficulty, puzzle_id, exp_val=reward_exp, is_event=False)
    caption_text = (
        f"<blockquote>🧩 <b>𝐉ᴜᴍʙʟᴇ #{puzzle_id}</b>\n\n"
        f"🎯 <b>𝐃ɪғғɪᴄᴜʟᴛʏ:</b> <code>{difficulty.title()}</code>\n"
        f"⏱️ <b>𝐓ɪᴍᴇ:</b> <code>{timer_val // 60}m {timer_val % 60}s</code>\n"
        f"⭐ <b>𝐑ᴇᴡᴀʀᴅ:</b> <code>+{reward_pts} Points</code>\n"
        f"⚡ <b>𝐄𝐗𝐏:</b> <code>+{reward_exp} EXP</code>\n"
        f"💡 <b>𝐇ɪɴᴛs:</b> <code>{hint_limit}/word</code></blockquote>\n\n"
        f"<blockquote>🔀 <i>𝐔ɴsᴄʀᴀᴍʙʟᴇ ᴛʜᴇ ʟᴇᴛᴛᴇʀs & ᴛʏᴘᴇ ɪɴ ᴄʜᴀᴛ!</i></blockquote>"
    )

    try:
        if isinstance(message_or_chat, Message):
            sent = await message_or_chat.reply_photo(photo=image, caption=caption_text, reply_markup=normal_keyboard(), parse_mode=ParseMode.HTML)
        else:
            sent = await app.send_photo(chat_id, photo=image, caption=caption_text, reply_markup=normal_keyboard(), parse_mode=ParseMode.HTML)

        DB.execute("UPDATE games SET message_id=? WHERE chat_id=?", (sent.id, chat_id))
        DB.commit()

        try:
            await sent.pin(disable_notification=True)
        except Exception:
            pass
    except (ChannelInvalid, ChannelPrivate, PeerIdInvalid, UserIsBlocked):
        DB.execute("UPDATE settings SET is_active=0 WHERE chat_id=?", (chat_id,))
        DB.commit()
    except Exception as e:
        print(f"Error sending puzzle to {chat_id}: {e}")

    asyncio.create_task(expire_game(chat_id, puzzle_id, expires))

async def expire_game(chat_id, puzzle_id, expires):
    await asyncio.sleep(max(0, expires - time.time()))
    if chat_id in JUMBLE_FIGHT:
        return

    row = DB.execute("SELECT * FROM games WHERE chat_id=? AND puzzle_id=?", (chat_id, puzzle_id)).fetchone()
    if not row or row["solved"]:
        return

    DB.execute("UPDATE games SET solved=1 WHERE chat_id=?", (chat_id,))
    DB.commit()

    s = get_settings(chat_id)
    if s["auto_delete"] and row["message_id"]:
        await safe_delete_and_unpin(chat_id, row["message_id"])

    try:
        exp_msg = await app.send_message(
            chat_id,
            f"<blockquote>⏰ <b>𝐓ɪᴍᴇ's 𝐔ᴘ!</b>\n\n"
            f"❌ <b>𝐍ᴏʙᴏᴅʏ sᴏʟᴠᴇᴅ ɪᴛ.</b>\n"
            f"✅ <b>𝐀ɴsᴡᴇʀ:</b> <code>{row['word'].upper()}</code>\n\n"
            f"🔄 <i>𝐍ᴇxᴛ ᴘᴜᴢᴢʟᴇ sᴛᴀʀᴛɪɴɢ ɪɴ 3 sᴇᴄᴏɴᴅs...</i></blockquote>",
            parse_mode=ParseMode.HTML
        )
        if s["auto_delete"]:
            asyncio.create_task(delete_after(exp_msg, 4))
    except Exception:
        pass

    await asyncio.sleep(3)
    s = get_settings(chat_id)
    if chat_id not in JUMBLE_FIGHT and s["is_active"]:
        asyncio.create_task(start_game(chat_id, s["default_diff"], chat_id))

# ============================================================
# DYNAMIC EVENT DISPATCHER & SCHEDULER
# ============================================================

async def dispatch_event_by_id(event_id, target_chat_id=None):
    ev = DB.execute("SELECT * FROM events_bank WHERE id=?", (event_id,)).fetchone()
    if not ev or not ev["is_active"]:
        return

    now = time.time()
    expires = now + 180

    targets = []
    if target_chat_id:
        targets = [target_chat_id]
    elif ev["target_type"] == "dm":
        users = DB.execute("SELECT user_id FROM users").fetchall()
        targets = [u["user_id"] for u in users]
    elif ev["target_type"] == "group":
        s_rows = DB.execute("SELECT chat_id FROM settings WHERE is_active=1 AND event_active=1 AND chat_id != 0").fetchall()
        targets = [r["chat_id"] for r in s_rows]
    else:
        users = DB.execute("SELECT user_id FROM users").fetchall()
        s_rows = DB.execute("SELECT chat_id FROM settings WHERE is_active=1 AND event_active=1 AND chat_id != 0").fetchall()
        targets = [u["user_id"] for u in users] + [r["chat_id"] for r in s_rows]

    for tid in targets:
        if ev["word"].lower() == "random":
            chosen_w = random.choice(EVENT_WORDS) if EVENT_WORDS else "MYSTERY"
        else:
            chosen_w = ev["word"]

        jumbled = jumble_word(chosen_w)
        puzzle_id = random.randint(10000, 99999)

        image = make_puzzle_image(jumbled, ev["title"], puzzle_id, exp_val=ev["reward_exp"], is_event=True)
        hint_text = f"\n💡 <b>Hint:</b> <code>{ev['hint']}</code>" if ev["hint"] and ev["hint"] != "0" else ""

        caption_text = (
            f"<blockquote>🌟 <b>{ev['title'].upper()} EVENT DROP!</b>\n\n"
            f"💎 <b>Reward Stars:</b> <code>+{ev['reward_stars']} pts</code>\n"
            f"⚡ <b>Reward EXP:</b> <code>+{ev['reward_exp']} EXP</code>{hint_text}\n"
            f"⏱️ <b>Time Limit:</b> <code>3 minutes</code></blockquote>\n\n"
            f"<blockquote>⚡ <i>Unscramble first to claim victory!</i></blockquote>"
        )

        try:
            old_ev = DB.execute("SELECT message_id FROM event_games WHERE chat_id=?", (tid,)).fetchone()
            if old_ev and old_ev["message_id"]:
                await safe_delete_and_unpin(tid, old_ev["message_id"])
            DB.execute("DELETE FROM event_games WHERE chat_id=?", (tid,))
            DB.commit()

            sent = await app.send_photo(tid, photo=image, caption=caption_text, parse_mode=ParseMode.HTML)
            DB.execute("""
                INSERT INTO event_games(chat_id, event_id, word, hint, puzzle_id, started, expires, message_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (tid, ev["id"], chosen_w, ev["hint"], puzzle_id, now, expires, sent.id))
            DB.commit()

            asyncio.create_task(expire_event_game(tid, puzzle_id, expires))
        except (ChannelInvalid, ChannelPrivate, PeerIdInvalid, UserIsBlocked):
            DB.execute("UPDATE settings SET is_active=0, event_active=0 WHERE chat_id=?", (tid,))
            DB.commit()
        except Exception as e:
            print(f"Error dispatching event to {tid}: {e}")

    next_run = now + (ev["interval_hrs"] * 3600)
    DB.execute("UPDATE events_bank SET next_run=? WHERE id=?", (next_run, event_id))
    DB.commit()

async def event_scheduler_loop():
    while True:
        await asyncio.sleep(60)
        now = time.time()
        due_events = DB.execute("SELECT id FROM events_bank WHERE is_active=1 AND next_run <= ?", (now,)).fetchall()
        for de in due_events:
            try:
                await dispatch_event_by_id(de["id"])
            except Exception as e:
                print(f"Scheduler loop error: {e}")

async def expire_event_game(chat_id, puzzle_id, expires):
    await asyncio.sleep(max(0, expires - time.time()))
    row = DB.execute("SELECT * FROM event_games WHERE chat_id=? AND puzzle_id=?", (chat_id, puzzle_id)).fetchone()
    if not row or row["solved"]:
        return

    DB.execute("UPDATE event_games SET solved=1 WHERE chat_id=?", (chat_id,))
    DB.commit()

    if row["message_id"]:
        await safe_delete_and_unpin(chat_id, row["message_id"])

    try:
        t_msg = await app.send_message(
            chat_id,
            f"<blockquote>⏰ <b>Event Word Expired!</b>\n\n"
            f"❌ Kisi ne solve nahi kiya.\n"
            f"✅ <b>Word:</b> <code>{row['word'].upper()}</code></blockquote>",
            parse_mode=ParseMode.HTML
        )
        asyncio.create_task(delete_after(t_msg, 5))
    except Exception:
        pass

# ============================================================
# AUTO-RESUME GAMES ON BOT STARTUP
# ============================================================

async def resume_all_active_games():
    await asyncio.sleep(3)
    rows = DB.execute("SELECT chat_id, default_diff FROM settings WHERE is_active = 1 AND chat_id != 0").fetchall()
    
    for row in rows:
        c_id = row["chat_id"]
        diff = row["default_diff"] or "medium"
        try:
            DB.execute("DELETE FROM games WHERE chat_id=?", (c_id,))
            DB.commit()
            
            await start_game(c_id, diff, c_id)
            await asyncio.sleep(0.8)
        except (ChannelInvalid, ChannelPrivate, PeerIdInvalid, UserIsBlocked):
            DB.execute("UPDATE settings SET is_active=0 WHERE chat_id=?", (c_id,))
            DB.commit()
        except Exception as e:
            print(f"Resume warning for chat {c_id}: {e}")

# ============================================================
# DATABASE BACKUP SYSTEM (MANUAL & AUTO BACKUP)
# ============================================================

@app.on_message(filters.command(["backup", "dbbackup", "getdb"]))
async def backup_db_cmd(_, message: Message):
    if not message.from_user or not is_owner(message.from_user.id):
        return await message.reply_text("<blockquote>❌ <b>Sirf Bot Owner database backup le sakta hai.</b></blockquote>", parse_mode=ParseMode.HTML)

    if not os.path.exists("jumble_game.db"):
        return await message.reply_text("<blockquote>❌ <b>Database file nahi mili!</b></blockquote>", parse_mode=ParseMode.HTML)

    status_msg = await message.reply_text("<blockquote>📦 <i>Exporting database backup...</i></blockquote>", parse_mode=ParseMode.HTML)
    try:
        await message.reply_document(
            document="jumble_game.db",
            caption=(
                "<blockquote>💾 <b>𝐉𝐔𝐌𝐁𝐋𝐄 𝐁𝐎𝐓 𝐃𝐀𝐓𝐀𝐁𝐀𝐒𝐄 𝐁𝐀𝐂𝐊𝐔𝐏</b>\n\n"
                f"📅 <b>Date:</b> <code>{time.strftime('%Y-%m-%d %H:%M:%S')}</code>\n"
                "📌 <i>Naye VPS par shift karte waqt yeh file bot ke folder me replace kar dena.</i></blockquote>"
            ),
            parse_mode=ParseMode.HTML
        )
        await status_msg.delete()
    except Exception as e:
        await status_msg.edit_text(f"<blockquote>❌ Backup failed: <code>{str(e)}</code></blockquote>", parse_mode=ParseMode.HTML)

async def auto_backup_task():
    while True:
        await asyncio.sleep(21600)  # 6 Hours interval
        try:
            if os.path.exists("jumble_game.db"):
                await app.send_document(
                    chat_id=OWNER_ID,
                    document="jumble_game.db",
                    caption=(
                        "<blockquote>🤖 <b>𝐀𝐔𝐓𝐎 𝐃𝐀𝐓𝐀𝐁𝐀𝐒𝐄 𝐁𝐀𝐂𝐊𝐔𝐏 (6h Interval)</b>\n\n"
                        f"⏰ <b>Time:</b> <code>{time.strftime('%Y-%m-%d %H:%M:%S')}</code>\n"
                        "Agar VPS achanak band ho jaye toh yeh file use karein.</blockquote>"
                    ),
                    parse_mode=ParseMode.HTML
                )
        except Exception as e:
            print(f"Auto-backup error: {e}")

# ============================================================
# JUMBLE FIGHT & BET FIGHT
# ============================================================

JUMBLE_FIGHT = {}
FIGHT_LOBBY = {}
REBET_LOBBY = {}

def fight_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💡 𝐇ɪɴᴛ", callback_data="fight_hint")]
    ])

async def fight_timeout_task(chat_id, round_num, timer_duration):
    await asyncio.sleep(timer_duration)

    should_advance = False
    async with LOCK:
        game = JUMBLE_FIGHT.get(chat_id)
        if game and game["round"] == round_num:
            word = game["word"]
            
            s = get_settings(chat_id)
            if s["auto_delete"] and game.get("msg_id"):
                await safe_delete_and_unpin(chat_id, game["msg_id"])

            try:
                t_msg = await app.send_message(
                    chat_id,
                    f"<blockquote>⏰ <b>𝐑ᴏᴜɴᴅ {round_num} 𝐓ɪᴍᴇᴏᴜᴛ!</b>\n"
                    f"❌ <b>𝐊ɪsɪ ɴᴇ sᴏʟᴠᴇ ɴᴀʜɪ ᴋɪʏᴀ.</b>\n"
                    f"✅ <b>𝐀ɴsᴡᴇʀ:</b> <code>{word.upper()}</code>\n\n"
                    f"🔄 <i>𝐍ᴇxᴛ ʀᴏᴜɴᴅ sᴛᴀʀᴛɪɴɢ...</i></blockquote>",
                    parse_mode=ParseMode.HTML
                )
                if s["auto_delete"]:
                    asyncio.create_task(delete_after(t_msg, 4))
            except Exception:
                pass
            should_advance = True

    if should_advance:
        await asyncio.sleep(2.5)
        asyncio.create_task(fight_next(chat_id))

async def fight_next(chat_id):
    game = JUMBLE_FIGHT.get(chat_id)
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
        await finish_fight(chat_id)
        return

    diff = game["difficulty"]
    word = random.choice(WORDS[diff])
    jumbled = jumble_word(word)

    game["word"] = word
    game["expires"] = time.time() + game["timer"]
    game["round_hints"] = defaultdict(lambda: {"count": 0, "indices": []})

    fight_tag = "BET FIGHT" if game.get("is_bet") else "FIGHT"
    image = make_puzzle_image(jumbled, f"{fight_tag} {diff.upper()}", game["round"])
    
    title_header = "💰 <b>𝐉𝐔𝐌𝐁𝐋𝐄 𝐁𝐄𝐓 𝐅𝐈𝐆𝐇𝐓" if game.get("is_bet") else "⚔️ <b>𝐉𝐔𝐌𝐁𝐋𝐄 𝐅𝐈𝐆𝐇𝐓"
    extra_info = f"\n💵 <b>𝐁ᴇᴛ:</b> <code>{game.get('bet_amount')} pts</code>" if game.get("is_bet") else ""

    try:
        sent = await app.send_photo(
            chat_id,
            photo=image,
            caption=(
                f"<blockquote>{title_header} — 𝐑𝐎𝐔𝐍𝐃 {game['round']}/10</b>\n\n"
                f"🎯 <b>𝐃ɪғғɪᴄᴜʟᴛʏ:</b> <code>{diff.title()}</code>\n"
                f"⏱️ <b>𝐓ɪᴍᴇ:</b> <code>{game['timer']}s</code>{extra_info}\n"
                f"🔀 <b>𝐒ᴏʟᴠᴇ ғᴀsᴛᴇsᴛ!</b>\n"
                f"👥 <b>𝐏ʟᴀʏᴇʀs:</b> {game['mentions'][game['players'][0]]} 🆚 {game['mentions'][game['players'][1]]}</blockquote>"
            ),
            reply_markup=fight_keyboard(),
            parse_mode=ParseMode.HTML
        )
        game["msg_id"] = sent.id
        try:
            await sent.pin(disable_notification=True)
        except Exception:
            pass
    except Exception as e:
        print(f"Fight send error: {e}")

    game["task"] = asyncio.create_task(fight_timeout_task(chat_id, game["round"], game["timer"]))

async def finish_fight(chat_id):
    game = JUMBLE_FIGHT.pop(chat_id, None)
    if not game:
        return

    curr = asyncio.current_task()
    if game.get("task") and game["task"] is not curr and not game["task"].done():
        try:
            game["task"].cancel()
        except Exception:
            pass

    s = get_settings(chat_id)
    if s["auto_delete"] and game.get("msg_id"):
        await safe_delete_and_unpin(chat_id, game["msg_id"])

    p1, p2 = game["players"]
    s1, s2 = game["scores"][p1], game["scores"][p2]
    is_bet = game.get("is_bet", False)
    bet_amt = game.get("bet_amount", 0)
    is_rebet = game.get("is_rebet", False)
    now = time.time()

    if s1 > s2:
        winner, loser = p1, p2
        w_score, l_score = s1, s2
    elif s2 > s1:
        winner, loser = p2, p1
        w_score, l_score = s2, s1
    else:
        winner = loser = None

    m1 = game["mentions"][p1]
    m2 = game["mentions"][p2]
    end_kb = None

    if not is_bet:
        if winner:
            DB.execute("UPDATE users SET fight_wins=fight_wins+1 WHERE user_id=?", (winner,))
            DB.execute("UPDATE users SET fight_losses=fight_losses+1 WHERE user_id=?", (loser,))
            DB.commit()

        result = f"<blockquote>🏁 <b>𝐉𝐔𝐌𝐁𝐋𝐄 𝐅𝐈𝐆𝐇𝐓 𝐎𝐕𝐄𝐑!</b>\n\n👤 {m1} — <b>{s1} pts</b>\n👤 {m2} — <b>{s2} pts</b>\n\n"
        if winner:
            result += f"🏆 <b>𝐌ᴀᴛᴄʜ 𝐖ɪɴɴᴇʀ:</b> {game['mentions'][winner]} 🎉</blockquote>"
        else:
            result += "🤝 <b>𝐌ᴀᴛᴄʜ 𝐃ʀᴀᴡ!</b></blockquote>"

    else:
        if winner:
            if is_rebet:
                total_rematch_pot = bet_amt * 2
                comeback_bonus = 100
                total_payout = total_rematch_pot + comeback_bonus

                DB.execute("UPDATE users SET points=points+?, bet_wins=bet_wins+1 WHERE user_id=?", (total_payout, winner))
                DB.execute("UPDATE users SET bet_losses=bet_losses+1 WHERE user_id=?", (loser,))
                DB.execute("INSERT INTO score_history (user_id, chat_id, points, tag, timestamp) VALUES (?, ?, ?, 'bet_fight', ?)", (winner, chat_id, total_payout, now))
                DB.commit()

                result = (
                    f"<blockquote>💰 <b>25% 𝐂𝐎𝐌𝐄𝐁𝐀𝐂𝐊 𝐑𝐄-𝐁𝐄𝐓 𝐅𝐈𝐆𝐇𝐓 𝐎𝐕𝐄𝐑!</b>\n\n"
                    f"👤 {game['mentions'][winner]} — <b>{w_score} pts</b> (WINNER)\n"
                    f"👤 {game['mentions'][loser]} — <b>{l_score} pts</b>\n\n"
                    f"🔥 <b>Comeback Payout:</b>\n"
                    f"• 25% + 25% Stake: <code>+{total_rematch_pot} pts</code>\n"
                    f"• Comeback Reward: <code>+100 stars/pts</code>\n"
                    f"🏆 <b>Total Reward:</b> <code>+{total_payout} points</code> to {game['mentions'][winner]}!\n\n"
                    f"💀 {game['mentions'][loser]} rematch haar gaya aur use 0 points mile.</blockquote>"
                )
            else:
                total_pot = bet_amt * 2
                win_reward = int(total_pot * 0.75)
                loser_cashback = total_pot - win_reward
                rebet_stake = int(bet_amt * 0.25)

                DB.execute("UPDATE users SET points=points+?, bet_wins=bet_wins+1 WHERE user_id=?", (win_reward, winner))
                DB.execute("UPDATE users SET points=points+?, bet_losses=bet_losses+1 WHERE user_id=?", (loser_cashback, loser))
                DB.execute("INSERT INTO score_history (user_id, chat_id, points, tag, timestamp) VALUES (?, ?, ?, 'bet_fight', ?)", (winner, chat_id, win_reward, now))
                DB.execute("INSERT INTO score_history (user_id, chat_id, points, tag, timestamp) VALUES (?, ?, ?, 'bet_fight', ?)", (loser, chat_id, loser_cashback, now))
                DB.commit()

                REBET_LOBBY[chat_id] = {
                    "original_winner": winner,
                    "original_loser": loser,
                    "rebet_amount": rebet_stake,
                    "difficulty": game["difficulty"],
                    "timer": game["timer"],
                    "winner_mention": game['mentions'][winner],
                    "loser_mention": game['mentions'][loser],
                    "orig_stake": bet_amt
                }

                end_kb = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(f"🔁 25% Re-Bet ({rebet_stake} pts) + 100 Bonus", callback_data="rebet_challenge")
                    ]
                ])

                result = (
                    f"<blockquote>💰 <b>𝐉𝐔𝐌𝐁𝐋𝐄 𝐁𝐄𝐓 𝐅𝐈𝐆𝐇𝐓 𝐎𝐕𝐄𝐑!</b>\n\n"
                    f"👤 {game['mentions'][winner]} — <b>{w_score} pts</b> (WINNER)\n"
                    f"👤 {game['mentions'][loser]} — <b>{l_score} pts</b>\n\n"
                    f"🏆 <b>75% 𝐖ɪɴɴᴇʀ 𝐑ᴇᴡᴀʀᴅ:</b> <code>+{win_reward} points</code> ({game['mentions'][winner]})\n"
                    f"🛡️ <b>25% 𝐋ᴏsᴇʀ 𝐂ᴀsʜʙᴀᴄᴋ:</b> <code>+{loser_cashback} points</code> ({game['mentions'][loser]})\n\n"
                    f"👉 {game['mentions'][loser]} chahe toh <b>25% Re-bet</b> karke 25%+25% pot aur <b>+100 Comeback Stars</b> jeet sakta hai!</blockquote>"
                )
        else:
            DB.execute("UPDATE users SET points=points+? WHERE user_id=?", (bet_amt, p1))
            DB.execute("UPDATE users SET points=points+? WHERE user_id=?", (bet_amt, p2))
            DB.execute("INSERT INTO score_history (user_id, chat_id, points, tag, timestamp) VALUES (?, ?, ?, 'bet_fight', ?)", (p1, chat_id, bet_amt, now))
            DB.execute("INSERT INTO score_history (user_id, chat_id, points, tag, timestamp) VALUES (?, ?, ?, 'bet_fight', ?)", (p2, chat_id, bet_amt, now))
            DB.commit()
            result = (
                f"<blockquote>🤝 <b>𝐉𝐔𝐌𝐁𝐋𝐄 𝐁𝐄𝐓 𝐅𝐈𝐆𝐇𝐓 𝐃𝐑𝐀𝐖!</b>\n\n"
                f"👤 {m1} — <b>{s1} pts</b>\n"
                f"👤 {m2} — <b>{s2} pts</b>\n\n"
                f"Dono players ko unka stake <code>{bet_amt} points</code> wapas refund kar diya gaya hai.</blockquote>"
            )

    await app.send_message(chat_id, result, reply_markup=end_kb, parse_mode=ParseMode.HTML)

    await asyncio.sleep(3)
    s = get_settings(chat_id)
    if s["is_active"]:
        await app.send_message(chat_id, "<blockquote>🔄 <i>𝐑ᴇsᴜᴍɪɴɢ ɴᴏʀᴍᴀʟ 𝐉ᴜᴍʙʟᴇ 𝐆ᴀᴍᴇ...</i></blockquote>", parse_mode=ParseMode.HTML)
        asyncio.create_task(start_game(chat_id, s["default_diff"], chat_id))

@app.on_message(filters.command(["jumblefight", "fight", "rapido"]))
async def jumble_fight_cmd(_, message: Message):
    if not is_group(message):
        return await message.reply_text("<blockquote>❌ <b>Jumble Fight sirf groups mein chal sakta hai.</b></blockquote>", parse_mode=ParseMode.HTML)

    target_user = None
    if message.reply_to_message and message.reply_to_message.from_user:
        target_user = message.reply_to_message.from_user
    elif len(message.command) >= 2:
        arg = message.command[1]
        try:
            if arg.isdigit():
                target_user = await app.get_users(int(arg))
            else:
                target_user = await app.get_users(arg)
        except Exception:
            return await message.reply_text("<blockquote>❌ <b>User nahi mila.</b></blockquote>", parse_mode=ParseMode.HTML)
    elif message.entities:
        for entity in message.entities:
            if entity.type.name == "TEXT_MENTION" and entity.user:
                target_user = entity.user
                break

    if not target_user:
        return await message.reply_text(
            "<blockquote>⚔️ <b>𝐉𝐔𝐌𝐁𝐋𝐄 𝐅𝐈𝐆𝐇𝐓 1v1:</b>\n\n"
            "Kisi player ko challenge karne ke liye uske message par reply karke <code>/jumblefight</code> likho ya mention karo:\n"
            "• <code>/jumblefight @username</code>\n"
            "• <code>/jumblefight UserID</code></blockquote>",
            parse_mode=ParseMode.HTML
        )

    if message.from_user and target_user.id == message.from_user.id:
        return await message.reply_text("<blockquote>❌ <b>Khud ke sath fight nahi kar sakte.</b></blockquote>", parse_mode=ParseMode.HTML)

    if target_user.is_bot:
        return await message.reply_text("<blockquote>❌ <b>Bots ke sath match nahi ho sakta.</b></blockquote>", parse_mode=ParseMode.HTML)

    ensure_user(message.from_user)
    ensure_user(target_user)

    key = message.chat.id
    if key in JUMBLE_FIGHT:
        return await message.reply_text("<blockquote>⚔️ <b>Is group mein already Jumble Fight chal rahi hai.</b></blockquote>", parse_mode=ParseMode.HTML)

    m1 = get_mention(message.from_user) if message.from_user else "Player 1"
    m2 = get_mention(target_user)

    p1_id = message.from_user.id if message.from_user else 0
    p1_name = message.from_user.first_name if message.from_user else "Player 1"

    FIGHT_LOBBY[key] = {
        "p1": p1_id,
        "p2": target_user.id,
        "p1_name": p1_name,
        "p2_name": target_user.first_name,
        "m1": m1,
        "m2": m2,
        "difficulty": "medium",
        "timer": 60,
        "is_bet": False,
        "bet_amount": 0
    }

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🟢 𝐄ᴀsʏ", callback_data="f_diff_easy"),
            InlineKeyboardButton("🟡 𝐌ᴇᴅɪᴜᴍ", callback_data="f_diff_medium"),
            InlineKeyboardButton("🔴 𝐇ᴀʀᴅ", callback_data="f_diff_hard")
        ],
        [
            InlineKeyboardButton("⏱️ 30s", callback_data="f_time_30"),
            InlineKeyboardButton("⏱️ 45s", callback_data="f_time_45"),
            InlineKeyboardButton("⏱️ 60s", callback_data="f_time_60")
        ],
        [
            InlineKeyboardButton("✅ 𝐀ᴄᴄᴇᴘᴛ 𝐂ʜᴀʟʟᴇɴɢᴇ", callback_data="f_accept"),
            InlineKeyboardButton("❌ 𝐃ᴇᴄʟɪɴᴇ", callback_data="f_decline")
        ]
    ])

    await message.reply_text(
        f"<blockquote>⚔️ <b>𝐉𝐔𝐌𝐁𝐋𝐄 𝐅𝐈𝐆𝐇𝐓 1v1 𝐂𝐇𝐀𝐋𝐋𝐄𝐍𝐆𝐄!</b>\n\n"
        f"👤 <b>𝐂ʜᴀʟʟᴇɴɢᴇʀ:</b> {m1} (<code>{p1_id}</code>)\n"
        f"🎯 <b>𝐓ᴀʀɢᴇᴛ:</b> {m2} (<code>{target_user.id}</code>)\n\n"
        f"⚙️ <b>𝐒ᴇᴛᴛɪɴɢs:</b> Mode: <code>Medium</code> | Timer: <code>60s</code>\n\n"
        f"👉 {m2}, match shuru karne ke liye <b>Accept Challenge</b> par click karo!</blockquote>",
        reply_markup=kb,
        parse_mode=ParseMode.HTML
    )

@app.on_message(filters.command(["jumblebetfight", "betfight"]))
async def jumble_bet_fight_cmd(_, message: Message):
    if not is_group(message):
        return await message.reply_text("<blockquote>❌ <b>Jumble Bet Fight sirf groups mein chal sakti hai.</b></blockquote>", parse_mode=ParseMode.HTML)

    if not message.from_user:
        return

    ensure_user(message.from_user)
    u1 = get_user(message.from_user.id)

    parts = message.command[1:]
    target_user = None

    if message.reply_to_message and message.reply_to_message.from_user:
        target_user = message.reply_to_message.from_user
    else:
        if message.entities:
            for entity in message.entities:
                if entity.type.name == "TEXT_MENTION" and entity.user:
                    target_user = entity.user
                    break

    diff = "medium"
    amount = 0

    clean_parts = []
    for p in parts:
        if p.startswith("@"):
            if not target_user:
                try:
                    target_user = await app.get_users(p)
                except Exception:
                    pass
        elif p.isdigit():
            clean_parts.append(p)
        elif p.lower() in ("easy", "medium", "hard"):
            diff = p.lower()
        else:
            if not target_user:
                try:
                    target_user = await app.get_users(p)
                except Exception:
                    pass

    for p in clean_parts:
        if int(p) >= 100:
            amount = int(p)
            break

    if not target_user or amount < 100:
        return await message.reply_text(
            "<blockquote>💰 <b>𝐉𝐔𝐌𝐁𝐋𝐄 𝐁𝐄𝐓 𝐅𝐈𝐆𝐇𝐓 𝐔𝐒𝐀𝐆𝐄:</b>\n\n"
            "• <code>/jumblebetfight easy 500 @username</code>\n"
            "• <code>/jumblebetfight hard 1000 UserID</code>\n"
            "• Kisi player ke message par reply karke: <code>/jumblebetfight medium 200</code>\n\n"
            "📌 <b>Rules:</b>\n"
            "- Minimum Bet: <b>100 points</b>\n"
            "- 75% Winner Reward | 25% Loser Cashback\n"
            "- Comeback rematch par 25%+25% pot aur 100 stars recovery!</blockquote>",
            parse_mode=ParseMode.HTML
        )

    if target_user.id == message.from_user.id:
        return await message.reply_text("<blockquote>❌ <b>Khud ke sath bet match nahi khel sakte.</b></blockquote>", parse_mode=ParseMode.HTML)

    if target_user.is_bot:
        return await message.reply_text("<blockquote>❌ <b>Bots ke sath bet match nahi ho sakta.</b></blockquote>", parse_mode=ParseMode.HTML)

    ensure_user(target_user)
    u2 = get_user(target_user.id)

    if u1["points"] < amount:
        return await message.reply_text(f"<blockquote>❌ <b>Aapke paas पर्याप्त points nahi hain!</b>\nAapka balance: <code>{u1['points']} pts</code> | Bet: <code>{amount} pts</code></blockquote>", parse_mode=ParseMode.HTML)

    if u2["points"] < amount:
        m2_temp = get_mention(target_user)
        return await message.reply_text(f"<blockquote>❌ {m2_temp} ke paas bet lagane ke liye poore points nahi hain!\nOpponent balance: <code>{u2['points']} pts</code> | Bet: <code>{amount} pts</code></blockquote>", parse_mode=ParseMode.HTML)

    key = message.chat.id
    if key in JUMBLE_FIGHT:
        return await message.reply_text("<blockquote>⚔️ <b>Is group mein already match chal raha hai, khatam hone tak wait karein.</b></blockquote>", parse_mode=ParseMode.HTML)

    m1 = get_mention(message.from_user)
    m2 = get_mention(target_user)

    FIGHT_LOBBY[key] = {
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
        "is_rebet": False,
        "orig_stake": amount
    }

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"{'✅ ' if diff=='easy' else ''}🟢 𝐄ᴀsʏ", callback_data="f_diff_easy"),
            InlineKeyboardButton(f"{'✅ ' if diff=='medium' else ''}🟡 𝐌ᴇᴅɪᴜᴍ", callback_data="f_diff_medium"),
            InlineKeyboardButton(f"{'✅ ' if diff=='hard' else ''}🔴 𝐇ᴀʀᴅ", callback_data="f_diff_hard")
        ],
        [
            InlineKeyboardButton("⏱️ 30s", callback_data="f_time_30"),
            InlineKeyboardButton("⏱️ 45s", callback_data="f_time_45"),
            InlineKeyboardButton("⏱️ 60s", callback_data="f_time_60")
        ],
        [
            InlineKeyboardButton("✅ 𝐀ᴄᴄᴇᴘᴛ 𝐁ᴇᴛ", callback_data="f_accept"),
            InlineKeyboardButton("❌ 𝐃ᴇᴄʟɪɴᴇ", callback_data="f_decline")
        ]
    ])

    await message.reply_text(
        f"<blockquote>💰 <b>𝐉𝐔𝐌𝐁𝐋𝐄 𝐁𝐄𝐓 𝐅𝐈𝐆𝐇𝐓 𝐂𝐇𝐀𝐋𝐋𝐄𝐍𝐆𝐄!</b>\n\n"
        f"👤 <b>𝐂ʜᴀʟʟᴇɴɢᴇʀ:</b> {m1} (<code>{message.from_user.id}</code>)\n"
        f"🎯 <b>𝐓ᴀʀɢᴇᴛ:</b> {m2} (<code>{target_user.id}</code>)\n\n"
        f"💵 <b>𝐁ᴇᴛ 𝐒ᴛᴀᴋᴇ:</b> <code>{amount} points each</code> (Pot: <code>{amount * 2} pts</code>)\n"
        f"🏆 <b>75% 𝐖ɪɴɴᴇʀ 𝐏ᴀʏᴏᴜᴛ:</b> <code>{int(amount * 2 * 0.75)} pts</code>\n"
        f"🛡️ <b>25% 𝐋ᴏsᴇʀ 𝐂ᴀs𝐇ʙᴀᴄᴋ:</b> <code>{amount * 2 - int(amount * 2 * 0.75)} pts</code>\n"
        f"⚙️ <b>𝐌ᴏᴅᴇ:</b> <code>{diff.title()}</code> | ⏱️ <b>𝐓ɪᴍᴇʀ:</b> <code>60s</code>\n\n"
        f"👉 {m2}, match shuru karne ke liye <b>Accept Bet</b> par click karo!\n"
        f"<i>(Points tab hi deduct honge jab target accept karega)</i></blockquote>",
        reply_markup=kb,
        parse_mode=ParseMode.HTML
    )

# ============================================================
# COMMAND HANDLERS & WIZARD BUILDERS
# ============================================================

@app.on_message(filters.command("start"))
async def start_cmd(_, message: Message):
    ensure_user(message.from_user)
    text = (
        "<blockquote>🧩 <b>𝐖ᴇʟᴄᴏᴍᴇ 𝐓ᴏ 𝐀ᴅᴠᴀɴᴄᴇᴅ 𝐉ᴜᴍʙʟᴇ 𝐁ᴏᴛ!</b></blockquote>\n\n"
        "<blockquote>🎮 <b>𝐆ᴀᴍᴇ 𝐂ᴏᴍᴍᴀɴᴅs:</b>\n"
        "• <code>/jumble</code> — 𝐒ᴛᴀʀᴛ 𝐀ᴜᴛᴏ-ʟᴏᴏᴘ 𝐉ᴜᴍʙʟᴇ 𝐆ᴀᴍᴇ\n"
        "• <code>/jumblefight @user</code> — 1v1 𝐁ᴀᴛᴛʟᴇ 𝐌ᴏᴅᴇ\n"
        "• <code>/jumblebetfight [mode] [amount] @user</code> — 1v1 𝐁ᴇᴛ 𝐁ᴀᴛᴛʟᴇ\n"
        "• <code>/shop</code> — 𝐏ᴏᴡᴇʀ & 𝐄𝐗𝐏 𝐒ʜᴏᴘ\n"
        "• <code>/eventlist</code> — 𝐀ᴄᴛɪᴠᴇ 𝐌ʏsᴛᴇʀʏ 𝐄ᴠᴇɴᴛs\n"
        "• <code>/settings</code> — 𝐀ᴅᴍɪɴ 𝐏ᴀɴᴇʟ</blockquote>\n\n"
        "<blockquote>🎁 <b>𝐅ʀᴇᴇ 𝐏ᴏɪɴᴛs & 𝐑ᴇᴡᴀʀᴅs:</b>\n"
        "• <code>/daily</code> — 𝐂ʟᴀɪᴍ 𝐃ᴀɪʟʏ 𝐁ᴏɴᴜs (𝐃𝐌 ᴏɴʟʏ)\n"
        "• <code>/bonus</code> — 𝐂ʟᴀɪᴍ 𝐆ʀᴏᴜᴘ 𝐀ᴅᴅɪᴛɪᴏɴ 𝐁ᴏɴᴜs</blockquote>\n\n"
        "<blockquote>📊 <b>𝐒ᴛᴀᴛs & 𝐑ᴀɴᴋɪɴɢs:</b>\n"
        "• <code>/stats [@user / ID]</code> — 𝐘ᴏᴜʀ ᴏʀ 𝐀ɴʏᴏɴᴇ's 𝐒ᴛᴀᴛs & 𝐋ᴇᴠᴇʟ\n"
        "• <code>/leaderboard</code> — 𝐓ᴏᴘ 𝐏ʟᴀʏᴇʀs 𝐑ᴀɴᴋs</blockquote>"
    )

    dm_markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💬 𝐒ᴜᴘᴘᴏʀᴛ", url=SUPPORT_GC),
            InlineKeyboardButton("➕ 𝐀ᴅᴅ 𝐌ᴇ", url=ADD_ME_URL)
        ],
        [
            InlineKeyboardButton("🛍️ 𝐎ᴘᴇɴ 𝐒ʜᴏᴘ", callback_data="open_shop_btn"),
            InlineKeyboardButton("📅 𝐄ᴠᴇɴᴛ 𝐋ɪsᴛ", callback_data="open_eventlist_btn")
        ]
    ])

    if message.chat.type in (ChatType.PRIVATE,):
        try:
            await message.reply_photo(photo=START_IMG, caption=text, reply_markup=dm_markup, parse_mode=ParseMode.HTML)
        except Exception:
            await message.reply_text(text, reply_markup=dm_markup, parse_mode=ParseMode.HTML)
    else:
        await message.reply_text(text, reply_markup=dm_markup, parse_mode=ParseMode.HTML)

@app.on_message(filters.command("help"))
async def help_cmd(_, message: Message):
    is_user_auth = is_authed(message.from_user.id) if message.from_user else False
    text = (
        "<blockquote>🧩 <b>𝐉ᴜᴍʙʟᴇ 𝐂ᴏᴍᴍᴀɴᴅs 𝐆ᴜɪᴅᴇ</b>\n\n"
        "• <code>/jumble</code> — 𝐒ᴛᴀʀᴛ ᴀᴜᴛᴏ-ʟᴏᴏᴘɪɴɢ ᴊᴜᴍʙʟᴇ ɢᴀᴍᴇ\n"
        "• <code>/jumblefight @user</code> — 1v1 ʙᴀᴛᴛʟᴇ ᴍᴀᴛᴄʜ\n"
        "• <code>/jumblebetfight [mode] [amount] @user</code> — 1v1 ʙᴇᴛ ᴍᴀᴛᴄʜ\n"
        "• <code>/shop</code> — 𝐏ᴏᴡᴇʀ 𝐂ᴀʀᴅ & 𝐄𝐗𝐏 𝐒ʜᴏᴘ\n"
        "• <code>/eventlist</code> — 𝐀ᴄᴛɪᴠᴇ 𝐌ʏsᴛᴇʀʏ 𝐄ᴠᴇɴᴛs\n"
        "• <code>/stats [@user / ID]</code> — 𝐕ɪᴇᴡ ᴀɴʏ ᴘʟᴀʏᴇʀ's sᴛᴀᴛs\n"
        "• <code>/settings</code> — 𝐀ᴅᴍɪɴ sᴛᴀʀᴛ/sᴛᴏᴘ & ɢᴀᴍᴇ sᴇᴛᴛɪɴɢs\n"
        "• <code>/daily</code> — 𝐂ʟᴀɪᴍ ᴅᴀɪʟʏ ᴘᴏɪɴᴛs (𝐃𝐌 ᴏɴʟʏ)\n"
        "• <code>/bonus</code> — 𝐂ʟᴀɪᴍ ɢʀᴏᴜᴘ ᴀᴅᴍɪɴ ʀᴇᴡᴀʀᴅ (𝐆ʀᴏᴜᴘ ᴏɴʟʏ)\n"
        "• <code>/leaderboard</code> — 𝐓ᴏᴘ ᴘʟᴀʏᴇʀs ʀᴀɴᴋɪɴɢ</blockquote>"
    )
    if is_user_auth:
        text += (
            "\n\n<blockquote>🔐 <b>𝐀ᴜᴛʜ / 𝐀ᴅᴍɪɴ 𝐂ᴏᴍᴍᴀɴᴅs:</b>\n"
            "• <code>/setcard [point|exp] [price] [hours] [min_lvl]</code> — Configure Shop Cards\n"
            "• <code>/setexp [easy|medium|hard] [exp]</code> — Set Mode Base EXP\n"
            "• <code>/setglobalexp [exp]</code> — Set EXP needed per Level Up\n"
            "• <code>/storeexpprize [price] [exp]</code> — Set Shop Instant EXP Pack\n"
            "• <code>/setevent</code> — <b>Step-by-step Interactive Event Creator Wizard</b>\n"
            "• <code>/startevent</code> / <code>/stopevent</code> — Mystery Event Toggle\n"
            "• <code>/addeventword word1 word2</code> — Add mystery event words\n"
            "• <code>/deleventword word</code> — Delete event word\n"
            "• <code>/eventwords</code> — View event word bank\n"
            "• <code>/addstar [pts] @user</code> — Manually credit stars\n"
            "• <code>/deductstar [pts] @user</code> — Manually debit stars\n"
            "• <code>/calculate @user</code> — Full detailed player audit calculator\n"
            "• <code>/log [on|off]</code> — Logger channel toggle\n"
            "• <code>/word</code> — 𝐕ɪᴇᴡ ᴄᴀᴛᴇɢᴏʀɪᴢᴇᴅ ᴡᴏʀᴅ ʙᴀɴᴋ\n"
            "• <code>/addword easy cat dog bird</code> — 𝐁ᴜʟᴋ ᴀᴅᴅ ᴡᴏʀᴅs\n"
            "• <code>/delword easy word</code> — 𝐃ᴇʟᴇᴛᴇ ᴡᴏʀᴅ ғʀᴏᴍ ʙᴀɴᴋ\n"
            "• <code>/delallword easy</code> — <b>𝐃ᴇʟᴇᴛᴇ ᴀʟʟ ᴡᴏʀᴅs ᴏғ ᴀ ᴍᴏᴅᴇ</b>\n"
            "• <code>/setpoints [easy|med|hard] [pts]</code> — 𝐒ᴇᴛ ɢʟᴏʙᴀʟ ᴘᴏɪɴᴛs\n"
            "• <code>/sethint [easy|med|hard] [hints]</code> — 𝐒ᴇᴛ ɢʟᴏʙᴀʟ ʜɪɴᴛs\n"
            "• <code>/update</code> — 𝐆ɪᴛ sᴛᴀsʜ, ᴘᴜʟʟ & 𝐀ᴜᴛᴏ-ʀᴇsᴜᴍᴇ</blockquote>"
        )
    if message.from_user and is_owner(message.from_user.id):
        text += (
            "\n\n<blockquote>👑 <b>𝐎ᴡɴᴇʀ 𝐂ᴏᴍᴍᴀɴᴅs:</b>\n"
            "• <code>/auth @user</code> — 𝐆ʀᴀɴᴛ ᴀᴜᴛʜ ᴀᴄᴄᴇss\n"
            "• <code>/unauth @user</code> — 𝐑ᴇᴠᴏᴋᴇ ᴀᴜᴛʜ ᴀᴄᴄᴇss\n"
            "• <code>/authlist</code> — 𝐋ɪsᴛ ᴏғ ᴀᴜᴛʜᴏʀɪᴢᴇᴅ ᴜsᴇʀs\n"
            "• <code>/backup</code> — 𝐃ᴏᴡɴʟᴏᴀᴅ 𝐋ᴀᴛᴇsᴛ 𝐃ᴀᴛᴀʙᴀsᴇ (.db)</blockquote>"
        )
    await message.reply_text(text, parse_mode=ParseMode.HTML)

# ============================================================
# INTERACTIVE STEP-BY-STEP EVENT CREATOR WIZARD (/setevent)
# ============================================================

@app.on_message(filters.command("setevent"))
async def set_event_wizard_cmd(_, message: Message):
    if not message.from_user or not is_authed(message.from_user.id):
        return await message.reply_text("<blockquote>❌ <b>Sirf Owner aur Auth users events create kar sakte hain.</b></blockquote>", parse_mode=ParseMode.HTML)

    uid = message.from_user.id
    EVENT_WIZARD[uid] = {"step": 1, "title": "", "word": "", "hint": "0", "stars": 0, "exp": 0, "interval": 4, "target": "group"}

    await message.reply_text(
        "<blockquote>🌟 <b>𝐄𝐕𝐄𝐍𝐓 𝐂𝐑𝐄𝐀𝐓𝐎𝐑 𝐖𝐈𝐙𝐀𝐑𝐃 (Step 1/7)</b>\n\n"
        "Is event ka title ya naam kya rakhna chahte hain? (Jaise: <i>Weekend Mystery Drop</i>)\n\n"
        "<i>(Cancel karne ke liye <code>/cancel</code> likhein)</i></blockquote>",
        parse_mode=ParseMode.HTML
    )

@app.on_message(filters.command("cancel"))
async def cancel_wizard(_, message: Message):
    uid = message.from_user.id
    if uid in EVENT_WIZARD:
        del EVENT_WIZARD[uid]
        await message.reply_text("<blockquote>❌ <b>Event creator wizard cancelled.</b></blockquote>", parse_mode=ParseMode.HTML)

# ============================================================
# EXP & LEVEL CONFIGURATION COMMANDS
# ============================================================

@app.on_message(filters.command("setglobalexp"))
async def set_global_exp_cmd(_, message: Message):
    if not message.from_user or not is_authed(message.from_user.id):
        return await message.reply_text("<blockquote>❌ <b>Sirf Owner aur Auth users global EXP per level set kar sakte hain.</b></blockquote>", parse_mode=ParseMode.HTML)

    args = message.command[1:]
    if not args:
        return await message.reply_text(
            "<blockquote><b>Usage:</b>\n<code>/setglobalexp [exp_required_per_level]</code>\n\n"
            "<b>Example:</b>\n<code>/setglobalexp 500</code> (Ab har 500 EXP par 1 level badhega)</blockquote>",
            parse_mode=ParseMode.HTML
        )

    clean_num = "".join(c for c in args[0] if c.isdigit())
    if not clean_num or int(clean_num) <= 0:
        return await message.reply_text("<blockquote>❌ <b>Invalid number.</b></blockquote>", parse_mode=ParseMode.HTML)

    val = int(clean_num)
    set_global_config("global_exp_per_lvl", val)
    
    users = DB.execute("SELECT user_id, exp FROM users").fetchall()
    for u in users:
        new_lvl = max(1, ((u["exp"] or 0) // val) + 1)
        DB.execute("UPDATE users SET level=? WHERE user_id=?", (new_lvl, u["user_id"]))
    DB.commit()

    await message.reply_text(
        f"<blockquote>✅ <b>Global Level Up Requirement Updated!</b>\n\n"
        f"🎯 Har <code>{val} EXP</code> earn karne par 1 Level badhega!\n"
        f"Sabhi users ke level instantly re-calculated ho gaye hain.</blockquote>",
        parse_mode=ParseMode.HTML
    )

@app.on_message(filters.command("storeexpprize"))
async def set_store_exp_prize_cmd(_, message: Message):
    if not message.from_user or not is_authed(message.from_user.id):
        return await message.reply_text("<blockquote>❌ <b>Sirf Owner aur Auth users shop EXP pack configure kar sakte hain.</b></blockquote>", parse_mode=ParseMode.HTML)

    numbers = [int(n) for n in re.findall(r"\d+", message.text)]
    if len(numbers) < 2:
        return await message.reply_text(
            "<blockquote><b>Usage:</b>\n"
            "<code>/storeexpprize [stars_cost] [exp_reward]</code>\n\n"
            "<b>Example:</b>\n"
            "<code>/storeexpprize 1000 500</code> (1000 stars me 500 EXP milega)</blockquote>",
            parse_mode=ParseMode.HTML
        )

    cost, exp_rew = numbers[0], numbers[1]
    set_global_config("shop_exp_cost", cost)
    set_global_config("shop_exp_reward", exp_rew)

    await message.reply_text(
        f"<blockquote>✅ <b>Shop Instant EXP Pack Updated!</b>\n\n"
        f"💵 <b>Price:</b> ⭐ <code>{cost} Stars/Points</code>\n"
        f"⚡ <b>EXP Gain:</b> <code>+{exp_rew} EXP</code></blockquote>",
        parse_mode=ParseMode.HTML
    )

@app.on_message(filters.command("setexp"))
async def set_exp_cmd(_, message: Message):
    if not message.from_user or not is_authed(message.from_user.id):
        return await message.reply_text("<blockquote>❌ <b>Sirf Owner aur Auth users EXP set kar sakte hain.</b></blockquote>", parse_mode=ParseMode.HTML)

    args = message.command[1:]
    if len(args) < 2:
        return await message.reply_text(
            "<blockquote><b>Usage:</b>\n"
            "<code>/setexp [easy|medium|hard] [exp_amount]</code>\n\n"
            "<b>Example:</b>\n"
            "<code>/setexp easy 15</code></blockquote>",
            parse_mode=ParseMode.HTML
        )

    diff = args[0].lower()
    if diff not in ("easy", "medium", "hard"):
        return await message.reply_text("<blockquote>❌ <b>Mode must be:</b> <code>easy</code>, <code>medium</code>, ya <code>hard</code>.</blockquote>", parse_mode=ParseMode.HTML)

    clean_num = "".join(c for c in args[1] if c.isdigit())
    if not clean_num:
        return await message.reply_text("<blockquote>❌ <b>Invalid number.</b></blockquote>", parse_mode=ParseMode.HTML)

    val = int(clean_num)
    set_global_config(f"exp_{diff}", val)
    await message.reply_text(f"<blockquote>✅ <b>{diff.title()} mode EXP reward set to <code>{val} EXP</code>!</b></blockquote>", parse_mode=ParseMode.HTML)

# ============================================================
# EVENT LIST COMMAND
# ============================================================

@app.on_message(filters.command(["eventlist", "events"]))
async def event_list_cmd(_, message: Message):
    events = DB.execute("SELECT * FROM events_bank").fetchall()
    if not events:
        return await message.reply_text("<blockquote>📅 <b>Active Events List:</b>\n\n<i>Filhaal koi mystery events configured nahi hain.</i></blockquote>", parse_mode=ParseMode.HTML)

    text = "<blockquote>📅 <b>𝐌𝐘𝐒𝐓𝐄𝐑𝐘 𝐄𝐕𝐄𝐍𝐓𝐒 𝐋𝐈𝐒𝐓</b>\n\n"
    buttons = []
    for ev in events:
        rem_time = max(0, ev["next_run"] - time.time())
        status_tag = "🟢 Active" if ev["is_active"] else "🔴 Paused"
        text += (
            f"🔹 <b>{ev['title']}</b> (#ID: <code>{ev['id']}</code>) — {status_tag}\n"
            f"• Word: <code>{ev['word'].upper()}</code> | Target: <code>{ev['target_type'].upper()}</code>\n"
            f"• Reward: ⭐ <code>{ev['reward_stars']} pts</code> | ⚡ <code>{ev['reward_exp']} EXP</code>\n"
            f"• Repeats: Every <code>{ev['interval_hrs']} hrs</code> | Next: <code>{format_duration(rem_time)}</code>\n\n"
        )
        buttons.append([
            InlineKeyboardButton(f"🛑 Toggle #{ev['id']}", callback_data=f"ev_toggle_{ev['id']}"),
            InlineKeyboardButton(f"🗑️ Delete #{ev['id']}", callback_data=f"ev_del_{ev['id']}")
        ])
    text += "</blockquote>"

    buttons.append([InlineKeyboardButton("❌ Close", callback_data="close_panel")])
    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.HTML)

# ============================================================
# EVENT WORDS MANAGEMENT & TRIGGER
# ============================================================

@app.on_message(filters.command("startevent"))
async def start_event_cmd(_, message: Message):
    if not message.from_user or not is_authed(message.from_user.id):
        return await message.reply_text("<blockquote>❌ <b>Authorized users only.</b></blockquote>", parse_mode=ParseMode.HTML)

    chat_id = message.chat.id
    DB.execute("UPDATE settings SET event_active=1 WHERE chat_id=?", (chat_id,))
    DB.commit()
    
    first_ev = DB.execute("SELECT id FROM events_bank WHERE is_active=1 LIMIT 1").fetchone()
    if first_ev:
        await dispatch_event_by_id(first_ev["id"], target_chat_id=chat_id)
        await message.reply_text("<blockquote>🚀 <b>Event launched instantly in this chat!</b></blockquote>", parse_mode=ParseMode.HTML)
    else:
        await message.reply_text("<blockquote>⚠️ <b>Pehle <code>/setevent</code> se kam se kam ek event configure karein!</b></blockquote>", parse_mode=ParseMode.HTML)

@app.on_message(filters.command("stopevent"))
async def stop_event_cmd(_, message: Message):
    if not message.from_user or not is_authed(message.from_user.id):
        return await message.reply_text("<blockquote>❌ <b>Authorized users only.</b></blockquote>", parse_mode=ParseMode.HTML)

    chat_id = message.chat.id
    DB.execute("UPDATE settings SET event_active=0 WHERE chat_id=?", (chat_id,))
    DB.commit()
    await message.reply_text("<blockquote>🛑 <b>Event Word Drops Disabled in this chat.</b></blockquote>", parse_mode=ParseMode.HTML)

@app.on_message(filters.command("addeventword"))
async def add_event_word_cmd(_, message: Message):
    if not message.from_user or not is_authed(message.from_user.id):
        return await message.reply_text("<blockquote>❌ <b>Authorized users only.</b></blockquote>", parse_mode=ParseMode.HTML)

    if len(message.command) < 2:
        return await message.reply_text("<blockquote><b>Usage:</b>\n<code>/addeventword supernova kaleidoscope cryptocurrency</code></blockquote>", parse_mode=ParseMode.HTML)

    raw_words = message.text.split(None, 1)[1]
    tokens = re.split(r"[\s,;\"'\n\r]+", raw_words)
    added = []

    for t in tokens:
        w = "".join(c.lower() for c in t if c.isalpha()).strip()
        if len(w) >= 4:
            if w not in EVENT_WORDS:
                EVENT_WORDS.append(w)
                DB.execute("INSERT OR IGNORE INTO event_words(word) VALUES (?)", (w,))
                added.append(w)

    DB.commit()
    await message.reply_text(f"<blockquote>✅ <b>{len(added)}</b> words added to <b>Event Mystery Word Bank</b>!</blockquote>", parse_mode=ParseMode.HTML)

@app.on_message(filters.command("deleventword"))
async def del_event_word_cmd(_, message: Message):
    if not message.from_user or not is_authed(message.from_user.id):
        return await message.reply_text("<blockquote>❌ <b>Authorized users only.</b></blockquote>", parse_mode=ParseMode.HTML)

    if len(message.command) < 2:
        return await message.reply_text("<blockquote><b>Usage:</b>\n<code>/deleventword supernova</code></blockquote>", parse_mode=ParseMode.HTML)

    target = clean_answer(message.command[1])
    if target in EVENT_WORDS:
        EVENT_WORDS.remove(target)
        DB.execute("DELETE FROM event_words WHERE word=?", (target,))
        DB.commit()
        return await message.reply_text(f"<blockquote>🗑️ <b>'{target.upper()}'</b> removed from event words.</blockquote>", parse_mode=ParseMode.HTML)
    await message.reply_text("<blockquote>❌ <b>Word not found in event bank.</b></blockquote>", parse_mode=ParseMode.HTML)

@app.on_message(filters.command("eventwords"))
async def view_event_words_cmd(_, message: Message):
    if not message.from_user or not is_authed(message.from_user.id):
        return await message.reply_text("<blockquote>❌ <b>Authorized users only.</b></blockquote>", parse_mode=ParseMode.HTML)

    if not EVENT_WORDS:
        return await message.reply_text("<blockquote><i>Event word bank is currently empty.</i></blockquote>", parse_mode=ParseMode.HTML)

    sample_words = "  •  ".join(f"<code>{w.upper()}</code>" for w in sorted(EVENT_WORDS)[:50])
    await message.reply_text(
        f"<blockquote>🌟 <b>𝐄𝐕𝐄𝐍𝐓 𝐌𝐘𝐒𝐓𝐄𝐑𝐘 𝐖𝐎𝐑𝐃 𝐁𝐀𝐍𝐊</b> (Total: {len(EVENT_WORDS)})\n\n"
        f"{sample_words}\n\n"
        "➕ <b>Add:</b> <code>/addeventword word1 word2</code>\n"
        "➖ <b>Del:</b> <code>/deleventword word</code></blockquote>",
        parse_mode=ParseMode.HTML
    )

# ============================================================
# SMART CARD SETTER COMMAND (/setcard)
# ============================================================

@app.on_message(filters.command("setcard"))
async def set_card_cmd(_, message: Message):
    if not message.from_user or not is_authed(message.from_user.id):
        return await message.reply_text("<blockquote>❌ <b>Sirf Owner aur Auth users shop cards configure kar sakte hain.</b></blockquote>", parse_mode=ParseMode.HTML)

    raw_str = message.text.lower()
    card_type = None

    if "point" in raw_str:
        card_type = "point"
    elif "exp" in raw_str or "level" in raw_str:
        card_type = "level"

    numbers = [int(n) for n in re.findall(r"\d+", message.text)]

    if not card_type or len(numbers) < 3:
        return await message.reply_text(
            "<blockquote><b>Card Configuration Usage:</b>\n\n"
            "• <code>/setcard point [price] [hours] [min_level]</code>\n"
            "• <code>/setcard exp [price] [hours] [min_level]</code>\n\n"
            "<b>Example:</b>\n"
            "<code>/setcard point 500 4 1</code>\n"
            "<code>/setcard exp 700 6 2</code></blockquote>",
            parse_mode=ParseMode.HTML
        )

    price, hrs, min_lvl = numbers[0], numbers[1], numbers[2]
    prefix = "card_point" if card_type == "point" else "card_level"

    set_global_config(f"{prefix}_price", price)
    set_global_config(f"{prefix}_hrs", hrs)
    set_global_config(f"{prefix}_req_lvl", min_lvl)

    card_title = "Point Multiplication Card (2x Points)" if card_type == "point" else "Level Multiplication Card (2x EXP)"
    await message.reply_text(
        f"<blockquote>✅ <b>{card_title} Updated!</b>\n\n"
        f"💵 <b>Price:</b> <code>{price} Stars/Points</code>\n"
        f"⏱️ <b>Validity:</b> <code>{hrs} Hours</code>\n"
        f"🎖️ <b>Min Level Required:</b> <code>Level {min_lvl}</code></blockquote>",
        parse_mode=ParseMode.HTML
    )

# ============================================================
# STATS COMMAND (SELF & TARGET USER LOOKUP)
# ============================================================

@app.on_message(filters.command(["stats", "stat", "mystats", "score"]))
async def stats_cmd(_, message: Message):
    if not message.from_user:
        return

    target_user = message.from_user
    if message.reply_to_message and message.reply_to_message.from_user:
        target_user = message.reply_to_message.from_user
    elif len(message.command) >= 2:
        arg = message.command[1]
        try:
            if arg.isdigit():
                target_user = await app.get_users(int(arg))
            else:
                target_user = await app.get_users(arg)
        except Exception:
            pass

    ensure_user(target_user)
    u = get_user(target_user.id)
    now = time.time()

    total_fights = u["fight_wins"] + u["fight_losses"]
    winrate = ((u["fight_wins"] / total_fights) * 100) if total_fights else 0
    total_bets = (u["bet_wins"] or 0) + (u["bet_losses"] or 0)
    bet_winrate = (((u["bet_wins"] or 0) / total_bets) * 100) if total_bets else 0
    mention = get_mention(target_user)
    priv_status = "🔒 Private" if u["is_private"] else "🌐 Public"

    pt_boost = format_duration(u["point_card_exp"] - now) if u["point_card_exp"] > now else "None"
    lvl_boost = format_duration(u["level_card_exp"] - now) if u["level_card_exp"] > now else "None"
    cur_lvl = u["level"] or 1
    cur_exp = u["exp"] or 0
    step = get_global_config("global_exp_per_lvl", 500)
    next_exp_bar = f"{cur_exp % step}/{step} EXP"

    await message.reply_text(
        f"<blockquote>👤 {mention} (<code>{target_user.id}</code>)\n\n"
        f"🎖️ <b>𝐋ᴇᴠᴇʟ:</b> <code>Level {cur_lvl}</code> ({next_exp_bar})\n"
        f"⭐ <b>𝐏ᴏɪɴᴛs / 𝐒ᴛᴀʀs:</b> <code>{u['points']}</code>\n"
        f"🧩 <b>𝐒ᴏʟᴠᴇᴅ:</b> <code>{u['solved']}</code>\n"
        f"🔥 <b>𝐒ᴛʀᴇᴀᴋ:</b> <code>{u['streak']}</code> (Best: {u['best_streak']})\n"
        f"🛡️ <b>𝐏ʀɪᴠᴀᴄʏ:</b> <code>{priv_status}</code>\n\n"
        f"⚡ <b>Active Point Card (2x):</b> <code>{pt_boost}</code>\n"
        f"⚡ <b>Active EXP Card (2x):</b> <code>{lvl_boost}</code>\n\n"
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
        [
            InlineKeyboardButton("❌ 𝐂ʟᴏsᴇ", callback_data="close_panel")
        ]
    ])

    return text, kb

@app.on_message(filters.command(["leaderboard", "top", "rank", "lb"]))
async def leaderboard_cmd(_, message: Message):
    chat_id = message.chat.id
    scope = "daily" if is_group(message) else "global"
    text, kb = build_leaderboard_text_and_kb(scope, chat_id)
    await message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)

# ============================================================
# SETTINGS PANEL
# ============================================================

@app.on_message(filters.command(["settings", "setting"]))
async def settings_cmd(_, message: Message):
    if not message.from_user or not await is_admin_or_owner(message.chat, message.from_user.id):
        return await message.reply_text("<blockquote>❌ <b>Only group admins can configure settings.</b></blockquote>", parse_mode=ParseMode.HTML)

    chat_id = message.chat.id
    s = get_settings(chat_id)
    cur_diff = s["default_diff"] if "default_diff" in s.keys() else "medium"
    status_btn = InlineKeyboardButton("⏹️ 𝐒ᴛᴏᴘ 𝐆ᴀᴍᴇ", callback_data="set_stop_game") if s["is_active"] else InlineKeyboardButton("▶️ 𝐒ᴛᴀʀᴛ 𝐆ᴀᴍᴇ", callback_data="set_start_game")
    del_btn = InlineKeyboardButton("🗑️ 𝐀ᴜᴛᴏ-𝐃ᴇʟ: 𝐎𝐍", callback_data="set_toggle_autodel") if s["auto_delete"] else InlineKeyboardButton("🗑️ 𝐀ᴜᴛᴏ-𝐃ᴇʟ: 𝐎𝐅𝐅", callback_data="set_toggle_autodel")

    p_easy = get_global_config("points_easy", 10)
    p_med = get_global_config("points_medium", 20)
    p_hard = get_global_config("points_hard", 30)

    h_easy = get_global_config("hints_easy", 3)
    h_med = get_global_config("hints_medium", 3)
    h_hard = get_global_config("hints_hard", 3)

    kb = InlineKeyboardMarkup([
        [
            status_btn,
            InlineKeyboardButton(f"🎯 𝐌ᴏᴅᴇ: {str(cur_diff).upper()}", callback_data="set_menu_mode")
        ],
        [
            InlineKeyboardButton("⏱️ 𝐓ɪᴍᴇʀs", callback_data="set_menu_timers"),
            del_btn
        ],
        [
            InlineKeyboardButton("❌ 𝐂ʟᴏsᴇ", callback_data="close_panel")
        ]
    ])
    text = (
        f"<blockquote>⚙️ <b>𝐉ᴜᴍʙʟᴇ 𝐆ʀᴏᴜᴘ 𝐒ᴇᴛᴛɪɴɢs</b>\n\n"
        f"🟢 <b>𝐆ᴀᴍᴇ 𝐒ᴛᴀᴛᴜs:</b> <code>{'Running' if s['is_active'] else 'Stopped'}</code>\n"
        f"🗑️ <b>𝐀ᴜᴛᴏ 𝐃ᴇʟᴇᴛᴇ 𝐎ʟᴅ:</b> <code>{'Enabled' if s['auto_delete'] else 'Disabled'}</code>\n"
        f"🎯 <b>𝐃ᴇғᴀᴜʟᴛ 𝐌ᴏᴅᴇ:</b> <code>{str(cur_diff).title()}</code>\n"
        f"⏱️ <b>𝐓ɪᴍᴇʀs:</b> Easy: <code>{s['easy']}s</code> | Med: <code>{s['medium']}s</code> | Hard: <code>{s['hard']}s</code>\n\n"
        f"🌍 <b>𝐆ʟᴏʙᴀʟ 𝐑ᴇᴡᴀʀᴅs:</b> Easy: <code>{p_easy}pts</code> | Med: <code>{p_med}pts</code> | Hard: <code>{p_hard}pts</code>\n"
        f"💡 <b>𝐆ʟᴏʙᴀʟ 𝐇ɪɴᴛs:</b> Easy: <code>{h_easy}</code> | Med: <code>{h_med}</code> | Hard: <code>{h_hard}</code></blockquote>"
    )
    await message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)

# ============================================================
# UNIVERSAL MESSAGE DISPATCHER (WIZARD & ANSWERS)
# ============================================================

ALL_BOT_COMMANDS = {
    "start", "help", "jumble", "jumblefight", "fight", "rapido", "jumblebetfight", "betfight",
    "settings", "setting", "setpoints", "sethint", "setdaily", "setbonus", "daily", "bonus",
    "private", "public", "addword", "addwords", "delword", "delallword", "delallwords",
    "clearword", "clearwords", "word", "words", "auth", "unauth", "authlist", "update", "gitpull",
    "stats", "stat", "mystats", "score", "leaderboard", "top", "rank", "lb", "backup", "dbbackup", "getdb",
    "shop", "store", "setcard", "setreward", "setevent", "startevent", "stopevent", "addeventword", "deleventword",
    "eventwords", "setexp", "eventlist", "events", "cancel", "setglobalexp", "storeexpprize", "addstar", "addstars",
    "addpoint", "addpoints", "deductstar", "deductstars", "removestar", "minusstar", "calculate", "calc", "audit", "log", "logging"
}

@app.on_message(filters.text)
async def universal_text_dispatcher(_, message: Message):
    if not message.from_user or not message.text:
        return

    uid = message.from_user.id
    txt = message.text.strip()

    # 1. Wizard Steps
    if uid in EVENT_WIZARD and not txt.startswith("/"):
        data = EVENT_WIZARD[uid]
        step = data["step"]

        if step == 1:
            data["title"] = txt
            data["step"] = 2
            return await message.reply_text(
                "<blockquote>🌟 <b>𝐄𝐕𝐄𝐍𝐓 𝐂𝐑𝐄𝐀𝐓𝐎𝐑 𝐖𝐈𝐙𝐀𝐑𝐃 (Step 2/7)</b>\n\n"
                "Ab is event ka <b>Unique Word</b> kya hoga?\n"
                "<i>(Agar random choose karwana chahte hain to <code>random</code> likhein)</i></blockquote>",
                parse_mode=ParseMode.HTML
            )
        elif step == 2:
            w = txt.lower().strip()
            if w != "random" and len("".join(c for c in w if c.isalpha())) < 3:
                return await message.reply_text("<blockquote>❌ <b>Word kam se kam 3 letters ka hona chahiye ya 'random' likhein.</b></blockquote>", parse_mode=ParseMode.HTML)
            data["word"] = w
            data["step"] = 3
            return await message.reply_text(
                "<blockquote>🌟 <b>𝐄𝐕𝐄𝐍𝐓 𝐂𝐑𝐄𝐀𝐓𝐎𝐑 𝐖𝐈𝐙𝐀𝐑𝐃 (Step 3/7)</b>\n\n"
                "Is event ke liye koi <b>Hint</b> dena chahte hain?\n"
                "<i>(Agar hint nahi deni toh sirf <b>0</b> likh kar bhej dein)</i></blockquote>",
                parse_mode=ParseMode.HTML
            )
        elif step == 3:
            data["hint"] = txt
            data["step"] = 4
            return await message.reply_text(
                "<blockquote>🌟 <b>𝐄𝐕𝐄𝐍𝐓 𝐂𝐑𝐄𝐀𝐓𝐎𝐑 𝐖𝐈𝐙𝐀𝐑𝐃 (Step 4/7)</b>\n\n"
                "Solve karne par winner ko kitne <b>Stars/Points</b> milne chahiye? (Jaise: <code>500</code>)</blockquote>",
                parse_mode=ParseMode.HTML
            )
        elif step == 4:
            nums = re.findall(r"\d+", txt)
            if not nums:
                return await message.reply_text("<blockquote>❌ <b>Kripya valid number enter karein.</b></blockquote>", parse_mode=ParseMode.HTML)
            data["stars"] = int(nums[0])
            data["step"] = 5
            return await message.reply_text(
                "<blockquote>🌟 <b>𝐄𝐕𝐄𝐍𝐓 𝐂𝐑𝐄𝐀𝐓𝐎𝐑 𝐖𝐈𝐙𝐀𝐑𝐃 (Step 5/7)</b>\n\n"
                "Solve karne par winner ko kitna <b>EXP</b> milna chahiye? (Jaise: <code>1000</code>)</blockquote>",
                parse_mode=ParseMode.HTML
            )
        elif step == 5:
            nums = re.findall(r"\d+", txt)
            if not nums:
                return await message.reply_text("<blockquote>❌ <b>Kripya valid number enter karein.</b></blockquote>", parse_mode=ParseMode.HTML)
            data["exp"] = int(nums[0])
            data["step"] = 6
            return await message.reply_text(
                "<blockquote>🌟 <b>𝐄𝐕𝐄𝐍𝐓 𝐂𝐑𝐄𝐀𝐓𝐎𝐑 𝐖𝐈𝐙𝐀𝐑𝐃 (Step 6/7)</b>\n\n"
                "Yeh event har kitne <b>Hours (Ghante)</b> baad repeat hona chahiye? (Jaise: <code>4</code>)</blockquote>",
                parse_mode=ParseMode.HTML
            )
        elif step == 6:
            nums = re.findall(r"\d+", txt)
            if not nums:
                return await message.reply_text("<blockquote>❌ <b>Kripya valid number enter karein.</b></blockquote>", parse_mode=ParseMode.HTML)
            data["interval"] = int(nums[0])
            data["step"] = 7

            kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("👥 Groups Only", callback_data="ev_target_group"),
                    InlineKeyboardButton("💬 DMs Only", callback_data="ev_target_dm")
                ],
                [
                    InlineKeyboardButton("🌍 Both Groups & DMs", callback_data="ev_target_both")
                ]
            ])

            return await message.reply_text(
                "<blockquote>🌟 <b>𝐄𝐕𝐄𝐍𝐓 𝐂𝐑𝐄𝐀𝐓𝐎𝐑 𝐖𝐈𝐙𝐀𝐑𝐃 (Step 7/7)</b>\n\n"
                "Yeh event kahan run hona chahiye? Neeche diye gaye button par click karein:</blockquote>",
                reply_markup=kb,
                parse_mode=ParseMode.HTML
            )

    if txt.startswith("/") or txt.startswith("!") or txt.startswith("."):
        cmd_candidate = txt[1:].split()[0].split("@")[0].lower()
        if cmd_candidate in ALL_BOT_COMMANDS:
            return

    if is_group(message):
        await group_answer_handler(_, message)

# ============================================================
# UNIFIED ANSWER HANDLER (LEVEL, EXP & POWER ENHANCED)
# ============================================================

async def group_answer_handler(_, message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    cleaned_input = clean_answer(message.text)
    if not cleaned_input:
        return

    now = time.time()

    # 1. Mystery Event Word Check
    ev_game = DB.execute("SELECT * FROM event_games WHERE chat_id=? AND solved=0", (chat_id,)).fetchone()
    if ev_game and now <= ev_game["expires"] and cleaned_input == clean_answer(ev_game["word"]):
        updated = DB.execute("UPDATE event_games SET solved=1 WHERE chat_id=? AND solved=0", (chat_id,))
        if updated.rowcount == 1:
            DB.commit()
            ensure_user(message.from_user)
            u = get_user(user_id)

            ev = DB.execute("SELECT * FROM events_bank WHERE id=?", (ev_game["event_id"],)).fetchone()
            b_pts = ev["reward_stars"] if ev else 250
            b_exp = ev["reward_exp"] if ev else 500
            c_hrs = 2

            if u["point_card_exp"] > now:
                b_pts *= 2
            if u["level_card_exp"] > now:
                b_exp *= 2

            new_pt_exp = max(u["point_card_exp"], now) + (c_hrs * 3600)
            new_exp = (u["exp"] or 0) + b_exp
            new_lvl = calculate_level(new_exp)

            DB.execute("""
                UPDATE users
                SET points=points+?, exp=?, level=?, point_card_exp=?
                WHERE user_id=?
            """, (b_pts, new_exp, new_lvl, new_pt_exp, user_id))
            
            DB.execute("INSERT INTO score_history (user_id, chat_id, points, tag, timestamp) VALUES (?, ?, ?, 'event', ?)", (user_id, chat_id, b_pts, now))
            DB.commit()

            if ev_game["message_id"]:
                await safe_delete_and_unpin(chat_id, ev_game["message_id"])

            u_mention = get_mention(message.from_user)
            ev_msg = await message.reply_text(
                f"<blockquote>🎉 <b>𝐄𝐕𝐄𝐍𝐓 𝐌𝐘𝐒𝐓𝐄𝐑𝐘 𝐖𝐎𝐑𝐃 𝐒𝐎𝐋𝐕𝐄𝐃!</b>\n\n"
                f"👤 {u_mention} (<code>{user_id}</code>)\n"
                f"✅ <b>Word:</b> <code>{ev_game['word'].upper()}</code>\n"
                f"⭐ <b>+{b_pts} Points/Stars</b>\n"
                f"⚡ <b>+{b_exp} EXP</b> (Level: <code>{new_lvl}</code>)\n"
                f"🃏 <b>Bonus Activated:</b> <code>Point Multiplier (2x for {c_hrs} hrs)</code></blockquote>",
                parse_mode=ParseMode.HTML
            )
            asyncio.create_task(delete_after(ev_msg, 6))

            # Send event log to logger group
            asyncio.create_task(send_log_notification(message.chat, message.from_user, ev_game["word"], b_pts, b_exp, u['points'] + b_pts, new_exp, new_lvl, is_event=True))
            return

    # 2. Active Jumble Fight Check
    if chat_id in JUMBLE_FIGHT:
        async with LOCK:
            game = JUMBLE_FIGHT.get(chat_id)
            if not game or user_id not in game["players"]:
                return

            if time.time() <= game["expires"] and cleaned_input == clean_answer(game["word"]):
                curr = asyncio.current_task()
                if game.get("task") and game["task"] is not curr and not game["task"].done():
                    try:
                        game["task"].cancel()
                    except Exception:
                        pass

                game["scores"][user_id] += 1
                
                s = get_settings(chat_id)
                if s["auto_delete"] and game.get("msg_id"):
                    await safe_delete_and_unpin(chat_id, game["msg_id"])

                u_mention = get_mention(message.from_user)
                r_msg = await message.reply_text(
                    f"<blockquote>⚡ {u_mention} (<code>{user_id}</code>) <b>𝐖𝐎𝐍 𝐑𝐎𝐔𝐍𝐃 {game['round']}!</b>\n"
                    f"🏆 <b>Round Score:</b> <code>{game['scores'][user_id]}</code></blockquote>",
                    parse_mode=ParseMode.HTML
                )
                if s["auto_delete"]:
                    asyncio.create_task(delete_after(r_msg, 4))
                    
                await asyncio.sleep(2.5)
                asyncio.create_task(fight_next(chat_id))
                return
        return

    # 3. Normal Loop Game Check
    game = DB.execute("SELECT * FROM games WHERE chat_id=? AND solved=0", (chat_id,)).fetchone()
    if not game or time.time() > game["expires"]:
        return

    if cleaned_input == clean_answer(game["word"]):
        updated = DB.execute("UPDATE games SET solved=1 WHERE chat_id=? AND solved=0", (chat_id,))
        if updated.rowcount != 1:
            return
        DB.commit()

        ensure_user(message.from_user)
        u = get_user(user_id)
        settings = get_settings(chat_id)
        
        diff = game["difficulty"]
        pts_reward = get_global_config(f"points_{diff}", 10)
        base_exp_reward = get_global_config(f"exp_{diff}", 30)

        pt_active = u["point_card_exp"] > now
        lvl_active = u["level_card_exp"] > now

        final_pts = pts_reward * 2 if pt_active else pts_reward
        final_exp = base_exp_reward * 2 if lvl_active else base_exp_reward

        new_streak = u["streak"] + 1
        best = max(new_streak, u["best_streak"])

        cur_exp = (u["exp"] or 0) + final_exp
        new_lvl = calculate_level(cur_exp)

        DB.execute("""
            UPDATE users
            SET points=points+?, solved=solved+1, streak=?, best_streak=?, exp=?, level=?
            WHERE user_id=?
        """, (final_pts, new_streak, best, cur_exp, new_lvl, user_id))
        
        DB.execute("""
            INSERT INTO score_history (user_id, chat_id, points, tag, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, chat_id, final_pts, diff, time.time()))
        DB.commit()

        if settings["auto_delete"] and game["message_id"]:
            await safe_delete_and_unpin(chat_id, game["message_id"])

        u_mention = get_mention(message.from_user)
        
        power_tag = ""
        if pt_active:
            power_tag += f" ⚡ [2x Points: {format_duration(u['point_card_exp'] - now)}]"
        if lvl_active:
            power_tag += f" 🎖️ [2x EXP: {format_duration(u['level_card_exp'] - now)}]"

        c_msg = await message.reply_text(
            f"<blockquote>🎉 <b>𝐂𝐎𝐑𝐑𝐄𝐂𝐓!</b>\n\n"
            f"👤 {u_mention} (<code>{user_id}</code>)\n"
            f"✅ <b>Answer:</b> <code>{game['word'].upper()}</code>\n"
            f"⭐ <b>+{final_pts} points</b> | ⚡ <b>+{final_exp} EXP</b> (Lvl {new_lvl}){power_tag}\n"
            f"🔥 <b>Current Streak:</b> <code>{new_streak}</code>\n\n"
            f"🔄 <i>Next puzzle coming in 3 seconds...</i></blockquote>",
            parse_mode=ParseMode.HTML
        )

        if settings["auto_delete"]:
            asyncio.create_task(delete_after(c_msg, 4))

        # Send log to logger group
        asyncio.create_task(send_log_notification(message.chat, message.from_user, game["word"], final_pts, final_exp, u['points'] + final_pts, cur_exp, new_lvl, is_event=False))

        await asyncio.sleep(3)
        s = get_settings(chat_id)
        if chat_id not in JUMBLE_FIGHT and s["is_active"]:
            asyncio.create_task(start_game(chat_id, s["default_diff"], chat_id))

# ============================================================
# CALLBACK QUERIES ROUTER
# ============================================================

@app.on_callback_query()
async def callback_router(_, query: CallbackQuery):
    data = query.data
    chat_id = query.message.chat.id
    user_id = query.from_user.id
    now = time.time()

    if data.startswith("ev_target_"):
        target_mode = data.split("_")[2]
        uid = user_id
        if uid not in EVENT_WIZARD:
            return await query.answer("Session expired. Kripya /setevent dubara likhein.", show_alert=True)

        EVENT_WIZARD[uid]["target"] = target_mode
        w = EVENT_WIZARD[uid]
        hint_str = w['hint'] if w['hint'] != "0" else "None"

        review_kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Confirm & Save Event", callback_data="ev_confirm_save"),
                InlineKeyboardButton("✏️ Edit / Restart", callback_data="ev_restart_wizard")
            ],
            [
                InlineKeyboardButton("❌ Cancel Event", callback_data="ev_cancel_wizard")
            ]
        ])

        review_text = (
            f"<blockquote>📋 <b>𝐄𝐕𝐄𝐍𝐓 𝐂𝐎𝐍𝐅𝐈𝐑𝐌𝐀𝐓𝐈𝐎𝐍 𝐑𝐄𝐕𝐈𝐄𝐖</b>\n\n"
            f"📌 <b>Title:</b> <code>{w['title']}</code>\n"
            f"🔑 <b>Mystery Word:</b> <code>{w['word'].upper()}</code>\n"
            f"💡 <b>Hint:</b> <code>{hint_str}</code>\n"
            f"⭐ <b>Reward Stars:</b> <code>{w['stars']} pts</code>\n"
            f"⚡ <b>Reward EXP:</b> <code>{w['exp']} EXP</code>\n"
            f"⏰ <b>Repeat Interval:</b> Every <code>{w['interval']} Hours</code>\n"
            f"🎯 <b>Target:</b> <code>{w['target'].upper()}</code>\n\n"
            f"👉 <i>Sabhi details check karke <b>Confirm</b> karein:</i></blockquote>"
        )
        await query.message.edit_text(review_text, reply_markup=review_kb, parse_mode=ParseMode.HTML)
        await query.answer()

    elif data == "ev_confirm_save":
        uid = user_id
        if uid not in EVENT_WIZARD:
            return await query.answer("Session expired.", show_alert=True)

        w = EVENT_WIZARD[uid]
        next_run = now + (w["interval"] * 3600)

        DB.execute("""
            INSERT INTO events_bank (title, word, hint, reward_stars, reward_exp, interval_hrs, target_type, next_run, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, (w["title"], w["word"], w["hint"], w["stars"], w["exp"], w["interval"], w["target"], next_run))
        DB.commit()

        del EVENT_WIZARD[uid]
        await query.answer("🎉 Event successfully saved!", show_alert=True)
        await query.message.edit_text(
            f"<blockquote>✅ <b>𝐄𝐕𝐄𝐍𝐓 𝐀𝐂𝐓𝐈𝐕𝐀𝐓𝐄𝐃 & 𝐒𝐂𝐇𝐄𝐃𝐔𝐋𝐄𝐃!</b>\n\n"
            f"Event database me add ho chuka hai aur <code>/eventlist</code> me check kiya ja sakta hai.</blockquote>",
            parse_mode=ParseMode.HTML
        )

    elif data == "ev_restart_wizard":
        uid = user_id
        EVENT_WIZARD[uid] = {"step": 1, "title": "", "word": "", "hint": "0", "stars": 0, "exp": 0, "interval": 4, "target": "group"}
        await query.message.edit_text(
            "<blockquote>🌟 <b>𝐄𝐕𝐄𝐍𝐓 𝐂𝐑𝐄𝐀𝐓𝐎𝐑 𝐖𝐈𝐙𝐀𝐑𝐃 (Step 1/7)</b>\n\n"
            "Is event ka title ya naam kya rakhna chahte hain? (Jaise: <i>Weekend Mystery Drop</i>)</blockquote>",
            parse_mode=ParseMode.HTML
        )
        await query.answer()

    elif data == "ev_cancel_wizard":
        uid = user_id
        if uid in EVENT_WIZARD:
            del EVENT_WIZARD[uid]
        await query.message.edit_text("<blockquote>❌ <b>Event Creation Cancelled.</b></blockquote>", parse_mode=ParseMode.HTML)
        await query.answer()

    elif data.startswith("ev_del_"):
        if not is_authed(user_id):
            return await query.answer("❌ Authorized users only.", show_alert=True)
        ev_id = int(data.split("_")[2])
        DB.execute("DELETE FROM events_bank WHERE id=?", (ev_id,))
        DB.commit()
        await query.answer(f"🗑️ Event #{ev_id} deleted!", show_alert=True)
        await query.message.delete()

    elif data.startswith("ev_toggle_"):
        if not is_authed(user_id):
            return await query.answer("❌ Authorized users only.", show_alert=True)
        ev_id = int(data.split("_")[2])
        ev = DB.execute("SELECT is_active FROM events_bank WHERE id=?", (ev_id,)) .fetchone()
        if ev:
            new_st = 0 if ev["is_active"] else 1
            DB.execute("UPDATE events_bank SET is_active=? WHERE id=?", (new_st, ev_id))
            DB.commit()
            st_text = "Activated" if new_st else "Paused"
            await query.answer(f"Event #{ev_id} {st_text}!")
            await query.message.delete()

    elif data == "buy_instant_exp":
        ensure_user(query.from_user)
        u = get_user(user_id)
        cost = get_global_config("shop_exp_cost", 1000)
        exp_rew = get_global_config("shop_exp_reward", 500)

        user_pts = u["points"] or 0
        if user_pts < cost:
            return await query.answer(f"❌ Poore points nahi hain! Pack price: {cost} pts | Your Balance: {user_pts} pts", show_alert=True)

        new_exp = (u["exp"] or 0) + exp_rew
        new_lvl = calculate_level(new_exp)

        DB.execute("UPDATE users SET points = points - ?, exp = ?, level = ? WHERE user_id = ?", (cost, new_exp, new_lvl, user_id))
        DB.execute("INSERT INTO score_history (user_id, chat_id, points, tag, timestamp) VALUES (?, 0, ?, 'shop_exp', ?)", (user_id, -cost, now))
        DB.commit()

        await query.answer(f"🎉 +{exp_rew} EXP Added! (Your Level: {new_lvl})", show_alert=True)
        text, kb = build_shop_text_and_kb(user_id)
        try:
            await query.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
        except Exception:
            pass

    elif data == "open_eventlist_btn":
        events = DB.execute("SELECT * FROM events_bank WHERE is_active=1").fetchall()
        if not events:
            return await query.answer("Filhaal koi active events nahi hain.", show_alert=True)

        text = "<blockquote>📅 <b>ACTIVE MYSTERY EVENTS LIST</b>\n\n"
        for ev in events:
            rem_time = max(0, ev["next_run"] - time.time())
            text += (
                f"🔹 <b>{ev['title']}</b> (#ID: {ev['id']})\n"
                f"• Word: <code>{ev['word'].upper()}</code> | Target: <code>{ev['target_type'].upper()}</code>\n"
                f"• Reward: ⭐ <code>{ev['reward_stars']} pts</code> | ⚡ <code>{ev['reward_exp']} EXP</code>\n"
                f"• Next Run In: <code>{format_duration(rem_time)}</code>\n\n"
            )
        text += "</blockquote>"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Close", callback_data="close_panel")]])
        try:
            await query.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
        except Exception:
            await app.send_message(chat_id, text, reply_markup=kb, parse_mode=ParseMode.HTML)
        await query.answer()

    elif data == "open_shop_btn" or data == "refresh_shop":
        ensure_user(query.from_user)
        text, kb = build_shop_text_and_kb(user_id)
        try:
            await query.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
        except Exception:
            await app.send_message(chat_id, text, reply_markup=kb, parse_mode=ParseMode.HTML)
        await query.answer()

    elif data.startswith("buy_card_"):
        ensure_user(query.from_user)
        u = get_user(user_id)
        card_type = data.split("_")[2]

        prefix = "card_point" if card_type == "point" else "card_level"
        price = get_global_config(f"{prefix}_price", 500)
        hrs = get_global_config(f"{prefix}_hrs", 3)
        min_lvl = get_global_config(f"{prefix}_req_lvl", 1)

        user_pts = u["points"] or 0
        user_lvl = u["level"] or 1

        if user_lvl < min_lvl:
            return await query.answer(f"❌ Is card ke liye Level {min_lvl}+ hona zaroori hai! (Your Level: {user_lvl})", show_alert=True)

        if user_pts < price:
            return await query.answer(f"❌ Poore points nahi hain! Card price: {price} pts | Your Balance: {user_pts} pts", show_alert=True)

        field = "point_card_exp" if card_type == "point" else "level_card_exp"
        cur_exp = u[field] if u[field] and u[field] > now else now
        new_exp = cur_exp + (hrs * 3600)

        DB.execute(f"UPDATE users SET points = points - ?, {field} = ? WHERE user_id = ?", (price, new_exp, user_id))
        DB.execute("INSERT INTO score_history (user_id, chat_id, points, tag, timestamp) VALUES (?, 0, ?, 'shop_card', ?)", (user_id, -price, now))
        DB.commit()

        await query.answer(f"🎉 Success! Card activated for {hrs} hours!", show_alert=True)
        text, kb = build_shop_text_and_kb(user_id)
        try:
            await query.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
        except Exception:
            pass

    elif data == "hint":
        game = DB.execute("SELECT * FROM games WHERE chat_id=? AND solved=0", (chat_id,)).fetchone()
        if not game:
            return await query.answer("Koi active puzzle nahi hai.", show_alert=True)

        ensure_user(query.from_user)
        puzzle_id = game["puzzle_id"]
        word = game["word"]
        difficulty = game["difficulty"]

        hint_limit = get_global_config(f"hints_{difficulty}", 3)

        hint_row = DB.execute("SELECT * FROM puzzle_hints WHERE chat_id=? AND puzzle_id=? AND user_id=?", (chat_id, puzzle_id, user_id)).fetchone()
        hints_used = hint_row["hints_used"] if hint_row else 0
        revealed_indices = [int(i) for i in hint_row["revealed_indices"].split(",") if i] if hint_row else []

        if hints_used >= hint_limit:
            return await query.answer(f"❌ Is word ke liye aapki {hint_limit} hints complete ho chuki hain!", show_alert=True)

        available_indices = [i for i in range(len(word)) if i not in revealed_indices]
        if not available_indices:
            return await query.answer("❌ Aur hints available nahi hain.", show_alert=True)

        chosen_index = random.choice(available_indices)
        revealed_indices.append(chosen_index)
        hints_used += 1

        DB.execute("""
            INSERT INTO puzzle_hints(chat_id, puzzle_id, user_id, hints_used, revealed_indices)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(chat_id, puzzle_id, user_id) DO UPDATE SET
                hints_used=excluded.hints_used,
                revealed_indices=excluded.revealed_indices
        """, (chat_id, puzzle_id, user_id, hints_used, ",".join(map(str, revealed_indices))))
        DB.commit()

        letter = word[chosen_index].upper()
        return await query.answer(f"💡 Hint: Letter #{chosen_index + 1} is '{letter}'\nRemaining: {hint_limit - hints_used}/{hint_limit}", show_alert=True)

    elif data == "fight_hint":
        game = JUMBLE_FIGHT.get(chat_id)
        if not game or user_id not in game["players"]:
            return await query.answer("❌ Sirf match players hints le sakte hain.", show_alert=True)

        difficulty = game["difficulty"]
        hint_limit = get_global_config(f"hints_{difficulty}", 3)

        p_hint = game["round_hints"][user_id]
        if p_hint["count"] >= hint_limit:
            return await query.answer(f"❌ Is round ke {hint_limit} hints use ho chuke hain!", show_alert=True)

        word = game["word"]
        avail = [i for i in range(len(word)) if i not in p_hint["indices"]]
        if not avail:
            return await query.answer("❌ Aur letters reveal nahi ho sakte.", show_alert=True)

        idx = random.choice(avail)
        p_hint["indices"].append(idx)
        p_hint["count"] += 1

        return await query.answer(f"💡 Hint: Letter #{idx + 1} is '{word[idx].upper()}'\nRemaining: {hint_limit - p_hint['count']}/{hint_limit}", show_alert=True)

    elif data.startswith("lb_"):
        await query.answer()
        parts = data.split("_")
        scope = parts[1]
        target_chat = int(parts[2])

        text, kb = build_leaderboard_text_and_kb(scope, target_chat)
        try:
            await query.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
        except MessageNotModified:
            pass

    elif data.startswith("wb_"):
        await query.answer()
        if not is_authed(user_id):
            return await query.answer("❌ Sirf Auth Users word bank dekh sakte hain.", show_alert=True)

        _, diff, page_str = data.split("_")
        page = int(page_str)
        word_list = sorted(WORDS.get(diff, []))
        total_words = len(word_list)
        per_page = 20
        total_pages = max(1, (total_words + per_page - 1) // per_page)
        page = max(1, min(page, total_pages))

        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        page_words = word_list[start_idx:end_idx]

        formatted_list = "  •  ".join(f"<code>{w.upper()}</code>" for w in page_words) if page_words else "<i>Koi words available nahi hain.</i>"

        nav_row = []
        if page > 1:
            nav_row.append(InlineKeyboardButton("⬅️ 𝐏ʀᴇᴠ", callback_data=f"wb_{diff}_{page - 1}"))
        nav_row.append(InlineKeyboardButton(f"📄 {page}/{total_pages}", callback_data="noop_page"))
        if page < total_pages:
            nav_row.append(InlineKeyboardButton("𝐍ᴇxᴛ ➡️", callback_data=f"wb_{diff}_{page + 1}"))

        kb = InlineKeyboardMarkup([
            nav_row,
            [
                InlineKeyboardButton("🟢 𝐄ᴀsʏ", callback_data="wb_easy_1"),
                InlineKeyboardButton("🟡 𝐌ᴇᴅɪᴜᴍ", callback_data="wb_medium_1"),
                InlineKeyboardButton("🔴 𝐇ᴀʀᴅ", callback_data="wb_hard_1")
            ],
            [
                InlineKeyboardButton("🔙 𝐁ᴀᴄᴋ ᴛᴏ 𝐌ᴇɴᴜ", callback_data="back_to_words_menu"),
                InlineKeyboardButton("❌ 𝐂ʟᴏsᴇ", callback_data="close_panel")
            ]
        ])

        msg = (
            f"<blockquote>📚 <b>{diff.upper()} 𝐖𝐎𝐑𝐃𝐒 𝐁𝐀𝐍𝐊</b> (Total: <code>{total_words}</code>)\n"
            f"📌 <i>Tip: Tap on any word below to copy it!</i>\n\n"
            f"{formatted_list}\n\n"
            f"➕ <b>Add:</b> <code>/addword {diff} word</code>\n"
            f"➖ <b>Del:</b> <code>/delword {diff} word</code>\n"
            f"🗑️ <b>Clear All:</b> <code>/delallword {diff}</code></blockquote>"
        )

        try:
            await query.message.edit_text(msg, reply_markup=kb, parse_mode=ParseMode.HTML)
        except MessageNotModified:
            pass
        except Exception:
            try:
                await app.send_message(chat_id, msg, reply_markup=kb, parse_mode=ParseMode.HTML)
            except Exception:
                pass

    elif data == "noop_page":
        await query.answer("Current Page Number", show_alert=False)

    elif data == "back_to_words_menu":
        await query.answer()
        if not is_authed(user_id):
            return await query.answer("❌ Authorized users only.", show_alert=True)

        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(f"🟢 𝐄ᴀsʏ ({len(WORDS['easy'])})", callback_data="wb_easy_1"),
                InlineKeyboardButton(f"🟡 𝐌ᴇᴅɪᴜᴍ ({len(WORDS['medium'])})", callback_data="wb_medium_1"),
                InlineKeyboardButton(f"🔴 𝐇ᴀʀᴅ ({len(WORDS['hard'])})", callback_data="wb_hard_1")
            ],
            [
                InlineKeyboardButton("❌ 𝐂ʟᴏsᴇ", callback_data="close_panel")
            ]
        ])
        try:
            await query.message.edit_text(
                "<blockquote>📚 <b>𝐉𝐔𝐌𝐁𝐋𝐄 𝐖𝐎𝐑𝐃 𝐁𝐀𝐍𝐊</b>\n\n"
                f"🟢 <b>𝐄ᴀsʏ 𝐖ᴏʀᴅs:</b> <code>{len(WORDS['easy'])}</code>\n"
                f"🟡 <b>𝐌ᴇᴅɪᴜᴍ 𝐖ᴏʀᴅs:</b> <code>{len(WORDS['medium'])}</code>\n"
                f"🔴 <b>𝐇ᴀʀᴅ 𝐖ᴏʀᴅs:</b> <code>{len(WORDS['hard'])}</code>\n\n"
                "📌 <b>𝐁ᴜʟᴋ 𝐖ᴏʀᴅs 𝐀ᴅᴅ:</b>\n"
                "<code>/addword easy cat dog bird tree lion</code>\n\n"
                "Neeche buttons par click karke category ke words check karein:</blockquote>",
                reply_markup=kb,
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass

    elif data.startswith("f_"):
        lobby = FIGHT_LOBBY.get(chat_id)
        if not lobby:
            return await query.answer("Match lobby expire ho chuki hai.", show_alert=True)

        if data == "f_decline":
            if user_id != lobby["p2"] and user_id != lobby["p1"] and not await is_admin_or_owner(query.message.chat, user_id):
                return await query.answer("❌ Sirf match players hi decline kar sakte hain.", show_alert=True)
            
            del FIGHT_LOBBY[chat_id]
            await query.message.delete()
            return await query.answer("Challenge declined.")

        if data == "f_accept":
            if user_id != lobby["p2"]:
                return await query.answer("❌ Yeh challenge aapke liye nahi hai! Sirf opponent accept kar sakta hai.", show_alert=True)

            if lobby.get("is_bet"):
                b_amt = lobby["bet_amount"]
                u1 = get_user(lobby["p1"])
                u2 = get_user(lobby["p2"])

                if u1["points"] < b_amt:
                    del FIGHT_LOBBY[chat_id]
                    return await query.message.edit_text(f"<blockquote>❌ Challenger ke paas <code>{b_amt} points</code> nahi hain. Bet cancel ho gayi.</blockquote>", parse_mode=ParseMode.HTML)

                if u2["points"] < b_amt:
                    del FIGHT_LOBBY[chat_id]
                    return await query.message.edit_text(f"<blockquote>❌ Aapke paas <code>{b_amt} points</code> nahi hain. Bet cancel ho gayi.</blockquote>", parse_mode=ParseMode.HTML)

                DB.execute("UPDATE users SET points = points - ? WHERE user_id = ?", (b_amt, lobby["p1"]))
                DB.execute("UPDATE users SET points = points - ? WHERE user_id = ?", (b_amt, lobby["p2"]))
                
                now = time.time()
                DB.execute("INSERT INTO score_history (user_id, chat_id, points, tag, timestamp) VALUES (?, ?, ?, 'bet_fight', ?)", (lobby["p1"], chat_id, -b_amt, now))
                DB.execute("INSERT INTO score_history (user_id, chat_id, points, tag, timestamp) VALUES (?, ?, ?, 'bet_fight', ?)", (lobby["p2"], chat_id, -b_amt, now))
                DB.commit()

            JUMBLE_FIGHT[chat_id] = {
                "players": [lobby["p1"], lobby["p2"]],
                "names": {lobby["p1"]: lobby["p1_name"], lobby["p2"]: lobby["p2_name"]},
                "mentions": {lobby["p1"]: lobby["m1"], lobby["p2"]: lobby["m2"]},
                "round": 0,
                "scores": defaultdict(int),
                "word": None,
                "expires": None,
                "task": None,
                "difficulty": lobby["difficulty"],
                "timer": lobby["timer"],
                "msg_id": None,
                "is_bet": lobby.get("is_bet", False),
                "bet_amount": lobby.get("bet_amount", 0),
                "is_rebet": lobby.get("is_rebet", False),
                "orig_stake": lobby.get("orig_stake", lobby.get("bet_amount", 0))
            }
            del FIGHT_LOBBY[chat_id]
            
            await query.message.delete()
            await query.answer("🚀 Challenge Accepted!")

            bet_text = f" (Bet: <b>{JUMBLE_FIGHT[chat_id]['bet_amount']} pts</b> each)" if JUMBLE_FIGHT[chat_id]["is_bet"] else ""
            announcement = await app.send_message(
                chat_id,
                f"<blockquote>🔥 <b>𝐂ʜᴀʟʟᴇɴɢᴇ 𝐀ᴄᴄᴇᴘᴛᴇᴅ ʙʏ {lobby['m2']}!</b>\n\n"
                f"⚔️ <b>{lobby['m1']}</b> 🆚 <b>{lobby['m2']}</b>{bet_text}\n"
                f"🚀 <i>𝐌ᴀᴛᴄʜ sᴛᴀʀᴛɪɴɢ ɪɴ 3 sᴇᴄᴏɴᴅs...</i></blockquote>",
                parse_mode=ParseMode.HTML
            )
            asyncio.create_task(delete_after(announcement, 4))
            
            await asyncio.sleep(3)
            asyncio.create_task(fight_next(chat_id))
            return

        if user_id not in (lobby["p1"], lobby["p2"]) and not await is_admin_or_owner(query.message.chat, user_id):
            return await query.answer("❌ Match players hi settings change kar sakte hain.", show_alert=True)

        if data.startswith("f_diff_"):
            lobby["difficulty"] = data.split("_")[2]
            await query.answer(f"Difficulty set to {lobby['difficulty'].upper()}")
        elif data.startswith("f_time_"):
            lobby["timer"] = int(data.split("_")[2])
            await query.answer(f"Timer set to {lobby['timer']}s")

        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(f"{'✅ ' if lobby['difficulty']=='easy' else ''}🟢 𝐄ᴀsʏ", callback_data="f_diff_easy"),
                InlineKeyboardButton(f"{'✅ ' if lobby['difficulty']=='medium' else ''}🟡 𝐌ᴇᴅɪᴜᴍ", callback_data="f_diff_medium"),
                InlineKeyboardButton(f"{'✅ ' if lobby['difficulty']=='hard' else ''}🔴 𝐇ᴀʀᴅ", callback_data="f_diff_hard")
            ],
            [
                InlineKeyboardButton(f"{'✅ ' if lobby['timer']==30 else ''}⏱️ 30s", callback_data="f_time_30"),
                InlineKeyboardButton(f"{'✅ ' if lobby['timer']==45 else ''}⏱️ 45s", callback_data="f_time_45"),
                InlineKeyboardButton(f"{'✅ ' if lobby['timer']==60 else ''}⏱️ 60s", callback_data="f_time_60")
            ],
            [
                InlineKeyboardButton("✅ 𝐀ᴄᴄᴇᴘᴛ 𝐂ʜᴀʟʟᴇɴɢᴇ", callback_data="f_accept"),
                InlineKeyboardButton("❌ 𝐃ᴇᴄʟɪɴᴇ", callback_data="f_decline")
            ]
        ])

        header_str = "💰 <b>𝐉𝐔𝐌𝐁𝐋𝐄 𝐁𝐄𝐓 𝐅𝐈𝐆𝐇𝐓 1v1 𝐂𝐇𝐀ʟʟᴇɴɢᴇ!</b>" if lobby.get("is_bet") else "⚔️ <b>𝐉𝐔𝐌𝐁𝐋𝐄 𝐅𝐈𝐆𝐇𝐓 1v1 𝐂𝐇𝐀𝐋ʟᴇɴɢᴇ!</b>"
        bet_info = f"\n💵 <b>𝐁ᴇᴛ:</b> <code>{lobby['bet_amount']} pts each</code>" if lobby.get("is_bet") else ""

        try:
            await query.message.edit_text(
                f"<blockquote>{header_str}\n\n"
                f"👤 <b>𝐂ʜᴀʟʟᴇɴɢᴇʀ:</b> {lobby['m1']} (<code>{lobby['p1']}</code>)\n"
                f"🎯 <b>𝐓ᴀʀɢᴇᴛ:</b> {lobby['m2']} (<code>{lobby['p2']}</code>)\n\n"
                f"⚙️ <b>𝐒ᴇᴛᴛɪɴɢs:</b> Mode: <code>{lobby['difficulty'].title()}</code> | Timer: <code>{lobby['timer']}s</code>{bet_info}\n\n"
                f"👉 {lobby['m2']}, match shuru karne ke liye <b>Accept Challenge</b> par click karo!</blockquote>",
                reply_markup=kb,
                parse_mode=ParseMode.HTML
            )
        except MessageNotModified:
            pass

    elif data.startswith("set_"):
        if not query.from_user or not await is_admin_or_owner(query.message.chat, user_id):
            return await query.answer("❌ Only admins can change settings.", show_alert=True)

        if data == "set_start_game":
            DB.execute("UPDATE settings SET is_active=1 WHERE chat_id=?", (chat_id,))
            DB.commit()
            await query.answer("▶️ Game started!")
            await show_settings_panel(query.message, chat_id)
            s = get_settings(chat_id)
            asyncio.create_task(start_game(chat_id, s["default_diff"], query.message))

        elif data == "set_stop_game":
            DB.execute("UPDATE settings SET is_active=0 WHERE chat_id=?", (chat_id,))
            old_g = DB.execute("SELECT message_id FROM games WHERE chat_id=?", (chat_id,)).fetchone()
            s = get_settings(chat_id)
            if old_g and s["auto_delete"] and old_g["message_id"]:
                await safe_delete_and_unpin(chat_id, old_g["message_id"])
            DB.execute("DELETE FROM games WHERE chat_id=?", (chat_id,))
            DB.commit()
            await query.answer("⏹️ Game stopped!")
            await show_settings_panel(query.message, chat_id)

        elif data == "set_toggle_autodel":
            s = get_settings(chat_id)
            new_val = 0 if s["auto_delete"] else 1
            DB.execute("UPDATE settings SET auto_delete=? WHERE chat_id=?", (new_val, chat_id))
            DB.commit()
            await query.answer(f"Auto Delete {'Enabled' if new_val else 'Disabled'}")
            await show_settings_panel(query.message, chat_id)

        elif data == "set_menu_mode":
            kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🟢 𝐄ᴀsʏ", callback_data="set_def_easy"),
                    InlineKeyboardButton("🟡 𝐌ᴇᴅɪᴜᴍ", callback_data="set_def_medium"),
                    InlineKeyboardButton("🔴 𝐇ᴀʀᴅ", callback_data="set_def_hard")
                ],
                [InlineKeyboardButton("🔙 𝐁ᴀᴄᴋ", callback_data="set_back")]
            ])
            try:
                await query.message.edit_text("<blockquote>🎯 <b>Default Jumble Difficulty Chuno:</b></blockquote>", reply_markup=kb, parse_mode=ParseMode.HTML)
            except MessageNotModified:
                pass

        elif data == "set_menu_timers":
            kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("Easy: 60s", callback_data="set_t_easy_60"),
                    InlineKeyboardButton("Easy: 120s", callback_data="set_t_easy_120")
                ],
                [
                    InlineKeyboardButton("Med: 180s", callback_data="set_t_medium_180"),
                    InlineKeyboardButton("Med: 300s", callback_data="set_t_medium_300")
                ],
                [
                    InlineKeyboardButton("Hard: 300s", callback_data="set_t_hard_300"),
                    InlineKeyboardButton("Hard: 600s", callback_data="set_t_hard_600")
                ],
                [InlineKeyboardButton("🔙 𝐁ᴀᴄᴋ", callback_data="set_back")]
            ])
            try:
                await query.message.edit_text("<blockquote>⏱️ <b>Select Timer Duration:</b></blockquote>", reply_markup=kb, parse_mode=ParseMode.HTML)
            except MessageNotModified:
                pass

        elif data.startswith("set_def_"):
            d = data.split("_")[2]
            DB.execute("UPDATE settings SET default_diff=? WHERE chat_id=?", (d, chat_id))
            DB.commit()
            await query.answer(f"Default mode set to {d.upper()}")
            await show_settings_panel(query.message, chat_id)

        elif data.startswith("set_t_"):
            _, _, diff, secs = data.split("_")
            DB.execute(f"UPDATE settings SET {diff}=? WHERE chat_id=?", (int(secs), chat_id))
            DB.commit()
            await query.answer(f"{diff.title()} timer updated to {secs}s")
            await show_settings_panel(query.message, chat_id)

        elif data == "set_back":
            await show_settings_panel(query.message, chat_id)

    elif data == "skip":
        if not query.from_user or not await is_admin_or_owner(query.message.chat, user_id):
            return await query.answer("❌ Only admins/owner can skip.", show_alert=True)

        game = DB.execute("SELECT * FROM games WHERE chat_id=? AND solved=0", (chat_id,)).fetchone()
        if not game:
            return await query.answer("Active game nahi mila.", show_alert=True)

        DB.execute("UPDATE games SET solved=1 WHERE chat_id=?", (chat_id,))
        DB.commit()
        
        s = get_settings(chat_id)
        if s["auto_delete"] and game["message_id"]:
            await safe_delete_and_unpin(chat_id, game["message_id"])

        sk_msg = await query.message.reply_text(f"<blockquote>⏭️ <b>𝐒ᴋɪᴘᴘᴇᴅ!</b>\n<b>Answer:</b> <code>{game['word'].upper()}</code>\n\n🔄 <i>Next puzzle starting in 3 seconds...</i></blockquote>", parse_mode=ParseMode.HTML)
        if s["auto_delete"]:
            asyncio.create_task(delete_after(sk_msg, 4))
            
        await query.answer("Skipped.")
        await asyncio.sleep(3)
        s = get_settings(chat_id)
        if s["is_active"]:
            asyncio.create_task(start_game(chat_id, s["default_diff"], chat_id))

    elif data == "newword":
        old = DB.execute("SELECT * FROM games WHERE chat_id=?", (chat_id,)).fetchone()
        if old and not old["solved"] and time.time() <= old["expires"]:
            return await query.answer("❌ Current puzzle abhi active hai.", show_alert=True)

        s = get_settings(chat_id)
        difficulty = old["difficulty"] if old else s["default_diff"]
        await query.answer("🧩 Starting new puzzle...")
        asyncio.create_task(start_game(chat_id, difficulty, query.message))

    elif data == "close_panel":
        await query.message.delete()

async def show_settings_panel(message_obj, chat_id):
    s = get_settings(chat_id)
    cur_diff = s["default_diff"] if "default_diff" in s.keys() else "medium"
    status_btn = InlineKeyboardButton("⏹️ 𝐒ᴛᴏᴘ 𝐆ᴀᴍᴇ", callback_data="set_stop_game") if s["is_active"] else InlineKeyboardButton("▶️ 𝐒ᴛᴀʀᴛ 𝐆ᴀᴍᴇ", callback_data="set_start_game")
    del_btn = InlineKeyboardButton("🗑️ 𝐀ᴜᴛᴏ-𝐃ᴇʟ: 𝐎𝐍", callback_data="set_toggle_autodel") if s["auto_delete"] else InlineKeyboardButton("🗑️ 𝐀ᴜᴛᴏ-𝐃ᴇʟ: 𝐎𝐅𝐅", callback_data="set_toggle_autodel")

    p_easy = get_global_config("points_easy", 10)
    p_med = get_global_config("points_medium", 20)
    p_hard = get_global_config("points_hard", 30)

    h_easy = get_global_config("hints_easy", 3)
    h_med = get_global_config("hints_medium", 3)
    h_hard = get_global_config("hints_hard", 3)

    kb = InlineKeyboardMarkup([
        [
            status_btn,
            InlineKeyboardButton(f"🎯 𝐌ᴏᴅᴇ: {str(cur_diff).upper()}", callback_data="set_menu_mode")
        ],
        [
            InlineKeyboardButton("⏱️ 𝐓ɪᴍᴇʀs", callback_data="set_menu_timers"),
            del_btn
        ],
        [
            InlineKeyboardButton("❌ 𝐂ʟᴏsᴇ", callback_data="close_panel")
        ]
    ])
    text = (
        f"<blockquote>⚙️ <b>𝐉ᴜᴍʙʟᴇ 𝐆ʀᴏᴜᴘ 𝐒ᴇᴛᴛɪɴɢs</b>\n\n"
        f"🟢 <b>𝐆ᴀᴍᴇ 𝐒ᴛᴀᴛᴜs:</b> <code>{'Running' if s['is_active'] else 'Stopped'}</code>\n"
        f"🗑️ <b>𝐀ᴜᴛᴏ 𝐃ᴇʟᴇᴛᴇ 𝐎ʟᴅ:</b> <code>{'Enabled' if s['auto_delete'] else 'Disabled'}</code>\n"
        f"🎯 <b>𝐃ᴇғᴀᴜʟᴛ 𝐌ᴏᴅᴇ:</b> <code>{str(cur_diff).title()}</code>\n"
        f"⏱️ <b>𝐓ɪᴍᴇʀs:</b> Easy: <code>{s['easy']}s</code> | Med: <code>{s['medium']}s</code> | Hard: <code>{s['hard']}s</code>\n\n"
        f"🌍 <b>𝐆ʟᴏʙᴀʟ 𝐑ᴇᴡᴀʀᴅs:</b> Easy: <code>{p_easy}pts</code> | Med: <code>{p_med}pts</code> | Hard: <code>{p_hard}pts</code>\n"
        f"💡 <b>𝐆ʟᴏʙᴀʟ 𝐇ɪɴᴛs:</b> Easy: <code>{h_easy}</code> | Med: <code>{h_med}</code> | Hard: <code>{h_hard}</code></blockquote>"
    )
    try:
        await message_obj.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    except MessageNotModified:
        pass

# ============================================================
# MAIN ENTRYPOINT
# ============================================================

if __name__ == "__main__":
    print("🚀 Advanced Jumble, Bet Fight, Level, Shop & Event Bot Started Successfully!")
    asyncio.get_event_loop().create_task(resume_all_active_games())
    asyncio.get_event_loop().create_task(auto_backup_task())
    asyncio.get_event_loop().create_task(event_scheduler_loop())
    app.run()

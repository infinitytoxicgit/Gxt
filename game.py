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
# HELPERS & UTILITIES
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
        # Choose word: if "random", pick from event bank per chat
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
# SHOP SYSTEM & POWER CARDS
# ============================================================

def build_shop_text_and_kb(user_id):
    u = get_user(user_id)
    now = time.time()

    pt_price = get_global_config("card_point_price", 500)
    pt_hrs = get_global_config("card_point_hrs", 3)
    pt_req = get_global_config("card_point_req_lvl", 1)

    lvl_price = get_global_config("card_level_price", 600)
    lvl_hrs = get_global_config("card_level_hrs", 3)
    lvl_req = get_global_config("card_level_req_lvl", 2)

    exp_cost = get_global_config("shop_exp_cost", 1000)
    exp_rew = get_global_config("shop_exp_reward", 500)
    step = get_global_config("global_exp_per_lvl", 500)

    pt_card_status = format_duration(u["point_card_exp"] - now) if u and u["point_card_exp"] > now else "Inactive"
    lvl_card_status = format_duration(u["level_card_exp"] - now) if u and u["level_card_exp"] > now else "Inactive"

    user_pts = u["points"] if u else 0
    user_lvl = u["level"] if u else 1
    user_exp = u["exp"] if u else 0

    text = (
        f"<blockquote>🛍️ <b>𝐉𝐔𝐌𝐁𝐋𝐄 𝐏𝐎𝐖𝐄𝐑 & 𝐄𝐗𝐏 𝐒𝐇𝐎𝐏</b>\n\n"
        f"👤 <b>Your Balance:</b> ⭐ <code>{user_pts} pts/stars</code>\n"
        f"🎖️ <b>Your Rank:</b> Level <code>{user_lvl}</code> (<code>{user_exp % step}/{step} EXP</code>)\n\n"
        f"⚡ <b>Active Powers:</b>\n"
        f"• <b>Point Multiplication Card:</b> <code>{pt_card_status}</code>\n"
        f"• <b>Level Multiplication Card:</b> <code>{lvl_card_status}</code></blockquote>\n\n"
        f"<blockquote>🃏 <b>Available Store Items:</b>\n\n"
        f"1️⃣ <b>Point Multiplication Card (2x Points)</b>\n"
        f"• Duration: <code>{pt_hrs} Hours</code> | Price: ⭐ <code>{pt_price} stars</code>\n"
        f"• Required: <code>Level {pt_req}+</code>\n\n"
        f"2️⃣ <b>Level Multiplication Card (2x EXP)</b>\n"
        f"• Duration: <code>{lvl_hrs} Hours</code> | Price: ⭐ <code>{lvl_price} stars</code>\n"
        f"• Required: <code>Level {lvl_req}+</code>\n\n"
        f"3️⃣ <b>Instant EXP Pack (+{exp_rew} EXP)</b>\n"
        f"• Price: ⭐ <code>{exp_cost} stars</code>\n"
        f"• Benefit: <i>Instant Level Up Booster!</i></blockquote>"
    )

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"⚡ Buy Point Card ({pt_price} ⭐)", callback_data="buy_card_point"),
            InlineKeyboardButton(f"🎖️ Buy Level Card ({lvl_price} ⭐)", callback_data="buy_card_level")
        ],
        [
            InlineKeyboardButton(f"✨ Instant +{exp_rew} EXP ({exp_cost} ⭐)", callback_data="buy_instant_exp")
        ],
        [
            InlineKeyboardButton("🔄 Refresh", callback_data="refresh_shop"),
            InlineKeyboardButton("❌ Close", callback_data="close_panel")
        ]
    ])
    return text, kb

@app.on_message(filters.command(["shop", "store"]))
async def shop_cmd(_, message: Message):
    ensure_user(message.from_user)
    text, kb = build_shop_text_and_kb(message.from_user.id)
    await message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)

# ============================================================
# STARS MANAGEMENT: ADD & DEDUCT STARS
# ============================================================

@app.on_message(filters.command(["addstar", "addstars", "addpoint", "addpoints"]))
async def add_star_cmd(_, message: Message):
    if not message.from_user or not is_authed(message.from_user.id):
        return await message.reply_text("<blockquote>❌ <b>Sirf Owner aur Auth users stars add kar sakte hain.</b></blockquote>", parse_mode=ParseMode.HTML)

    target_user = None
    amount = 0

    if message.reply_to_message and message.reply_to_message.from_user:
        target_user = message.reply_to_message.from_user
        for arg in message.command[1:]:
            if arg.isdigit():
                amount = int(arg)
                break
    else:
        for arg in message.command[1:]:
            if arg.isdigit() and amount == 0:
                amount = int(arg)
            else:
                try:
                    if arg.startswith("@"):
                        target_user = await app.get_users(arg)
                    elif arg.isdigit() and len(arg) >= 7:
                        target_user = await app.get_users(int(arg))
                except Exception:
                    pass

    if not target_user or amount <= 0:
        return await message.reply_text(
            "<blockquote><b>Usage:</b>\n"
            "• Reply karke: <code>/addstar 500</code>\n"
            "• Mention karke: <code>/addstar 500 @username</code>\n"
            "• ID se: <code>/addstar 500 UserID</code></blockquote>",
            parse_mode=ParseMode.HTML
        )

    ensure_user(target_user)
    now = time.time()
    DB.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (amount, target_user.id))
    DB.execute("INSERT INTO score_history (user_id, chat_id, points, tag, timestamp) VALUES (?, ?, ?, 'manual_add', ?)", (target_user.id, message.chat.id, amount, now))
    DB.commit()

    u = get_user(target_user.id)
    m = get_mention(target_user)
    await message.reply_text(
        f"<blockquote>⭐ <b>STARS ADDED SUCCESSFULLY!</b>\n\n"
        f"👤 <b>User:</b> {m} (<code>{target_user.id}</code>)\n"
        f"➕ <b>Added:</b> <code>+{amount} Stars</code>\n"
        f"💰 <b>New Total:</b> <code>{u['points']} Stars</code></blockquote>",
        parse_mode=ParseMode.HTML
    )

@app.on_message(filters.command(["deductstar", "deductstars", "removestar", "minusstar"]))
async def deduct_star_cmd(_, message: Message):
    if not message.from_user or not is_authed(message.from_user.id):
        return await message.reply_text("<blockquote>❌ <b>Sirf Owner aur Auth users stars minus kar sakte hain.</b></blockquote>", parse_mode=ParseMode.HTML)

    target_user = None
    amount = 0

    if message.reply_to_message and message.reply_to_message.from_user:
        target_user = message.reply_to_message.from_user
        for arg in message.command[1:]:
            if arg.isdigit():
                amount = int(arg)
                break
    else:
        for arg in message.command[1:]:
            if arg.isdigit() and amount == 0:
                amount = int(arg)
            else:
                try:
                    if arg.startswith("@"):
                        target_user = await app.get_users(arg)
                    elif arg.isdigit() and len(arg) >= 7:
                        target_user = await app.get_users(int(arg))
                except Exception:
                    pass

    if not target_user or amount <= 0:
        return await message.reply_text(
            "<blockquote><b>Usage:</b>\n"
            "• Reply karke: <code>/deductstar 500</code>\n"
            "• Mention karke: <code>/deductstar 500 @username</code>\n"
            "• ID se: <code>/deductstar 500 UserID</code></blockquote>",
            parse_mode=ParseMode.HTML
        )

    ensure_user(target_user)
    now = time.time()
    DB.execute("UPDATE users SET points = MAX(0, points - ?) WHERE user_id = ?", (amount, target_user.id))
    DB.execute("INSERT INTO score_history (user_id, chat_id, points, tag, timestamp) VALUES (?, ?, ?, 'manual_deduct', ?)", (target_user.id, message.chat.id, -amount, now))
    DB.commit()

    u = get_user(target_user.id)
    m = get_mention(target_user)
    await message.reply_text(
        f"<blockquote>🔻 <b>STARS DEDUCTED SUCCESSFULLY!</b>\n\n"
        f"👤 <b>User:</b> {m} (<code>{target_user.id}</code>)\n"
        f"➖ <b>Deducted:</b> <code>-{amount} Stars</code>\n"
        f"💰 <b>Current Balance:</b> <code>{u['points']} Stars</code></blockquote>",
        parse_mode=ParseMode.HTML
    )

# ============================================================
# DETAILED PLAYER CALCULATOR AUDIT (/calculate)
# ============================================================

@app.on_message(filters.command(["calculate", "calc", "audit"]))
async def calculate_player_cmd(_, message: Message):
    if not message.from_user or not is_authed(message.from_user.id):
        return await message.reply_text("<blockquote>❌ <b>Sirf Owner aur Auth users audit calculate kar sakte hain.</b></blockquote>", parse_mode=ParseMode.HTML)

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
    uid = target_user.id
    u = get_user(uid)

    easy_pts = DB.execute("SELECT SUM(points) as s, COUNT(*) as c FROM score_history WHERE user_id=? AND tag='easy'", (uid,)).fetchone()
    med_pts = DB.execute("SELECT SUM(points) as s, COUNT(*) as c FROM score_history WHERE user_id=? AND tag='medium'", (uid,)).fetchone()
    hard_pts = DB.execute("SELECT SUM(points) as s, COUNT(*) as c FROM score_history WHERE user_id=? AND tag='hard'", (uid,)).fetchone()
    fight_pts = DB.execute("SELECT SUM(points) as s FROM score_history WHERE user_id=? AND tag='bet_fight'", (uid,)).fetchone()
    event_pts = DB.execute("SELECT SUM(points) as s FROM score_history WHERE user_id=? AND tag='event'", (uid,)).fetchone()

    e_total = easy_pts["s"] or 0
    e_cnt = easy_pts["c"] or 0
    m_total = med_pts["s"] or 0
    m_cnt = med_pts["c"] or 0
    h_total = hard_pts["s"] or 0
    h_cnt = hard_pts["c"] or 0
    f_total = fight_pts["s"] or 0
    ev_total = event_pts["s"] or 0

    m = get_mention(target_user)
    await message.reply_text(
        f"<blockquote>📊 <b>𝐏𝐋𝐀𝐘𝐄𝐑 𝐀𝐔𝐃𝐈𝐓 & 𝐒𝐓𝐀𝐓𝐒 𝐂𝐀𝐋𝐂𝐔𝐋𝐀𝐓𝐎𝐑</b>\n\n"
        f"👤 <b>Player:</b> {m} (<code>{uid}</code>)\n"
        f"🎖️ <b>Level:</b> <code>Level {u['level']}</code> (<code>{u['exp']} EXP</code>)\n"
        f"💰 <b>Net Total Balance:</b> ⭐ <code>{u['points']} Stars/Points</code>\n\n"
        f"🟢 <b>Easy Solved:</b> <code>{e_cnt} words</code> (⭐ <code>{e_total} pts</code>)\n"
        f"🟡 <b>Medium Solved:</b> <code>{m_cnt} words</code> (⭐ <code>{m_total} pts</code>)\n"
        f"🔴 <b>Hard Solved:</b> <code>{h_cnt} words</code> (⭐ <code>{h_total} pts</code>)\n"
        f"🌟 <b>Event Mystery Gains:</b> ⭐ <code>{ev_total} pts</code>\n\n"
        f"⚔️ <b>Fights Record:</b> <code>{u['fight_wins']}W - {u['fight_losses']}L</code>\n"
        f"🎲 <b>Bet Fights Record:</b> <code>{u['bet_wins']}W - {u['bet_losses']}L</code> (⭐ <code>{f_total} pts net</code>)</blockquote>",
        parse_mode=ParseMode.HTML
    )

# ============================================================
# LOGGING TOGGLE COMMAND (/log)
# ============================================================

@app.on_message(filters.command(["log", "logging"]))
async def log_toggle_cmd(_, message: Message):
    if not message.from_user or not await is_admin_or_owner(message.chat, message.from_user.id):
        return await message.reply_text("<blockquote>❌ <b>Only group admins or bot owner can toggle logs.</b></blockquote>", parse_mode=ParseMode.HTML)

    args = message.command[1:]
    s = get_settings(message.chat.id)

    if args and args[0].lower() in ("on", "enable", "true"):
        new_val = 1
    elif args and args[0].lower() in ("off", "disable", "false"):
        new_val = 0
    else:
        new_val = 0 if s["logging_enabled"] else 1

    DB.execute("UPDATE settings SET logging_enabled=? WHERE chat_id=?", (new_val, message.chat.id))
    DB.commit()

    st_text = "ENABLED" if new_val else "DISABLED"
    await message.reply_text(f"<blockquote>📡 <b>Logger Group Notifications: <code>{st_text}</code> for this chat!</b></blockquote>", parse_mode=ParseMode.HTML)

# ============================================================
# JUMBLE COMMAND (LOOP PUZZLE LAUNCHER WITH AUTO-ENABLE)
# ============================================================

@app.on_message(filters.command("jumble"))
async def jumble_cmd(_, message: Message):
    ensure_user(message.from_user)
    if message.chat.id in JUMBLE_FIGHT:
        return await message.reply_text("<blockquote>⚔️ <b>Jumble Fight chal rahi hai, match khatam hone tak wait karein.</b></blockquote>", parse_mode=ParseMode.HTML)

    # Automatically enable group if it was stopped/disabled
    DB.execute("UPDATE settings SET is_active=1 WHERE chat_id=?", (message.chat.id,))
    DB.commit()

    s = get_settings(message.chat.id)
    default_d = s["default_diff"] if "default_diff" in s.keys() else "medium"
    
    # If user provided difficulty (e.g. /jumble easy)
    difficulty = default_d
    if len(message.command) > 1:
        cand = message.command[1].lower()
        if cand in WORDS:
            difficulty = cand

    await start_game(message.chat.id, difficulty, message)

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
        f"🛡️ <b>25% 𝐋ᴏsᴇʀ 𝐂ᴀsʜʙᴀᴄᴋ:</b> <code>{amount * 2 - int(amount * 2 * 0.75)} pts</code>\n"
        f"⚙️ <b>𝐌ᴏᴅᴇ:</b> <code>{diff.title()}</code> | ⏱️ <b>𝐓ɪᴍᴇʀ:</b> <code>60s</code>\n\n"
        f"👉 {m2}, match shuru karne ke liye <b>Accept Bet</b> par click karo!\n"
        f"<i>(Points tab hi deduct honge jab target accept karega)</i></blockquote>",
        reply_markup=kb,
        parse_mode=ParseMode.HTML
    )

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
# RUN BOT
# ============================================================

if __name__ == "__main__":
    print("🚀 Advanced Jumble, Bet Fight, Level, Shop & Event Bot Started Successfully!")
    asyncio.get_event_loop().create_task(resume_all_active_games())
    asyncio.get_event_loop().create_task(auto_backup_task())
    asyncio.get_event_loop().create_task(event_scheduler_loop())
    app.run()

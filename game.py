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
    event_active INTEGER DEFAULT 1
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
    }
    for k, v in defaults.items():
        DB.execute("INSERT OR IGNORE INTO bot_config (key, value) VALUES (?, ?)", (k, v))

    user_cols = [c[1] for c in DB.execute("PRAGMA table_info(users)").fetchall()]
    if "exp" not in user_cols:
        DB.execute("ALTER TABLE users ADD COLUMN exp INTEGER DEFAULT 0")
    if "level" not in user_cols:
        DB.execute("ALTER TABLE users ADD COLUMN level INTEGER DEFAULT 1")
    if "point_card_exp" not in user_cols:
        DB.execute("ALTER TABLE users ADD COLUMN point_card_exp REAL DEFAULT 0")
    if "level_card_exp" not in user_cols:
        DB.execute("ALTER TABLE users ADD COLUMN level_card_exp REAL DEFAULT 0")

    settings_cols = [c[1] for c in DB.execute("PRAGMA table_info(settings)").fetchall()]
    if "event_active" not in settings_cols:
        DB.execute("ALTER TABLE settings ADD COLUMN event_active INTEGER DEFAULT 1")

    for ew in DEFAULT_EVENT:
        DB.execute("INSERT OR IGNORE INTO event_words (word) VALUES (?)", (ew.lower().strip(),))

    try:
        users = DB.execute("SELECT user_id, points FROM users").fetchall()
        now = time.time()
        for u in users:
            uid = u["user_id"]
            real_pts = u["points"]
            history_sum_row = DB.execute("SELECT SUM(points) as total FROM score_history WHERE user_id = ?", (uid,)).fetchone()
            history_total = history_sum_row["total"] if history_sum_row and history_sum_row["total"] else 0
            
            diff = real_pts - history_total
            if diff != 0:
                DB.execute("INSERT INTO score_history (user_id, chat_id, points, timestamp) VALUES (?, 0, ?, ?)", (uid, diff, now))
        DB.commit()
    except Exception as e:
        print(f"Sync migration warning: {e}")

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
# HELPERS, EXP & POWER SYSTEMS
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
            INSERT INTO settings(chat_id, easy, medium, hard, default_diff, is_active, auto_delete, event_active)
            VALUES (?, 120, 300, 600, 'medium', 1, 0, 1)
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
    return max(1, (exp // 1000) + 1)

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

    asyncio.create_task(expire_game(chat_id, puzzle_id, expires, difficulty))

async def expire_game(chat_id, puzzle_id, expires, difficulty):
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
        asyncio.create_task(start_game(chat_id, difficulty, chat_id))

# ============================================================
# DYNAMIC EVENT DISPATCHER & SCHEDULER
# ============================================================

async def dispatch_event_by_id(event_id, target_chat_id=None):
    ev = DB.execute("SELECT * FROM events_bank WHERE id=?", (event_id,)).fetchone()
    if not ev or not ev["is_active"]:
        return

    word = ev["word"]
    jumbled = jumble_word(word)
    puzzle_id = random.randint(10000, 99999)
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

    image = make_puzzle_image(jumbled, ev["title"], puzzle_id, exp_val=ev["reward_exp"], is_event=True)
    hint_text = f"\n💡 <b>Hint:</b> <code>{ev['hint']}</code>" if ev["hint"] and ev["hint"] != "0" else ""
    
    caption_text = (
        f"<blockquote>🌟 <b>{ev['title'].upper()} EVENT DROP!</b>\n\n"
        f"💎 <b>Reward Stars:</b> <code>+{ev['reward_stars']} pts</code>\n"
        f"⚡ <b>Reward EXP:</b> <code>+{ev['reward_exp']} EXP</code>{hint_text}\n"
        f"⏱️ <b>Time Limit:</b> <code>3 minutes</code></blockquote>\n\n"
        f"<blockquote>⚡ <i>Unscramble first to claim victory!</i></blockquote>"
    )

    for tid in targets:
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
            """, (tid, ev["id"], word, ev["hint"], puzzle_id, now, expires, sent.id))
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
                print(f"Scheduler loop error for event {de['id']}: {e}")

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

    pt_card_status = format_duration(u["point_card_exp"] - now) if u and u["point_card_exp"] > now else "Inactive"
    lvl_card_status = format_duration(u["level_card_exp"] - now) if u and u["level_card_exp"] > now else "Inactive"

    user_pts = u["points"] if u else 0
    user_lvl = u["level"] if u else 1
    user_exp = u["exp"] if u else 0

    text = (
        f"<blockquote>🛍️ <b>𝐉𝐔𝐌𝐁𝐋𝐄 𝐏𝐎𝐖𝐄𝐑 𝐒𝐇𝐎𝐏</b>\n\n"
        f"👤 <b>Your Balance:</b> ⭐ <code>{user_pts} pts</code>\n"
        f"🎖️ <b>Your Rank:</b> Level <code>{user_lvl}</code> (<code>{user_exp % 1000}/1000 EXP</code>)\n\n"
        f"⚡ <b>𝐀ᴄᴛɪᴠᴇ 𝐏ᴏᴡᴇʀs:</b>\n"
        f"• <b>Point Multiplication Card:</b> <code>{pt_card_status}</code>\n"
        f"• <b>Level Multiplication Card:</b> <code>{lvl_card_status}</code></blockquote>\n\n"
        f"<blockquote>🃏 <b>𝐀𝐯𝐚𝐢𝐥𝐚𝐛𝐥𝐞 𝐂𝐚𝐫𝐝𝐬:</b>\n\n"
        f"1️⃣ <b>Point Multiplication Card (2x Points)</b>\n"
        f"• Duration: <code>{pt_hrs} Hours</code> | Price: ⭐ <code>{pt_price} pts</code>\n"
        f"• Required Level: <code>Level {pt_req}+</code>\n\n"
        f"2️⃣ <b>Level Multiplication Card (2x EXP)</b>\n"
        f"• Duration: <code>{lvl_hrs} Hours</code> | Price: ⭐ <code>{lvl_price} pts</code>\n"
        f"• Required Level: <code>Level {lvl_req}+</code></blockquote>"
    )

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"⚡ Buy Point Card ({pt_price} pts)", callback_data="buy_card_point"),
            InlineKeyboardButton(f"🎖️ Buy Level Card ({lvl_price} pts)", callback_data="buy_card_level")
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
# JUMBLE FIGHT & JUMBLE BET FIGHT (1v1)
# ============================================================

JUMBLE_FIGHT = {}
FIGHT_LOBBY = {}
REBET_LOBBY = {}

def fight_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💡 𝐇ɪɴᴛ", callback_data="fight_hint")
        ]
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
                DB.execute("INSERT INTO score_history (user_id, chat_id, points, timestamp) VALUES (?, ?, ?, ?)", (winner, chat_id, total_payout, now))
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
            DB.execute("INSERT INTO score_history (user_id, chat_id, points, timestamp) VALUES (?, ?, ?, ?)", (p1, chat_id, bet_amt, now))
            DB.execute("INSERT INTO score_history (user_id, chat_id, points, timestamp) VALUES (?, ?, ?, ?)", (p2, chat_id, bet_amt, now))
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

# ============================================================
# DATABASE BACKUP SYSTEM (MANUAL & AUTO BACKUP)
# ============================================================

@app.on_message(filters.command(["backup", "dbbackup", "getdb"]))
async def backup_db_cmd(_, message: Message):
    if not message.from_user or not is_owner(message.from_user.id):
        return await message.reply_text("❌ Sirf Bot Owner database backup le sakta hai.")

    if not os.path.exists("jumble_game.db"):
        return await message.reply_text("❌ Database file nahi mili!")

    status_msg = await message.reply_text("📦 <i>Exporting database backup...</i>", parse_mode=ParseMode.HTML)
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
        await status_msg.edit_text(f"❌ Backup failed: <code>{str(e)}</code>")

async def auto_backup_task():
    while True:
        await asyncio.sleep(21600)
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
        "• <code>/shop</code> — 𝐏ᴏᴡᴇʀ 𝐂ᴀʀᴅ 𝐒ʜᴏᴘ\n"
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
        "• <code>/shop</code> — 𝐏ᴏᴡᴇʀ 𝐂ᴀʀᴅ 𝐒ʜᴏᴘ\n"
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
            "• <code>/setexp [easy|medium|hard] [exp]</code> — Set Mode EXP\n"
            "• <code>/setevent</code> — <b>Step-by-step Interactive Event Creator Wizard</b>\n"
            "• <code>/startevent</code> / <code>/stopevent</code> — Mystery Event Toggle\n"
            "• <code>/addeventword word1 word2</code> — Add mystery event words\n"
            "• <code>/deleventword word</code> — Delete event word\n"
            "• <code>/eventwords</code> — View event word bank\n"
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
    EVENT_WIZARD[uid] = {"step": 1, "title": "", "word": "", "hint": "", "stars": 0, "exp": 0, "interval": 4, "target": "group"}

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
# SETEXP COMMAND
# ============================================================

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
    events = DB.execute("SELECT * FROM events_bank WHERE is_active=1").fetchall()
    if not events:
        return await message.reply_text("<blockquote>📅 <b>Active Events List:</b>\n\n<i>Filhaal koi active mystery events configured nahi hain.</i></blockquote>", parse_mode=ParseMode.HTML)

    text = "<blockquote>📅 <b>𝐀𝐂𝐓𝐈𝐕𝐄 𝐌𝐘𝐒𝐓𝐄𝐑𝐘 𝐄𝐕𝐄𝐍𝐓𝐒 𝐋𝐈𝐒𝐓</b>\n\n"
    for ev in events:
        rem_time = max(0, ev["next_run"] - time.time())
        text += (
            f"🔹 <b>{ev['title']}</b> (#ID: {ev['id']})\n"
            f"• Word: <code>{ev['word'].upper()}</code> | Target: <code>{ev['target_type'].upper()}</code>\n"
            f"• Reward: ⭐ <code>{ev['reward_stars']} pts</code> | ⚡ <code>{ev['reward_exp']} EXP</code>\n"
            f"• Repeats: Every <code>{ev['interval_hrs']} hrs</code>\n"
            f"• Next Run In: <code>{format_duration(rem_time)}</code>\n\n"
        )
    text += "</blockquote>"

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Close", callback_data="close_panel")]
    ])
    await message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)

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
# UNIVERSAL MESSAGE DISPATCHER (WIZARD & ANSWERS)
# ============================================================

ALL_BOT_COMMANDS = {
    "start", "help", "jumble", "jumblefight", "fight", "rapido", "jumblebetfight", "betfight",
    "settings", "setting", "setpoints", "sethint", "setdaily", "setbonus", "daily", "bonus",
    "private", "public", "addword", "addwords", "delword", "delallword", "delallwords",
    "clearword", "clearwords", "word", "words", "auth", "unauth", "authlist", "update", "gitpull",
    "stats", "stat", "mystats", "score", "leaderboard", "top", "rank", "lb", "backup", "dbbackup", "getdb",
    "shop", "store", "setcard", "setreward", "setevent", "startevent", "stopevent", "addeventword", "deleventword", "eventwords", "setexp", "eventlist", "events", "cancel"
}

@app.on_message(filters.text)
async def universal_text_dispatcher(_, message: Message):
    if not message.from_user or not message.text:
        return

    uid = message.from_user.id
    txt = message.text.strip()

    # 1. Wizard Steps (Allowed in Groups & DMs)
    if uid in EVENT_WIZARD and not txt.startswith("/"):
        data = EVENT_WIZARD[uid]
        step = data["step"]

        if step == 1:
            data["title"] = txt
            data["step"] = 2
            return await message.reply_text(
                "<blockquote>🌟 <b>𝐄𝐕𝐄𝐍𝐓 𝐂𝐑𝐄𝐀𝐓𝐎𝐑 𝐖𝐈𝐙𝐀𝐑𝐃 (Step 2/7)</b>\n\n"
                "Ab is event ka <b>Unique Word</b> kya hoga? (Jaise: <i>quantum</i>)</blockquote>",
                parse_mode=ParseMode.HTML
            )
        elif step == 2:
            w = "".join(c.lower() for c in txt if c.isalpha()).strip()
            if len(w) < 3:
                return await message.reply_text("<blockquote>❌ <b>Word kam se kam 3 letters ka hona chahiye.</b></blockquote>", parse_mode=ParseMode.HTML)
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

    # Ignore command texts from game solvers
    if txt.startswith("/") or txt.startswith("!") or txt.startswith("."):
        cmd_candidate = txt[1:].split()[0].split("@")[0].lower()
        if cmd_candidate in ALL_BOT_COMMANDS:
            return

    # Answer handler in groups
    if is_group(message):
        await group_answer_handler(_, message)

# ============================================================
# AUTO-RESUME GAMES ON BOT STARTUP (SAFE RESUME)
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

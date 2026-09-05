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
# HELPERS
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
    """, (user.id, user.username or "", user.first_name or "Player"))
    DB.commit()

def get_user(user_id):
    return DB.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()

def is_owner(user_id):
    return int(user_id) == int(OWNER_ID) if user_id else False

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
    if is_owner(user_id) or chat.type in (ChatType.PRIVATE,):
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
    return f"{hrs}h {mins}m" if hrs > 0 else f"{mins}m"

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
    used = {row["word"] for row in DB.execute("SELECT word FROM used_words WHERE chat_id=? AND difficulty=?", (chat_id, difficulty)).fetchall()}
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
    paths = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf", "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"]
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
    word_font = get_font(85 if text_len <= 7 else 65 if text_len <= 11 else 50 if text_len <= 15 else 38)
    display_text = "   ".join(jumbled) if text_len <= 7 else "  ".join(jumbled) if text_len <= 11 else " ".join(jumbled)

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
# GAME CORE (AUTO-LOOP)
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
        f"🎯 <b>Difficulty:</b> <code>{difficulty.title()}</code>\n"
        f"⏱️ <b>Time:</b> <code>{timer_val // 60}m {timer_val % 60}s</code>\n"
        f"⭐ <b>Reward:</b> <code>+{reward_pts} Points</code>\n"
        f"⚡ <b>EXP:</b> <code>+{reward_exp} EXP</code>\n"
        f"💡 <b>Hints:</b> <code>{hint_limit}/word</code>\n\n"
        f"🔀 <i>Unscramble the letters & type in chat!</i></blockquote>"
    )

    try:
        if isinstance(message_or_chat, Message):
            sent = await message_or_chat.reply_photo(photo=image, caption=caption_text, reply_markup=normal_keyboard(), parse_mode=ParseMode.HTML)
        else:
            sent = await app.send_photo(chat_id, photo=image, caption=caption_text, reply_markup=normal_keyboard(), parse_mode=ParseMode.HTML)

        DB.execute("UPDATE games SET message_id=? WHERE chat_id=?", (sent.id, chat_id))
        DB.commit()
    except Exception:
        pass

    asyncio.create_task(expire_game(chat_id, puzzle_id, expires))

async def expire_game(chat_id, puzzle_id, expires):
    await asyncio.sleep(max(0, expires - time.time()))
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
            f"<blockquote>⏰ <b>Time's Up!</b>\n\n❌ <b>Nobody solved it.</b>\n✅ <b>Answer:</b> <code>{row['word'].upper()}</code>\n\n🔄 <i>Next puzzle starting...</i></blockquote>",
            parse_mode=ParseMode.HTML
        )
        if s["auto_delete"]:
            asyncio.create_task(delete_after(exp_msg, 4))
    except Exception:
        pass

    await asyncio.sleep(3)
    if s["is_active"]:
        asyncio.create_task(start_game(chat_id, s["default_diff"], chat_id))

# ============================================================
# SHOP UI BUILDER
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

    pt_status = format_duration(u["point_card_exp"] - now) if u and u["point_card_exp"] > now else "Inactive"
    lvl_status = format_duration(u["level_card_exp"] - now) if u and u["level_card_exp"] > now else "Inactive"
    user_pts = u["points"] if u else 0
    user_lvl = u["level"] if u else 1
    user_exp = u["exp"] if u else 0

    text = (
        f"<blockquote>🛍️ <b>JUMBLE POWER & EXP SHOP</b>\n\n"
        f"👤 <b>Balance:</b> ⭐ <code>{user_pts} stars</code>\n"
        f"🎖️ <b>Rank:</b> Level <code>{user_lvl}</code> (<code>{user_exp % step}/{step} EXP</code>)\n\n"
        f"⚡ <b>Active Powers:</b>\n"
        f"• 2x Point Booster: <code>{pt_status}</code>\n"
        f"• 2x Level Booster: <code>{lvl_status}</code>\n\n"
        f"🃏 <b>Store Items:</b>\n"
        f"1️⃣ <b>Point Multiplier (2x Points)</b> — ⭐ <code>{pt_price} stars</code> ({pt_hrs}h, Req Lvl {pt_req})\n"
        f"2️⃣ <b>Level Multiplier (2x EXP)</b> — ⭐ <code>{lvl_price} stars</code> ({lvl_hrs}h, Req Lvl {lvl_req})\n"
        f"3️⃣ <b>Instant +{exp_rew} EXP Pack</b> — ⭐ <code>{exp_cost} stars</code></blockquote>"
    )

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"⚡ Buy 2x Point ({pt_price} ⭐)", callback_data="buy_card_point"),
            InlineKeyboardButton(f"🎖️ Buy 2x EXP ({lvl_price} ⭐)", callback_data="buy_card_level")
        ],
        [InlineKeyboardButton(f"✨ Instant +{exp_rew} EXP ({exp_cost} ⭐)", callback_data="buy_instant_exp")],
        [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_shop"), InlineKeyboardButton("❌ Close", callback_data="close_panel")]
    ])
    return text, kb

# ============================================================
# CALLBACK QUERIES ROUTER (INSTANT ANSWER & STRICT CATCH)
# ============================================================

@app.on_callback_query()
async def callback_router(_, query: CallbackQuery):
    await query.answer()
    data = query.data
    chat_id = query.message.chat.id
    user_id = query.from_user.id
    now = time.time()

    if data.startswith("ev_target_"):
        target_mode = data.split("_")[2]
        if user_id not in EVENT_WIZARD:
            return await query.message.edit_text("<blockquote>❌ <b>Wizard session expired. Use /setevent again.</b></blockquote>", parse_mode=ParseMode.HTML)

        EVENT_WIZARD[user_id]["target"] = target_mode
        w = EVENT_WIZARD[user_id]
        hint_str = w['hint'] if w['hint'] != "0" else "None"

        review_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Confirm & Save Event", callback_data="ev_confirm_save"), InlineKeyboardButton("✏️ Edit / Restart", callback_data="ev_restart_wizard")],
            [InlineKeyboardButton("❌ Cancel Event", callback_data="ev_cancel_wizard")]
        ])

        review_text = (
            f"<blockquote>📋 <b>EVENT CONFIRMATION REVIEW</b>\n\n"
            f"📌 <b>Title:</b> <code>{w['title']}</code>\n"
            f"🔑 <b>Word:</b> <code>{w['word'].upper()}</code>\n"
            f"💡 <b>Hint:</b> <code>{hint_str}</code>\n"
            f"⭐ <b>Stars:</b> <code>{w['stars']} pts</code> | ⚡ <b>EXP:</b> <code>{w['exp']} EXP</code>\n"
            f"⏰ <b>Repeat:</b> Every <code>{w['interval']} Hours</code>\n"
            f"🎯 <b>Target:</b> <code>{w['target'].upper()}</code></blockquote>"
        )
        return await query.message.edit_text(review_text, reply_markup=review_kb, parse_mode=ParseMode.HTML)

    elif data == "ev_confirm_save":
        if user_id not in EVENT_WIZARD:
            return await query.message.edit_text("<blockquote>❌ <b>Session expired.</b></blockquote>", parse_mode=ParseMode.HTML)
        w = EVENT_WIZARD[user_id]
        next_run = now + (w["interval"] * 3600)
        DB.execute("""
            INSERT INTO events_bank (title, word, hint, reward_stars, reward_exp, interval_hrs, target_type, next_run, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, (w["title"], w["word"], w["hint"], w["stars"], w["exp"], w["interval"], w["target"], next_run))
        DB.commit()
        del EVENT_WIZARD[user_id]
        return await query.message.edit_text("<blockquote>✅ <b>Event Successfully Created & Scheduled! Check with /eventlist.</b></blockquote>", parse_mode=ParseMode.HTML)

    elif data == "ev_restart_wizard":
        EVENT_WIZARD[user_id] = {"step": 1, "title": "", "word": "", "hint": "0", "stars": 0, "exp": 0, "interval": 4, "target": "group"}
        return await query.message.edit_text("<blockquote>🌟 <b>EVENT CREATOR WIZARD (Step 1/7)</b>\n\nEvent ka title/naam likhein:</blockquote>", parse_mode=ParseMode.HTML)

    elif data == "ev_cancel_wizard":
        if user_id in EVENT_WIZARD:
            del EVENT_WIZARD[user_id]
        return await query.message.edit_text("<blockquote>❌ <b>Event wizard cancelled.</b></blockquote>", parse_mode=ParseMode.HTML)

    elif data.startswith("ev_del_"):
        if not is_authed(user_id):
            return
        ev_id = int(data.split("_")[2])
        DB.execute("DELETE FROM events_bank WHERE id=?", (ev_id,))
        DB.commit()
        return await query.message.edit_text(f"<blockquote>🗑️ <b>Event #{ev_id} deleted successfully.</b></blockquote>", parse_mode=ParseMode.HTML)

    elif data.startswith("ev_toggle_"):
        if not is_authed(user_id):
            return
        ev_id = int(data.split("_")[2])
        ev = DB.execute("SELECT is_active FROM events_bank WHERE id=?", (ev_id,)).fetchone()
        if ev:
            new_st = 0 if ev["is_active"] else 1
            DB.execute("UPDATE events_bank SET is_active=? WHERE id=?", (new_st, ev_id))
            DB.commit()
            st_text = "Activated" if new_st else "Paused"
            return await query.message.edit_text(f"<blockquote>⚙️ <b>Event #{ev_id} status changed to: {st_text}</b></blockquote>", parse_mode=ParseMode.HTML)

    elif data == "buy_instant_exp":
        ensure_user(query.from_user)
        u = get_user(user_id)
        cost = get_global_config("shop_exp_cost", 1000)
        exp_rew = get_global_config("shop_exp_reward", 500)
        if (u["points"] or 0) < cost:
            return await query.message.reply_text(f"<blockquote>❌ <b>Stars kam hain! Required: {cost} stars.</b></blockquote>", parse_mode=ParseMode.HTML)
        new_exp = (u["exp"] or 0) + exp_rew
        new_lvl = calculate_level(new_exp)
        DB.execute("UPDATE users SET points = points - ?, exp = ?, level = ? WHERE user_id = ?", (cost, new_exp, new_lvl, user_id))
        DB.execute("INSERT INTO score_history (user_id, chat_id, points, tag, timestamp) VALUES (?, 0, ?, 'shop_exp', ?)", (user_id, -cost, now))
        DB.commit()
        text, kb = build_shop_text_and_kb(user_id)
        return await query.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)

    elif data == "open_shop_btn" or data == "refresh_shop":
        ensure_user(query.from_user)
        text, kb = build_shop_text_and_kb(user_id)
        return await query.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)

    elif data.startswith("buy_card_"):
        ensure_user(query.from_user)
        u = get_user(user_id)
        card_type = data.split("_")[2]
        prefix = "card_point" if card_type == "point" else "card_level"
        price = get_global_config(f"{prefix}_price", 500)
        hrs = get_global_config(f"{prefix}_hrs", 3)
        min_lvl = get_global_config(f"{prefix}_req_lvl", 1)

        if (u["level"] or 1) < min_lvl or (u["points"] or 0) < price:
            return await query.message.reply_text("<blockquote>❌ <b>Required Level ya Stars poore nahi hain.</b></blockquote>", parse_mode=ParseMode.HTML)

        field = "point_card_exp" if card_type == "point" else "level_card_exp"
        cur_exp = u[field] if u[field] and u[field] > now else now
        DB.execute(f"UPDATE users SET points = points - ?, {field} = ? WHERE user_id = ?", (price, cur_exp + (hrs * 3600), user_id))
        DB.execute("INSERT INTO score_history (user_id, chat_id, points, tag, timestamp) VALUES (?, 0, ?, 'shop_card', ?)", (user_id, -price, now))
        DB.commit()
        text, kb = build_shop_text_and_kb(user_id)
        return await query.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)

    elif data == "close_panel":
        return await query.message.delete()

# ============================================================
# COMMAND DISPATCHER & WIZARD ENGINE
# ============================================================

ALL_BOT_COMMANDS = {
    "start", "help", "jumble", "shop", "store", "setevent", "cancel", "setglobalexp",
    "storeexpprize", "setexp", "eventlist", "events", "startevent", "stopevent",
    "addeventword", "deleventword", "eventwords", "setcard", "stats", "calculate", "log"
}

@app.on_message(filters.command("jumble"))
async def jumble_cmd_handler(_, message: Message):
    DB.execute("UPDATE settings SET is_active=1 WHERE chat_id=?", (message.chat.id,))
    DB.commit()
    s = get_settings(message.chat.id)
    diff = s["default_diff"]
    if len(message.command) > 1 and message.command[1].lower() in WORDS:
        diff = message.command[1].lower()
    await start_game(message.chat.id, diff, message)

@app.on_message(filters.command("setevent"))
async def set_event_cmd_handler(_, message: Message):
    if not is_authed(message.from_user.id):
        return await message.reply_text("<blockquote>❌ <b>Authorized users only.</b></blockquote>", parse_mode=ParseMode.HTML)
    EVENT_WIZARD[message.from_user.id] = {"step": 1, "title": "", "word": "", "hint": "0", "stars": 0, "exp": 0, "interval": 4, "target": "group"}
    await message.reply_text("<blockquote>🌟 <b>EVENT CREATOR WIZARD (Step 1/7)</b>\n\nEvent ka Title/Naam likhein:</blockquote>", parse_mode=ParseMode.HTML)

@app.on_message(filters.command("cancel"))
async def cancel_wizard_handler(_, message: Message):
    if message.from_user and message.from_user.id in EVENT_WIZARD:
        del EVENT_WIZARD[message.from_user.id]
        await message.reply_text("<blockquote>❌ <b>Event wizard cancelled.</b></blockquote>", parse_mode=ParseMode.HTML)

@app.on_message(filters.command("setglobalexp"))
async def set_global_exp_cmd(_, message: Message):
    if not is_authed(message.from_user.id):
        return
    nums = re.findall(r"\d+", message.text)
    if not nums:
        return await message.reply_text("<blockquote>Usage: <code>/setglobalexp 500</code></blockquote>", parse_mode=ParseMode.HTML)
    val = int(nums[0])
    set_global_config("global_exp_per_lvl", val)
    await message.reply_text(f"<blockquote>✅ <b>Global Level EXP Requirement set to {val} EXP!</b></blockquote>", parse_mode=ParseMode.HTML)

@app.on_message(filters.command("storeexpprize"))
async def set_store_exp_prize_cmd(_, message: Message):
    if not is_authed(message.from_user.id):
        return
    nums = [int(n) for n in re.findall(r"\d+", message.text)]
    if len(nums) < 2:
        return await message.reply_text("<blockquote>Usage: <code>/storeexpprize [cost] [exp]</code></blockquote>", parse_mode=ParseMode.HTML)
    set_global_config("shop_exp_cost", nums[0])
    set_global_config("shop_exp_reward", nums[1])
    await message.reply_text(f"<blockquote>✅ <b>Shop EXP Pack set: {nums[0]} stars for {nums[1]} EXP!</b></blockquote>", parse_mode=ParseMode.HTML)

@app.on_message(filters.command("stats"))
async def stats_cmd_handler(_, message: Message):
    u = get_user(message.from_user.id)
    step = get_global_config("global_exp_per_lvl", 500)
    await message.reply_text(
        f"<blockquote>👤 <b>Player:</b> {get_mention(message.from_user)}\n"
        f"🎖️ <b>Level:</b> <code>{u['level']}</code> (<code>{u['exp'] % step}/{step} EXP</code>)\n"
        f"⭐ <b>Stars:</b> <code>{u['points']}</code> | 🧩 <b>Solved:</b> <code>{u['solved']}</code></blockquote>",
        parse_mode=ParseMode.HTML
    )

@app.on_message(filters.command("shop"))
async def shop_cmd_handler(_, message: Message):
    text, kb = build_shop_text_and_kb(message.from_user.id)
    await message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)

@app.on_message(filters.command("eventlist"))
async def eventlist_cmd_handler(_, message: Message):
    events = DB.execute("SELECT * FROM events_bank").fetchall()
    if not events:
        return await message.reply_text("<blockquote>📅 <b>No active events in bank.</b></blockquote>", parse_mode=ParseMode.HTML)
    text = "<blockquote>📅 <b>MYSTERY EVENTS LIST</b>\n\n"
    btns = []
    for ev in events:
        text += f"🔹 <b>{ev['title']}</b> (ID: <code>{ev['id']}</code>) | Target: <code>{ev['target_type']}</code>\n"
        btns.append([InlineKeyboardButton(f"🛑 Toggle #{ev['id']}", callback_data=f"ev_toggle_{ev['id']}"), InlineKeyboardButton(f"🗑️ Delete #{ev['id']}", callback_data=f"ev_del_{ev['id']}")])
    text += "</blockquote>"
    btns.append([InlineKeyboardButton("❌ Close", callback_data="close_panel")])
    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(btns), parse_mode=ParseMode.HTML)

# ============================================================
# UNIVERSAL TEXT DISPATCHER
# ============================================================

@app.on_message(filters.text)
async def universal_text_dispatcher(_, message: Message):
    if not message.from_user or not message.text:
        return
    uid = message.from_user.id
    txt = message.text.strip()

    if uid in EVENT_WIZARD and not txt.startswith("/"):
        w = EVENT_WIZARD[uid]
        step = w["step"]
        if step == 1:
            w["title"] = txt
            w["step"] = 2
            return await message.reply_text("<blockquote>🌟 <b>EVENT CREATOR WIZARD (Step 2/7)</b>\n\nUnique Word likhein (ya <code>random</code>):</blockquote>", parse_mode=ParseMode.HTML)
        elif step == 2:
            w["word"] = txt.lower().strip()
            w["step"] = 3
            return await message.reply_text("<blockquote>🌟 <b>EVENT CREATOR WIZARD (Step 3/7)</b>\n\nHint likhein (ya <code>0</code>):</blockquote>", parse_mode=ParseMode.HTML)
        elif step == 3:
            w["hint"] = txt
            w["step"] = 4
            return await message.reply_text("<blockquote>🌟 <b>EVENT CREATOR WIZARD (Step 4/7)</b>\n\nReward Stars kitne honge?:</blockquote>", parse_mode=ParseMode.HTML)
        elif step == 4:
            nums = re.findall(r"\d+", txt)
            if nums:
                w["stars"] = int(nums[0])
                w["step"] = 5
                return await message.reply_text("<blockquote>🌟 <b>EVENT CREATOR WIZARD (Step 5/7)</b>\n\nReward EXP kitna hoga?:</blockquote>", parse_mode=ParseMode.HTML)
        elif step == 5:
            nums = re.findall(r"\d+", txt)
            if nums:
                w["exp"] = int(nums[0])
                w["step"] = 6
                return await message.reply_text("<blockquote>🌟 <b>EVENT CREATOR WIZARD (Step 6/7)</b>\n\nRepeat Interval (Ghante) likhein:</blockquote>", parse_mode=ParseMode.HTML)
        elif step == 6:
            nums = re.findall(r"\d+", txt)
            if nums:
                w["interval"] = int(nums[0])
                w["step"] = 7
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("👥 Groups Only", callback_data="ev_target_group"), InlineKeyboardButton("💬 DMs Only", callback_data="ev_target_dm")],
                    [InlineKeyboardButton("🌍 Both Groups & DMs", callback_data="ev_target_both")]
                ])
                return await message.reply_text("<blockquote>🌟 <b>EVENT CREATOR WIZARD (Step 7/7)</b>\n\nTarget choose karein:</blockquote>", reply_markup=kb, parse_mode=ParseMode.HTML)

    if txt.startswith("/") or txt.startswith("!") or txt.startswith("."):
        return

    # Check puzzle solution
    chat_id = message.chat.id
    game = DB.execute("SELECT * FROM games WHERE chat_id=? AND solved=0", (chat_id,)).fetchone()
    if game and time.time() <= game["expires"] and clean_answer(txt) == clean_answer(game["word"]):
        DB.execute("UPDATE games SET solved=1 WHERE chat_id=?", (chat_id,))
        ensure_user(message.from_user)
        u = get_user(uid)
        pts = get_global_config(f"points_{game['difficulty']}", 10)
        exp_gain = get_global_config(f"exp_{game['difficulty']}", 30)
        new_exp = (u["exp"] or 0) + exp_gain
        new_lvl = calculate_level(new_exp)
        DB.execute("UPDATE users SET points=points+?, solved=solved+1, exp=?, level=? WHERE user_id=?", (pts, new_exp, new_lvl, uid))
        DB.commit()

        await message.reply_text(
            f"<blockquote>🎉 <b>CORRECT!</b>\n\n👤 {get_mention(message.from_user)}\n✅ <b>Answer:</b> <code>{game['word'].upper()}</code>\n⭐ <b>+{pts} points</b> | ⚡ <b>+{exp_gain} EXP</b> (Lvl {new_lvl})</blockquote>",
            parse_mode=ParseMode.HTML
        )
        s = get_settings(chat_id)
        if s["is_active"]:
            await asyncio.sleep(3)
            await start_game(chat_id, s["default_diff"], chat_id)

# ============================================================
# MAIN ENTRYPOINT
# ============================================================

if __name__ == "__main__":
    print("🚀 Advanced Jumble, Bet Fight, Level, Shop & Event Bot Started Successfully!")
    asyncio.get_event_loop().create_task(resume_all_active_games())
    asyncio.get_event_loop().create_task(auto_backup_task())
    asyncio.get_event_loop().create_task(event_scheduler_loop())
    app.run()

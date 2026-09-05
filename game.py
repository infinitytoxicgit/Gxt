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
from pyrogram.errors import (
    MessageNotModified,
    RPCError,
    ChannelInvalid,
    ChannelPrivate,
    PeerIdInvalid,
    UserIsBlocked,
)
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    Message,
    ChatMemberUpdated,
)

# ============================================================
# OPTIONAL DOTENV
# ============================================================

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


# ============================================================
# CONFIG
# ============================================================

API_ID = int(os.getenv("API_ID", "35218869"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_ID = int(os.getenv("OWNER_ID", "8564072723"))

START_IMG = os.getenv("START_IMG", "")
SUPPORT_GC = os.getenv("SUPPORT_GC", "")
ADD_ME_URL = os.getenv("ADD_ME_URL", "")
MUSIC_BOT_URL = os.getenv("MUSIC_BOT_URL", "")

LOGGER_GROUP_ID = int(
    os.getenv("LOGGER_GROUP_ID", "-1003515360437")
)

DB_FILE = os.getenv(
    "JUMBLE_DB",
    "jumble_game.db"
)

if not API_HASH or not BOT_TOKEN:
    print(
        "WARNING: API_HASH and BOT_TOKEN "
        "environment variables are not set."
    )


# ============================================================
# PYROGRAM CLIENT
# ============================================================

app = Client(
    "advanced_jumble_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)


# ============================================================
# DATABASE
# ============================================================

DB = sqlite3.connect(
    DB_FILE,
    check_same_thread=False
)

DB.row_factory = sqlite3.Row

LOCK = asyncio.Lock()


# ============================================================
# GLOBAL GAME STATE
# ============================================================

JUMBLE_FIGHT = {}

FIGHT_LOBBY = {}

REBET_LOBBY = {}

EVENT_WIZARD = {}

EVENT_WORDS = set()


# ============================================================
# DEFAULT WORD BANKS
# ============================================================

DEFAULT_EASY = """
cat dog sun moon book tree fish milk ball apple house
water green red blue black white chair table phone cloud
star bird king queen road car train school friend happy
music
""".split()


DEFAULT_MEDIUM = """
planet diamond computer keyboard elephant mountain hospital
internet football cricket rainbow sandwich chocolate camera
teacher student garden morning evening country language
picture journey weather airport library village freedom
""".split()


DEFAULT_HARD = """
photosynthesis cryptocurrency metamorphic electroencephalography
compartmentalization counterrevolutionary kaleidoscope
quantum singularity transcendence bioluminescent
incomprehensible interdisciplinary entrepreneurial
misunderstanding synchronization telecommunications
""".split()


DEFAULT_EVENT = """
supernova quantum singularity kaleidoscope cryptocurrency
metamorphic photosynthesis transcendence bioluminescent
counterrevolutionary electroencephalography
compartmentalization
""".split()


# ============================================================
# DATABASE MIGRATION HELPERS
# ============================================================

def column_exists(table, column):
    rows = DB.execute(
        f"PRAGMA table_info({table})"
    ).fetchall()

    return any(
        row["name"] == column
        for row in rows
    )


def add_column(table, column, definition):
    if not column_exists(table, column):
        DB.execute(
            f"ALTER TABLE {table} "
            f"ADD COLUMN {column} {definition}"
        )


# ============================================================
# DATABASE MIGRATIONS
# ============================================================

def run_migrations():

    DB.executescript(
        """
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
            last_daily INTEGER DEFAULT 0,
            exp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1,
            point_card_exp INTEGER DEFAULT 0,
            level_card_exp INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS auth_users (
            user_id INTEGER PRIMARY KEY
        );

        CREATE TABLE IF NOT EXISTS custom_words (
            chat_id INTEGER,
            word TEXT,
            difficulty TEXT DEFAULT 'medium'
        );

        CREATE TABLE IF NOT EXISTS settings (
            chat_id INTEGER PRIMARY KEY,
            easy INTEGER DEFAULT 1,
            medium INTEGER DEFAULT 1,
            hard INTEGER DEFAULT 1,
            default_diff TEXT DEFAULT 'medium',
            is_active INTEGER DEFAULT 0,
            auto_delete INTEGER DEFAULT 1,
            event_active INTEGER DEFAULT 1,
            logging_enabled INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS bot_config (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS group_adders (
            chat_id INTEGER PRIMARY KEY,
            user_id INTEGER
        );

        CREATE TABLE IF NOT EXISTS group_bonus (
            chat_id INTEGER PRIMARY KEY,
            claimed INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS games (
            chat_id INTEGER PRIMARY KEY,
            word TEXT,
            jumbled TEXT,
            difficulty TEXT,
            puzzle_id TEXT,
            started INTEGER,
            expires INTEGER,
            message_id INTEGER
        );

        CREATE TABLE IF NOT EXISTS used_words (
            chat_id INTEGER,
            word TEXT,
            used_at INTEGER
        );

        CREATE TABLE IF NOT EXISTS puzzle_hints (
            chat_id INTEGER PRIMARY KEY,
            hint TEXT
        );

        CREATE TABLE IF NOT EXISTS score_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            chat_id INTEGER,
            points INTEGER,
            timestamp INTEGER,
            tag TEXT DEFAULT 'normal'
        );

        CREATE TABLE IF NOT EXISTS event_words (
            word TEXT PRIMARY KEY,
            hint TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS events_bank (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            word TEXT,
            hint TEXT,
            reward_stars INTEGER DEFAULT 0,
            reward_exp INTEGER DEFAULT 0,
            interval_hrs REAL DEFAULT 24,
            target_type TEXT DEFAULT 'group',
            next_run INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS event_games (
            chat_id INTEGER PRIMARY KEY,
            event_id INTEGER,
            word TEXT,
            hint TEXT,
            puzzle_id TEXT,
            started INTEGER,
            expires INTEGER,
            message_id INTEGER,
            solved INTEGER DEFAULT 0
        );
        """
    )

    # --------------------------------------------------------
    # USERS
    # --------------------------------------------------------

    add_column(
        "users",
        "exp",
        "INTEGER DEFAULT 0"
    )

    add_column(
        "users",
        "level",
        "INTEGER DEFAULT 1"
    )

    add_column(
        "users",
        "point_card_exp",
        "INTEGER DEFAULT 0"
    )

    add_column(
        "users",
        "level_card_exp",
        "INTEGER DEFAULT 0"
    )

    # --------------------------------------------------------
    # SETTINGS
    # --------------------------------------------------------

    add_column(
        "settings",
        "event_active",
        "INTEGER DEFAULT 1"
    )

    add_column(
        "settings",
        "logging_enabled",
        "INTEGER DEFAULT 0"
    )

    # --------------------------------------------------------
    # SCORE HISTORY
    # --------------------------------------------------------

    add_column(
        "score_history",
        "tag",
        "TEXT DEFAULT 'normal'"
    )


    # ========================================================
    # GLOBAL DEFAULT CONFIG
    # ========================================================

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
        "shop_exp_reward": 500,
    }

    for key, value in defaults.items():

        DB.execute(
            """
            INSERT OR IGNORE INTO bot_config
            (key, value)
            VALUES (?, ?)
            """,
            (
                key,
                str(value)
            )
        )


    # ========================================================
    # DEFAULT EVENT WORDS
    # ========================================================

    for word in DEFAULT_EVENT:

        DB.execute(
            """
            INSERT OR IGNORE INTO event_words
            (word, hint)
            VALUES (?, ?)
            """,
            (
                word.lower(),
                "Event word"
            )
        )


    DB.commit()


    # ========================================================
    # LOAD EVENT WORDS
    # ========================================================

    EVENT_WORDS.clear()

    rows = DB.execute(
        "SELECT word FROM event_words"
    ).fetchall()

    for row in rows:
        EVENT_WORDS.add(
            row["word"]
        )


run_migrations()


# ============================================================
# GLOBAL CONFIG HELPERS
# ============================================================

def get_global_config(key, default=None):

    row = DB.execute(
        """
        SELECT value
        FROM bot_config
        WHERE key=?
        """,
        (key,)
    ).fetchone()

    if row:
        return row["value"]

    return default


def set_global_config(key, value):

    DB.execute(
        """
        INSERT OR REPLACE INTO bot_config
        (key, value)
        VALUES (?, ?)
        """,
        (
            key,
            str(value)
        )
    )

    DB.commit()


# ============================================================
# USER HELPERS
# ============================================================

def ensure_user(user):

    if not user:
        return

    user_id = user.id

    username = user.username or ""

    name = (
        user.first_name or ""
    ).strip()

    DB.execute(
        """
        INSERT INTO users
        (
            user_id,
            username,
            name
        )
        VALUES (?, ?, ?)

        ON CONFLICT(user_id)
        DO UPDATE SET
            username=excluded.username,
            name=excluded.name
        """,
        (
            user_id,
            username,
            name
        )
    )

    DB.commit()


def get_user(user_id):

    row = DB.execute(
        """
        SELECT *
        FROM users
        WHERE user_id=?
        """,
        (user_id,)
    ).fetchone()

    if not row:

        DB.execute(
            """
            INSERT INTO users
            (user_id, name)
            VALUES (?, ?)
            """,
            (
                user_id,
                "User"
            )
        )

        DB.commit()

        row = DB.execute(
            """
            SELECT *
            FROM users
            WHERE user_id=?
            """,
            (user_id,)
        ).fetchone()

    return row


def is_owner(user_id):

    return int(user_id) == OWNER_ID


def is_authed(user_id):

    return (
        is_owner(user_id)
        or
        bool(
            DB.execute(
                """
                SELECT 1
                FROM auth_users
                WHERE user_id=?
                """,
                (user_id,)
            ).fetchone()
        )
    )


# ============================================================
# CHAT HELPERS
# ============================================================

def is_group(message):

    if not message:
        return False

    if not message.chat:
        return False

    return message.chat.type in (
        ChatType.GROUP,
        ChatType.SUPERGROUP
    )


def is_admin_or_owner(message):

    if not message:
        return False

    if not message.from_user:
        return False

    if is_owner(message.from_user.id):
        return True

    if not is_group(message):
        return False

    # Actual admin check is performed asynchronously
    # by commands which need it.
    return False


def get_mention(user):

    if not user:
        return "User"

    name = html.escape(
        (
            user.first_name
            or
            "User"
        ).strip()
    )

    return (
        f'<a href="tg://user?id={user.id}">'
        f'{name}'
        f'</a>'
    )


# ============================================================
# TEXT HELPERS
# ============================================================

def clean_answer(text):

    return re.sub(
        r"[^a-z0-9]",
        "",
        (text or "").lower().strip()
    )


def jumble_word(word):

    word = word.lower()

    if len(word) < 2:
        return word

    chars = list(word)

    original = "".join(chars)

    for _ in range(20):

        random.shuffle(chars)

        result = "".join(chars)

        if result != original:
            return result

    return original


# ============================================================
# LEVEL SYSTEM
# ============================================================

def calculate_level(exp):

    step = int(
        get_global_config(
            "global_exp_per_lvl",
            500
        )
    )

    return max(
        1,
        (int(exp) // max(step, 1)) + 1
    )


def format_duration(seconds):

    seconds = max(
        0,
        int(seconds)
    )

    hours, remainder = divmod(
        seconds,
        3600
    )

    minutes, seconds = divmod(
        remainder,
        60
    )

    if hours:
        return (
            f"{hours}h "
            f"{minutes}m"
        )

    if minutes:
        return (
            f"{minutes}m "
            f"{seconds}s"
        )

    return f"{seconds}s"


# ============================================================
# SETTINGS
# ============================================================

def get_settings(chat_id):

    row = DB.execute(
        """
        SELECT *
        FROM settings
        WHERE chat_id=?
        """,
        (chat_id,)
    ).fetchone()

    if not row:

        DB.execute(
            """
            INSERT INTO settings
            (chat_id)
            VALUES (?)
            """,
            (chat_id,)
        )

        DB.commit()

        row = DB.execute(
            """
            SELECT *
            FROM settings
            WHERE chat_id=?
            """,
            (chat_id,)
        ).fetchone()

    return row


# ============================================================
# IMAGE HELPERS
# ============================================================

def get_font(size=44):

    candidates = [
        "/usr/share/fonts/truetype/dejavu/"
        "DejaVuSans-Bold.ttf",

        "/usr/share/fonts/truetype/liberation2/"
        "LiberationSans-Bold.ttf",
    ]

    for path in candidates:

        if os.path.exists(path):

            return ImageFont.truetype(
                path,
                size
            )

    return ImageFont.load_default()


def make_puzzle_image(
    jumbled,
    mode_tag="JUMBLE",
    puzzle_id="",
    exp_val=0,
    is_event=False
):

    img = Image.new(
        "RGB",
        (1100, 500),
        "white"
    )

    draw = ImageDraw.Draw(img)

    title_font = get_font(52)

    word_font = get_font(78)

    small_font = get_font(30)


    draw.text(
        (40, 35),
        mode_tag,
        font=title_font,
        fill="black"
    )


    bbox = draw.textbbox(
        (0, 0),
        jumbled.upper(),
        font=word_font
    )

    width = bbox[2] - bbox[0]

    height = bbox[3] - bbox[1]


    draw.text(
        (
            (1100 - width) / 2,
            170
        ),
        jumbled.upper(),
        font=word_font,
        fill="black"
    )


    draw.text(
        (40, 420),
        (
            f"Puzzle: {puzzle_id}   "
            f"EXP: {exp_val}"
        ),
        font=small_font,
        fill="black"
    )


    output = io.BytesIO()

    output.name = "puzzle.jpg"

    img.save(
        output,
        "JPEG",
        quality=92
    )

    output.seek(0)

    return output


# ============================================================
# DELETE HELPERS
# ============================================================

async def delete_after(
    message,
    seconds
):

    await asyncio.sleep(seconds)

    try:
        await message.delete()
    except Exception:
        pass


async def safe_delete_and_unpin(
    chat_id,
    message_id
):

    try:
        await app.unpin_chat_message(
            chat_id,
            message_id
        )
    except Exception:
        pass

    try:
        await app.delete_messages(
            chat_id,
            message_id
        )
    except Exception:
        pass


# ============================================================
# WORD SELECTION
# ============================================================

def choose_word(
    chat_id,
    difficulty
):

    if difficulty not in (
        "easy",
        "medium",
        "hard"
    ):
        difficulty = "medium"


    rows = DB.execute(
        """
        SELECT word
        FROM custom_words
        WHERE chat_id=?
        AND difficulty=?
        """,
        (
            chat_id,
            difficulty
        )
    ).fetchall()


    custom_words = [
        row["word"]
        for row in rows
    ]


    banks = {
        "easy": DEFAULT_EASY,
        "medium": DEFAULT_MEDIUM,
        "hard": DEFAULT_HARD,
    }


    pool = list(
        dict.fromkeys(
            custom_words
            +
            banks[difficulty]
        )
    )


    used_rows = DB.execute(
        """
        SELECT word
        FROM used_words
        WHERE chat_id=?
        AND used_at>?
        """,
        (
            chat_id,
            int(time.time()) - 3600
        )
    ).fetchall()


    used = {
        row["word"]
        for row in used_rows
    }


    available = [
        word
        for word in pool
        if word not in used
    ]


    if not available:
        available = pool


    word = random.choice(
        available
    )


    DB.execute(
        """
        INSERT INTO used_words
        (
            chat_id,
            word,
            used_at
        )
        VALUES (?, ?, ?)
        """,
        (
            chat_id,
            word,
            int(time.time())
        )
    )

    DB.commit()


    return word


# ============================================================
# NORMAL GAME KEYBOARD
# ============================================================

def normal_keyboard():

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "💡 Hint",
                    callback_data="hint"
                ),
                InlineKeyboardButton(
                    "⏭ Skip",
                    callback_data="skip"
                ),
            ],
            [
                InlineKeyboardButton(
                    "🔄 New Word",
                    callback_data="newword"
                ),
                InlineKeyboardButton(
                    "🛒 Shop",
                    callback_data="open_shop_btn"
                ),
            ],
        ]
    )


# ============================================================
# FIGHT KEYBOARD
# ============================================================

def fight_keyboard():

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "💡 Hint",
                    callback_data="fight_hint"
                ),
                InlineKeyboardButton(
                    "❌ Close",
                    callback_data="close_panel"
                ),
            ]
        ]
    )

# ============================================================
# NORMAL GAME
# ============================================================

async def start_game(
    chat_id,
    difficulty="medium",
    message_or_chat=None
):

    async with LOCK:

        # Fight active hai to normal game start nahi hoga
        if chat_id in JUMBLE_FIGHT:
            return None

        # Already active puzzle
        existing = DB.execute(
            """
            SELECT *
            FROM games
            WHERE chat_id=?
            """,
            (chat_id,)
        ).fetchone()

        if existing:
            return None


        # Word select
        word = choose_word(
            chat_id,
            difficulty
        )

        # Puzzle ID
        puzzle_id = str(
            random.randint(
                100000,
                999999
            )
        )

        # Jumble
        jumbled = jumble_word(word)

        # Timing
        now = int(time.time())
        expires = now + 60

        # EXP reward
        exp_reward = int(
            get_global_config(
                f"exp_{difficulty}",
                30
            )
        )

        # Points reward
        points_reward = int(
            get_global_config(
                f"points_{difficulty}",
                20
            )
        )


        # Save game
        DB.execute(
            """
            INSERT OR REPLACE INTO games
            (
                chat_id,
                word,
                jumbled,
                difficulty,
                puzzle_id,
                started,
                expires,
                message_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chat_id,
                word,
                jumbled,
                difficulty,
                puzzle_id,
                now,
                expires,
                0
            )
        )


        # Save hint
        DB.execute(
            """
            INSERT OR REPLACE INTO puzzle_hints
            (
                chat_id,
                hint
            )
            VALUES (?, ?)
            """,
            (
                chat_id,
                word
            )
        )


        # Enable game
        DB.execute(
            """
            INSERT OR IGNORE INTO settings
            (
                chat_id
            )
            VALUES (?)
            """,
            (chat_id,)
        )

        DB.execute(
            """
            UPDATE settings
            SET is_active=1,
                default_diff=?
            WHERE chat_id=?
            """,
            (
                difficulty,
                chat_id
            )
        )

        DB.commit()


    # ========================================================
    # PUZZLE IMAGE
    # ========================================================

    image = make_puzzle_image(
        jumbled,
        f"🔤 {difficulty.upper()} JUMBLE",
        puzzle_id,
        exp_reward
    )


    # ========================================================
    # SEND PUZZLE
    # ========================================================

    try:

        sent = await app.send_photo(
            chat_id,
            image,
            caption=(
                "🔤 <b>JUMBLE PUZZLE</b>\n\n"

                f"🔀 <b>"
                f"{html.escape(jumbled.upper())}"
                f"</b>\n\n"

                f"⭐ Points: <b>"
                f"{points_reward}"
                f"</b>\n"

                f"✨ EXP: <b>"
                f"{exp_reward}"
                f"</b>\n"

                f"⏳ Time: <b>60 seconds</b>\n\n"

                "📝 Reply with the correct word!"
            ),
            reply_markup=normal_keyboard()
        )


        # Pin puzzle
        try:

            await app.pin_chat_message(
                chat_id,
                sent.id,
                disable_notification=True
            )

        except Exception:
            pass


        # Store message ID
        DB.execute(
            """
            UPDATE games
            SET message_id=?
            WHERE chat_id=?
            """,
            (
                sent.id,
                chat_id
            )
        )

        DB.commit()


        # Expiration task
        asyncio.create_task(
            expire_game(
                chat_id,
                puzzle_id,
                expires
            )
        )


        return sent


    except Exception as e:

        print(
            "start_game error:",
            e
        )

        DB.execute(
            """
            DELETE FROM games
            WHERE chat_id=?
            """,
            (chat_id,)
        )

        DB.commit()

        return None


# ============================================================
# NORMAL GAME EXPIRATION
# ============================================================

async def expire_game(
    chat_id,
    puzzle_id,
    expires
):

    wait_time = max(
        0,
        expires - int(time.time())
    )

    await asyncio.sleep(
        wait_time
    )


    row = DB.execute(
        """
        SELECT *
        FROM games
        WHERE chat_id=?
        AND puzzle_id=?
        """,
        (
            chat_id,
            puzzle_id
        )
    ).fetchone()


    if not row:
        return


    # Fight started meanwhile
    if chat_id in JUMBLE_FIGHT:
        return


    # Delete old puzzle
    if row["message_id"]:

        await safe_delete_and_unpin(
            chat_id,
            row["message_id"]
        )


    DB.execute(
        """
        DELETE FROM games
        WHERE chat_id=?
        """,
        (chat_id,)
    )

    DB.commit()


    # Start another puzzle if game is active
    settings = get_settings(
        chat_id
    )

    if (
        settings
        and settings["is_active"]
        and chat_id not in JUMBLE_FIGHT
    ):

        await asyncio.sleep(1)

        await start_game(
            chat_id,
            settings["default_diff"]
            or "medium",
            chat_id
        )


# ============================================================
# FIGHT SYSTEM
# ============================================================

def fight_text(fight):

    p1 = fight["p1"]
    p2 = fight["p2"]

    score1 = fight["scores"].get(
        p1.id,
        0
    )

    score2 = fight["scores"].get(
        p2.id,
        0
    )

    return (
        "⚔️ <b>JUMBLE FIGHT</b>\n\n"

        f"👤 {get_mention(p1)} "
        f"— <b>{score1}</b>\n"

        f"👤 {get_mention(p2)} "
        f"— <b>{score2}</b>\n\n"

        f"🎯 Round: "
        f"<b>{fight['round']}/10</b>\n\n"

        f"🔀 <b>"
        f"{html.escape(fight['jumbled'].upper())}"
        f"</b>\n\n"

        "⏳ Time: <b>15 seconds</b>\n\n"

        "⚡ First correct answer gets the round!"
    )


# ============================================================
# START NEXT FIGHT ROUND
# ============================================================

async def fight_next(
    chat_id
):

    fight = JUMBLE_FIGHT.get(
        chat_id
    )

    if not fight:
        return


    # Ten rounds completed
    if fight["round"] > 10:

        await finish_fight(
            chat_id
        )

        return


    # Select word
    word = choose_word(
        chat_id,
        fight.get(
            "difficulty",
            "medium"
        )
    )


    # Puzzle ID
    puzzle_id = str(
        random.randint(
            100000,
            999999
        )
    )


    # Update fight state
    fight["word"] = word

    fight["jumbled"] = jumble_word(
        word
    )

    fight["puzzle_id"] = puzzle_id

    fight["round_started"] = int(
        time.time()
    )

    fight["round_expires"] = (
        int(time.time())
        + 15
    )


    # Delete previous fight message
    if fight.get("message_id"):

        await safe_delete_and_unpin(
            chat_id,
            fight["message_id"]
        )


    # Send new round
    try:

        message = await app.send_message(
            chat_id,
            fight_text(fight),
            reply_markup=fight_keyboard()
        )

        fight["message_id"] = message.id

    except Exception as e:

        print(
            "fight_next error:",
            e
        )

        return


    # Timeout
    asyncio.create_task(
        fight_timeout_task(
            chat_id,
            puzzle_id
        )
    )


# ============================================================
# FIGHT ROUND TIMEOUT
# ============================================================

async def fight_timeout_task(
    chat_id,
    puzzle_id
):

    await asyncio.sleep(
        15
    )


    fight = JUMBLE_FIGHT.get(
        chat_id
    )

    if not fight:
        return


    # Different puzzle already started
    if (
        fight.get("puzzle_id")
        != puzzle_id
    ):
        return


    fight["round"] += 1


    await fight_next(
        chat_id
    )


# ============================================================
# FINISH FIGHT
# ============================================================

async def finish_fight(
    chat_id
):

    fight = JUMBLE_FIGHT.pop(
        chat_id,
        None
    )

    if not fight:
        return


    p1 = fight["p1"]
    p2 = fight["p2"]

    score1 = fight["scores"].get(
        p1.id,
        0
    )

    score2 = fight["scores"].get(
        p2.id,
        0
    )


    winner = None
    loser = None


    # --------------------------------------------------------
    # WINNER
    # --------------------------------------------------------

    if score1 > score2:

        winner = p1
        loser = p2

    elif score2 > score1:

        winner = p2
        loser = p1


    # --------------------------------------------------------
    # DRAW
    # --------------------------------------------------------

    if winner is None:

        if fight.get("message_id"):

            await safe_delete_and_unpin(
                chat_id,
                fight["message_id"]
            )

        try:

            await app.send_message(
                chat_id,
                (
                    "🤝 <b>FIGHT DRAW!</b>\n\n"

                    f"👤 {get_mention(p1)}: "
                    f"<b>{score1}</b>\n"

                    f"👤 {get_mention(p2)}: "
                    f"<b>{score2}</b>"
                )
            )

        except Exception:
            pass


    # --------------------------------------------------------
    # WIN
    # --------------------------------------------------------

    else:

        get_user(
            winner.id
        )

        get_user(
            loser.id
        )


        # Normal fight stats
        DB.execute(
            """
            UPDATE users
            SET fight_wins=fight_wins+1
            WHERE user_id=?
            """,
            (winner.id,)
        )

        DB.execute(
            """
            UPDATE users
            SET fight_losses=fight_losses+1
            WHERE user_id=?
            """,
            (loser.id,)
        )


        # ----------------------------------------------------
        # BET FIGHT
        # ----------------------------------------------------

        if fight.get("bet"):

            bet = int(
                fight["bet"]
            )

            pot = bet * 2


            # Winner receives 75%
            winner_amount = int(
                pot * 0.75
            )


            # Loser cashback 25%
            loser_cashback = int(
                pot * 0.25
            )


            DB.execute(
                """
                UPDATE users
                SET points=points+?
                WHERE user_id=?
                """,
                (
                    winner_amount,
                    winner.id
                )
            )


            DB.execute(
                """
                UPDATE users
                SET points=points+?
                WHERE user_id=?
                """,
                (
                    loser_cashback,
                    loser.id
                )
            )


            DB.execute(
                """
                UPDATE users
                SET bet_wins=bet_wins+1
                WHERE user_id=?
                """,
                (winner.id,)
            )


            DB.execute(
                """
                UPDATE users
                SET bet_losses=bet_losses+1
                WHERE user_id=?
                """,
                (loser.id,)
            )


            # Rebet information
            REBET_LOBBY[
                loser.id
            ] = {
                "loser": loser,
                "winner": winner,
                "original_bet": bet,
                "chat_id": chat_id
            }


        DB.commit()


        # Delete fight message
        if fight.get("message_id"):

            await safe_delete_and_unpin(
                chat_id,
                fight["message_id"]
            )


        # Result
        if fight.get("bet"):

            bet = int(
                fight["bet"]
            )

            pot = bet * 2

            winner_amount = int(
                pot * 0.75
            )

            cashback = int(
                pot * 0.25
            )


            result_text = (
                "🏆 <b>BET FIGHT OVER!</b>\n\n"

                f"🥇 Winner: "
                f"{get_mention(winner)}\n"

                f"💀 Loser: "
                f"{get_mention(loser)}\n\n"

                f"📊 Score: "
                f"<b>{max(score1, score2)}</b>"
                f" - "
                f"<b>{min(score1, score2)}</b>\n\n"

                f"💰 Winner received: "
                f"<b>{winner_amount}</b>\n"

                f"💸 Loser cashback: "
                f"<b>{cashback}</b>"
            )

        else:

            result_text = (
                "🏆 <b>FIGHT OVER!</b>\n\n"

                f"🥇 Winner: "
                f"{get_mention(winner)}\n"

                f"💀 Loser: "
                f"{get_mention(loser)}\n\n"

                f"📊 Score: "
                f"<b>{max(score1, score2)}</b>"
                f" - "
                f"<b>{min(score1, score2)}</b>"
            )


        try:

            await app.send_message(
                chat_id,
                result_text
            )

        except Exception:
            pass


    # --------------------------------------------------------
    # Resume normal game
    # --------------------------------------------------------

    await asyncio.sleep(
        2
    )


    settings = get_settings(
        chat_id
    )

    if (
        settings
        and settings["is_active"]
    ):

        await start_game(
            chat_id,
            settings["default_diff"]
            or "medium",
            chat_id
        )


# ============================================================
# CREATE FIGHT
# ============================================================

async def create_fight(
    chat_id,
    challenger,
    opponent,
    bet=0,
    difficulty="medium"
):

    if chat_id in JUMBLE_FIGHT:
        return False


    bet = int(
        bet or 0
    )


    # --------------------------------------------------------
    # Validate bet
    # --------------------------------------------------------

    if bet:

        challenger_user = get_user(
            challenger.id
        )

        opponent_user = get_user(
            opponent.id
        )


        if (
            challenger_user["points"]
            < bet
        ):

            return False


        if (
            opponent_user["points"]
            < bet
        ):

            return False


        # Take stake
        DB.execute(
            """
            UPDATE users
            SET points=points-?
            WHERE user_id=?
            """,
            (
                bet,
                challenger.id
            )
        )


        DB.execute(
            """
            UPDATE users
            SET points=points-?
            WHERE user_id=?
            """,
            (
                bet,
                opponent.id
            )
        )


        DB.commit()


    # --------------------------------------------------------
    # Fight state
    # --------------------------------------------------------

    JUMBLE_FIGHT[
        chat_id
    ] = {
        "chat_id": chat_id,

        "p1": challenger,

        "p2": opponent,

        "scores": defaultdict(int),

        "round": 1,

        "difficulty": difficulty,

        "bet": bet,

        "message_id": None,
    }


    await fight_next(
        chat_id
    )

    return True


# ============================================================
# SHOP / LEVEL SYSTEM
# ============================================================

def build_shop_text_and_kb(
    user_id
):

    user = get_user(
        user_id
    )

    now = int(
        time.time()
    )


    point_left = max(
        0,
        int(
            user["point_card_exp"]
            or 0
        ) - now
    )


    level_left = max(
        0,
        int(
            user["level_card_exp"]
            or 0
        ) - now
    )


    point_price = int(
        get_global_config(
            "card_point_price",
            500
        )
    )


    level_price = int(
        get_global_config(
            "card_level_price",
            600
        )
    )


    instant_cost = int(
        get_global_config(
            "shop_exp_cost",
            1000
        )
    )


    instant_reward = int(
        get_global_config(
            "shop_exp_reward",
            500
        )
    )


    text = (
        "🛒 <b>JUMBLE SHOP</b>\n\n"

        f"⭐ Points: "
        f"<b>{user['points']}</b>\n"

        f"✨ EXP: "
        f"<b>{user['exp']}</b>\n"

        f"🏅 Level: "
        f"<b>{user['level']}</b>\n\n"

        f"💎 Point Booster: "
        f"<b>{format_duration(point_left)}</b>\n"

        f"⚡ Level Booster: "
        f"<b>{format_duration(level_left)}</b>\n\n"

        "━━━━━━━━━━━━━━━━━━\n\n"

        f"💎 <b>2x Point Booster</b>\n"
        f"💰 Cost: <b>{point_price}</b> points\n"
        f"⏱ Duration: "
        f"{get_global_config('card_point_hrs', 3)} hours\n\n"

        f"⚡ <b>2x EXP Booster</b>\n"
        f"💰 Cost: <b>{level_price}</b> points\n"
        f"⏱ Duration: "
        f"{get_global_config('card_level_hrs', 3)} hours\n\n"

        f"✨ <b>Instant EXP Pack</b>\n"
        f"💰 Cost: <b>{instant_cost}</b> points\n"
        f"🎁 Reward: <b>{instant_reward}</b> EXP"
    )


    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    (
                        f"💎 2x Points "
                        f"({point_price})"
                    ),
                    callback_data="buy_card_point"
                )
            ],

            [
                InlineKeyboardButton(
                    (
                        f"⚡ 2x EXP "
                        f"({level_price})"
                    ),
                    callback_data="buy_card_level"
                )
            ],

            [
                InlineKeyboardButton(
                    "✨ Instant EXP",
                    callback_data="buy_instant_exp"
                ),

                InlineKeyboardButton(
                    "🔄 Refresh",
                    callback_data="refresh_shop"
                )
            ],

            [
                InlineKeyboardButton(
                    "❌ Close",
                    callback_data="close_panel"
                )
            ]
        ]
    )


    return (
        text,
        keyboard
    )


# ============================================================
# EVENT SYSTEM
# ============================================================

async def send_event_to_chat(
    chat_id,
    event
):

    # Do not interrupt fights
    if chat_id in JUMBLE_FIGHT:
        return False


    # Existing event
    current = DB.execute(
        """
        SELECT *
        FROM event_games
        WHERE chat_id=?
        AND solved=0
        """,
        (chat_id,)
    ).fetchone()


    if current:
        return False


    # Select event word
    word = event["word"]


    if word == "random":

        if EVENT_WORDS:

            word = random.choice(
                list(EVENT_WORDS)
            )

        else:

            word = random.choice(
                DEFAULT_EVENT
            )


    word = clean_answer(
        word
    )


    # Puzzle
    puzzle_id = str(
        random.randint(
            100000,
            999999
        )
    )

    now = int(
        time.time()
    )

    expires = now + 120

    jumbled = jumble_word(
        word
    )


    # Save event game
    DB.execute(
        """
        INSERT OR REPLACE INTO event_games
        (
            chat_id,
            event_id,
            word,
            hint,
            puzzle_id,
            started,
            expires,
            message_id,
            solved
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
        """,
        (
            chat_id,
            event["id"],
            word,
            event["hint"] or "",
            puzzle_id,
            now,
            expires,
            0
        )
    )

    DB.commit()


    # Event image
    image = make_puzzle_image(
        jumbled,
        "🎉 EVENT JUMBLE",
        puzzle_id,
        int(
            event["reward_exp"]
        ),
        True
    )


    try:

        message = await app.send_photo(
            chat_id,
            image,
            caption=(
                f"🎉 <b>"
                f"{html.escape(event['title'])}"
                f"</b>\n\n"

                f"🔀 <b>"
                f"{html.escape(jumbled.upper())}"
                f"</b>\n\n"

                f"⭐ Reward: "
                f"<b>{event['reward_stars']}</b>\n"

                f"✨ EXP: "
                f"<b>{event['reward_exp']}</b>\n"

                f"💡 Hint: "
                f"<b>"
                f"{html.escape(event['hint'] or 'No hint')}"
                f"</b>\n\n"

                "📝 Reply with the answer!"
            )
        )


        DB.execute(
            """
            UPDATE event_games
            SET message_id=?
            WHERE chat_id=?
            """,
            (
                message.id,
                chat_id
            )
        )

        DB.commit()


        asyncio.create_task(
            expire_event_game(
                chat_id,
                puzzle_id,
                expires
            )
        )


        return True


    except (
        UserIsBlocked,
        PeerIdInvalid,
        ChannelPrivate,
        ChannelInvalid,
        RPCError
    ):

        DB.execute(
            """
            DELETE FROM event_games
            WHERE chat_id=?
            """,
            (chat_id,)
        )

        DB.commit()

        return False


    except Exception as e:

        print(
            "send_event_to_chat:",
            e
        )

        DB.execute(
            """
            DELETE FROM event_games
            WHERE chat_id=?
            """,
            (chat_id,)
        )

        DB.commit()

        return False


# ============================================================
# EVENT GAME EXPIRATION
# ============================================================

async def expire_event_game(
    chat_id,
    puzzle_id,
    expires
):

    wait_time = max(
        0,
        expires - int(time.time())
    )

    await asyncio.sleep(
        wait_time
    )


    row = DB.execute(
        """
        SELECT *
        FROM event_games
        WHERE chat_id=?
        AND puzzle_id=?
        """,
        (
            chat_id,
            puzzle_id
        )
    ).fetchone()


    if not row:
        return


    if row["solved"]:
        return


    if row["message_id"]:

        await safe_delete_and_unpin(
            chat_id,
            row["message_id"]
        )


    DB.execute(
        """
        DELETE FROM event_games
        WHERE chat_id=?
        """,
        (chat_id,)
    )

    DB.commit()


# ============================================================
# EVENT SCHEDULER
# ============================================================

async def event_scheduler_loop():

    await asyncio.sleep(
        5
    )


    while True:

        try:

            now = int(
                time.time()
            )


            events = DB.execute(
                """
                SELECT *
                FROM events_bank
                WHERE is_active=1
                AND next_run<=?
                """,
                (now,)
            ).fetchall()


            for event in events:

                settings_rows = DB.execute(
                    """
                    SELECT *
                    FROM settings
                    WHERE event_active=1
                    """
                ).fetchall()


                for settings in settings_rows:

                    chat_id = settings["chat_id"]

                    target_type = (
                        event["target_type"]
                        or "group"
                    )


                    # Group events
                    if (
                        target_type
                        in ("group", "both")
                    ):

                        if chat_id < 0:

                            await send_event_to_chat(
                                chat_id,
                                event
                            )


                    # DM target support
                    # Users that have interacted with the bot
                    if (
                        target_type
                        in ("dm", "both")
                    ):

                        users = DB.execute(
                            """
                            SELECT user_id
                            FROM users
                            WHERE is_private=0
                            """
                        ).fetchall()


                        for user in users:

                            try:

                                await send_event_to_chat(
                                    user["user_id"],
                                    event
                                )

                            except (
                                UserIsBlocked,
                                PeerIdInvalid,
                                ChannelPrivate,
                                ChannelInvalid,
                                RPCError
                            ):

                                pass

                            except Exception:

                                pass


                # Schedule next run
                interval = max(
                    1,
                    float(
                        event["interval_hrs"]
                        or 24
                    )
                )


                DB.execute(
                    """
                    UPDATE events_bank
                    SET next_run=?
                    WHERE id=?
                    """,
                    (
                        int(
                            now
                            +
                            interval * 3600
                        ),
                        event["id"]
                    )
                )

                DB.commit()


        except Exception as e:

            print(
                "event_scheduler_loop:",
                e
            )


        await asyncio.sleep(
            30
        )

# ============================================================
# BACKUP SYSTEM
# ============================================================

async def auto_backup_task():

    while True:

        await asyncio.sleep(
            6 * 3600
        )

        try:

            if os.path.exists(DB_FILE):

                await app.send_document(
                    OWNER_ID,
                    DB_FILE,
                    caption=(
                        "🗄 <b>Automatic Database Backup</b>\n"
                        "⏱ Backup interval: 6 hours"
                    )
                )

        except Exception as e:

            print(
                "auto_backup_task:",
                e
            )


# ============================================================
# RESUME ACTIVE GAMES
# ============================================================

async def resume_all_active_games():

    await asyncio.sleep(
        3
    )


    rows = DB.execute(
        """
        SELECT
            chat_id,
            default_diff
        FROM settings
        WHERE is_active=1
        AND chat_id != 0
        """
    ).fetchall()


    for row in rows:

        chat_id = row["chat_id"]

        difficulty = (
            row["default_diff"]
            or "medium"
        )


        try:

            # Remove stale game
            DB.execute(
                """
                DELETE FROM games
                WHERE chat_id=?
                """,
                (chat_id,)
            )

            DB.commit()


            # Start fresh puzzle
            await start_game(
                chat_id,
                difficulty,
                chat_id
            )


            await asyncio.sleep(
                0.8
            )


        except Exception as e:

            print(
                "resume game error:",
                chat_id,
                e
            )


# ============================================================
# BOT ADDED TO GROUP
# ============================================================

@app.on_chat_member_updated()
async def bot_added_handler(
    _,
    update: ChatMemberUpdated
):

    try:

        if not update.new_chat_member:
            return


        member = update.new_chat_member


        if not member.user:
            return


        if not member.user.is_bot:
            return


        me = await app.get_me()


        if member.user.id != me.id:
            return


        chat_id = update.chat.id


        adder_id = (
            update.from_user.id
            if update.from_user
            else 0
        )


        DB.execute(
            """
            INSERT OR REPLACE INTO group_adders
            (
                chat_id,
                user_id
            )
            VALUES (?, ?)
            """,
            (
                chat_id,
                adder_id
            )
        )


        DB.execute(
            """
            INSERT OR IGNORE INTO settings
            (
                chat_id
            )
            VALUES (?)
            """,
            (chat_id,)
        )


        DB.commit()


        try:

            await app.send_message(
                chat_id,
                (
                    "🎮 <b>Advanced Jumble Bot Added!</b>\n\n"
                    "Use /jumble to start the game.\n"
                    "Use /help to see all commands."
                )
            )

        except Exception:
            pass


    except Exception as e:

        print(
            "bot_added_handler:",
            e
        )


# ============================================================
# ALL BOT COMMANDS
# ============================================================

ALL_BOT_COMMANDS = {

    # Basic
    "start",
    "help",

    # Stats
    "stats",
    "stat",
    "mystats",
    "score",

    # Leaderboard
    "leaderboard",
    "top",
    "rank",
    "lb",

    # Settings
    "settings",
    "setting",

    # Points / hints
    "setpoints",
    "sethint",
    "setdaily",
    "setbonus",

    # Rewards
    "daily",
    "bonus",
    "addstar",
    "addpoints",
    "deductstar",
    "deductpoints",
    "removestar",

    # Privacy
    "private",
    "public",

    # Git / update
    "update",
    "gitpull",

    # Authorization
    "auth",
    "unauth",
    "authlist",

    # Words
    "addword",
    "addwords",
    "word",
    "words",
    "delword",
    "delallword",
    "delallwords",
    "clearword",
    "clearwords",

    # Games
    "jumble",
    "jumblefight",
    "fight",
    "rapido",
    "jumblebetfight",
    "betfight",

    # Database
    "backup",
    "dbbackup",
    "getdb",

    # Shop
    "shop",
    "store",

    # Events
    "setevent",
    "cancel",
    "setglobalexp",
    "storeexpprize",
    "setexp",
    "eventlist",
    "events",
    "startevent",
    "stopevent",
    "addeventword",
    "deleventword",
    "eventwords",

    # Cards
    "setcard",

    # Misc
    "calculate",
    "log",
}


# ============================================================
# /START
# ============================================================

@app.on_message(
    filters.command("start")
)
async def start_cmd(
    _,
    message
):

    ensure_user(
        message.from_user
    )


    keyboard_rows = []


    if ADD_ME_URL:

        keyboard_rows.append(
            [
                InlineKeyboardButton(
                    "➕ Add Me To Group",
                    url=ADD_ME_URL
                )
            ]
        )


    if SUPPORT_GC:

        keyboard_rows.append(
            [
                InlineKeyboardButton(
                    "💬 Support",
                    url=SUPPORT_GC
                )
            ]
        )


    keyboard = (
        InlineKeyboardMarkup(
            keyboard_rows
        )
        if keyboard_rows
        else None
    )


    text = (
        "🎮 <b>ADVANCED JUMBLE BOT</b>\n\n"

        "🔤 <b>Jumble Game</b>\n"
        "⚔️ <b>Jumble Fight</b>\n"
        "💰 <b>Bet Fight</b>\n"
        "🏅 <b>Level & EXP</b>\n"
        "🛒 <b>Shop & Boosters</b>\n"
        "🎉 <b>Events</b>\n"
        "🏆 <b>Leaderboard</b>\n\n"

        "Use <code>/help</code> to see all commands."
    )


    try:

        if START_IMG:

            await message.reply_photo(
                START_IMG,
                caption=text,
                reply_markup=keyboard
            )

        else:

            await message.reply_text(
                text,
                reply_markup=keyboard
            )

    except Exception:

        await message.reply_text(
            text,
            reply_markup=keyboard
        )


# ============================================================
# /HELP
# ============================================================

@app.on_message(
    filters.command("help")
)
async def help_cmd(
    _,
    message
):

    await message.reply_text(
        """
📚 <b>AVAILABLE COMMANDS</b>

━━━━━━━━━━━━━━━━━━

🎮 <b>GAME</b>

/jumble
/jumble easy
/jumble medium
/jumble hard

⚔️ <b>FIGHT</b>

/fight
/jumblefight
/rapido

💰 <b>BET FIGHT</b>

/betfight amount
/jumblebetfight amount

📊 <b>STATS</b>

/stats
/stat
/mystats
/score

🏆 <b>LEADERBOARD</b>

/leaderboard
/top
/rank
/lb

🎁 <b>REWARDS</b>

/daily
/bonus

🛒 <b>SHOP</b>

/shop
/store

📝 <b>WORDS</b>

/addword
/addwords
/words
/word
/delword
/delallword
/delallwords
/clearword
/clearwords

⚙️ <b>SETTINGS</b>

/settings
/setting
/setpoints
/sethint
/setdaily
/setbonus

🎉 <b>EVENTS</b>

/setevent
/eventlist
/events
/startevent
/stopevent
/addeventword
/deleventword
/eventwords
/cancel

🏅 <b>EXP</b>

/setexp
/setglobalexp
/calculate
/storeexpprize
/setcard

🔐 <b>OWNER</b>

/auth
/unauth
/authlist
/backup
/dbbackup
/getdb
/log
"""
    )


# ============================================================
# /STATS
# ============================================================

@app.on_message(
    filters.command(
        [
            "stats",
            "stat",
            "mystats",
            "score"
        ]
    )
)
async def stats_cmd(
    _,
    message
):

    ensure_user(
        message.from_user
    )


    user = get_user(
        message.from_user.id
    )


    exp_per_level = int(
        get_global_config(
            "global_exp_per_lvl",
            500
        )
    )


    current_level_exp = (
        int(user["exp"])
        %
        exp_per_level
    )


    now = int(
        time.time()
    )


    point_booster = max(
        0,
        int(
            user["point_card_exp"]
            or 0
        )
        -
        now
    )


    exp_booster = max(
        0,
        int(
            user["level_card_exp"]
            or 0
        )
        -
        now
    )


    await message.reply_text(
        (
            "📊 <b>YOUR STATISTICS</b>\n\n"

            f"👤 {get_mention(message.from_user)}\n\n"

            f"⭐ Points: "
            f"<b>{user['points']}</b>\n"

            f"✨ EXP: "
            f"<b>{user['exp']}</b>\n"

            f"🏅 Level: "
            f"<b>{user['level']}</b>\n"

            f"📈 Level EXP: "
            f"<b>{current_level_exp}/"
            f"{exp_per_level}</b>\n\n"

            f"🧩 Solved: "
            f"<b>{user['solved']}</b>\n"

            f"🔥 Streak: "
            f"<b>{user['streak']}</b>\n"

            f"🔥 Best Streak: "
            f"<b>{user['best_streak']}</b>\n\n"

            f"⚔️ Fight W/L: "
            f"<b>{user['fight_wins']}/"
            f"{user['fight_losses']}</b>\n"

            f"💰 Bet W/L: "
            f"<b>{user['bet_wins']}/"
            f"{user['bet_losses']}</b>\n\n"

            f"💎 Point Booster: "
            f"<b>{format_duration(point_booster)}</b>\n"

            f"⚡ EXP Booster: "
            f"<b>{format_duration(exp_booster)}</b>"
        )
    )


# ============================================================
# /LEADERBOARD
# ============================================================

@app.on_message(
    filters.command(
        [
            "leaderboard",
            "top",
            "rank",
            "lb"
        ]
    )
)
async def leaderboard_cmd(
    _,
    message
):

    rows = DB.execute(
        """
        SELECT *
        FROM users
        ORDER BY points DESC,
                 exp DESC
        LIMIT 10
        """
    ).fetchall()


    if not rows:

        return await message.reply_text(
            "🏆 No players yet."
        )


    medals = [
        "🥇",
        "🥈",
        "🥉"
    ]


    lines = [
        "🏆 <b>TOP PLAYERS</b>\n"
    ]


    for index, row in enumerate(
        rows,
        1
    ):

        if index <= 3:

            rank_icon = medals[
                index - 1
            ]

        else:

            rank_icon = (
                f"<b>{index}.</b>"
            )


        name = (
            row["name"]
            or
            row["username"]
            or
            str(row["user_id"])
        )


        name = html.escape(
            name
        )


        lines.append(
            (
                f"{rank_icon} "
                f"<b>{name}</b>\n"
                f"   ⭐ {row['points']} "
                f"| ✨ {row['exp']} "
                f"| 🏅 Lv.{row['level']}"
            )
        )


    await message.reply_text(
        "\n".join(lines)
    )


# ============================================================
# /JUMBLE
# ============================================================

@app.on_message(
    filters.command("jumble")
)
async def jumble_cmd(
    _,
    message
):

    ensure_user(
        message.from_user
    )


    if not is_group(message):

        return await message.reply_text(
            "❌ Jumble games are available in groups only."
        )


    difficulty = "medium"


    if len(
        message.command
    ) > 1:

        requested = (
            message.command[1]
            .lower()
        )


        if requested in (
            "easy",
            "medium",
            "hard"
        ):

            difficulty = requested


    settings = get_settings(
        message.chat.id
    )


    # Activate group
    DB.execute(
        """
        UPDATE settings
        SET
            is_active=1,
            default_diff=?
        WHERE chat_id=?
        """,
        (
            difficulty,
            message.chat.id
        )
    )


    DB.commit()


    # Don't interrupt fight
    if message.chat.id in JUMBLE_FIGHT:

        return await message.reply_text(
            "⚔️ A fight is currently active."
        )


    # Check existing puzzle
    active = DB.execute(
        """
        SELECT 1
        FROM games
        WHERE chat_id=?
        """,
        (
            message.chat.id,
        )
    ).fetchone()


    if active:

        return await message.reply_text(
            "🔤 A jumble is already active."
        )


    await start_game(
        message.chat.id,
        difficulty,
        message.chat.id
    )


# ============================================================
# FIGHT COMMAND
# ============================================================

@app.on_message(
    filters.command(
        [
            "fight",
            "jumblefight",
            "rapido"
        ]
    )
)
async def fight_cmd(
    _,
    message
):

    if not is_group(message):

        return await message.reply_text(
            "❌ Use fights inside a group."
        )


    if not message.from_user:

        return


    target = None


    # --------------------------------------------------------
    # Reply target
    # --------------------------------------------------------

    if (
        message.reply_to_message
        and
        message.reply_to_message.from_user
    ):

        target = (
            message.reply_to_message
            .from_user
        )


    # --------------------------------------------------------
    # Username / ID target
    # --------------------------------------------------------

    if (
        not target
        and
        len(message.command) > 1
    ):

        target_text = (
            message.command[1]
        )

        try:

            target = await app.get_users(
                target_text
            )

        except Exception:

            target = None


    if not target:

        return await message.reply_text(
            (
                "⚔️ <b>Fight Usage</b>\n\n"
                "Reply to a user with /fight\n"
                "or use /fight @username"
            )
        )


    if target.id == message.from_user.id:

        return await message.reply_text(
            "❌ You cannot fight yourself."
        )


    if target.is_bot:

        return await message.reply_text(
            "❌ You cannot fight a bot."
        )


    if message.chat.id in JUMBLE_FIGHT:

        return await message.reply_text(
            "⚔️ A fight is already running."
        )


    # --------------------------------------------------------
    # Challenge
    # --------------------------------------------------------

    FIGHT_LOBBY[
        message.from_user.id
    ] = {

        "chat_id":
            message.chat.id,

        "challenger":
            message.from_user,

        "opponent":
            target,

        "bet":
            0,
    }


    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Accept",
                    callback_data=(
                        f"f_accept:"
                        f"{message.from_user.id}"
                    )
                ),

                InlineKeyboardButton(
                    "❌ Decline",
                    callback_data=(
                        f"f_decline:"
                        f"{message.from_user.id}"
                    )
                )
            ]
        ]
    )


    await message.reply_text(
        (
            "⚔️ <b>JUMBLE FIGHT CHALLENGE</b>\n\n"

            f"👤 Challenger: "
            f"{get_mention(message.from_user)}\n"

            f"🎯 Opponent: "
            f"{get_mention(target)}\n\n"

            "🔥 10 rounds\n"
            "⏱ 15 seconds per round"
        ),
        reply_markup=keyboard
    )


# ============================================================
# BET FIGHT COMMAND
# ============================================================

@app.on_message(
    filters.command(
        [
            "betfight",
            "jumblebetfight"
        ]
    )
)
async def betfight_cmd(
    _,
    message
):

    if not is_group(message):

        return await message.reply_text(
            "❌ Use bet fights inside groups."
        )


    if not message.from_user:

        return


    # --------------------------------------------------------
    # Bet amount
    # --------------------------------------------------------

    if (
        len(message.command)
        < 2
        or
        not message.command[1].isdigit()
    ):

        return await message.reply_text(
            (
                "💰 <b>Bet Fight Usage</b>\n\n"
                "Reply to opponent:\n"
                "<code>/betfight 100</code>"
            )
        )


    bet = int(
        message.command[1]
    )


    if bet <= 0:

        return await message.reply_text(
            "❌ Bet must be greater than zero."
        )


    # --------------------------------------------------------
    # Target
    # --------------------------------------------------------

    if (
        not message.reply_to_message
        or
        not message.reply_to_message.from_user
    ):

        return await message.reply_text(
            "❌ Reply to the opponent's message."
        )


    target = (
        message.reply_to_message
        .from_user
    )


    if target.id == message.from_user.id:

        return await message.reply_text(
            "❌ You cannot bet against yourself."
        )


    if target.is_bot:

        return await message.reply_text(
            "❌ Bots cannot participate."
        )


    # --------------------------------------------------------
    # Balance checks
    # --------------------------------------------------------

    challenger = get_user(
        message.from_user.id
    )

    opponent = get_user(
        target.id
    )


    if challenger["points"] < bet:

        return await message.reply_text(
            (
                "❌ You don't have enough "
                "points for this bet."
            )
        )


    if opponent["points"] < bet:

        return await message.reply_text(
            (
                "❌ Opponent doesn't have "
                "enough points."
            )
        )


    if message.chat.id in JUMBLE_FIGHT:

        return await message.reply_text(
            "⚔️ A fight is already active."
        )


    # --------------------------------------------------------
    # Lobby
    # --------------------------------------------------------

    FIGHT_LOBBY[
        message.from_user.id
    ] = {

        "chat_id":
            message.chat.id,

        "challenger":
            message.from_user,

        "opponent":
            target,

        "bet":
            bet,
    }


    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "💰 Accept Bet",
                    callback_data=(
                        f"f_accept:"
                        f"{message.from_user.id}"
                    )
                ),

                InlineKeyboardButton(
                    "❌ Decline",
                    callback_data=(
                        f"f_decline:"
                        f"{message.from_user.id}"
                    )
                )
            ]
        ]
    )


    await message.reply_text(
        (
            "💰 <b>BET FIGHT CHALLENGE</b>\n\n"

            f"👤 "
            f"{get_mention(message.from_user)}\n"

            f"⚔️ "
            f"{get_mention(target)}\n\n"

            f"💵 Stake: "
            f"<b>{bet}</b> points each\n"

            "🏆 Winner gets 75% of pot\n"
            "💸 Loser gets 25% cashback"
        ),
        reply_markup=keyboard
    )

# ============================================================
# SHOP COMMAND
# ============================================================

@app.on_message(
    filters.command(
        [
            "shop",
            "store"
        ]
    )
)
async def shop_cmd(
    _,
    message
):

    ensure_user(
        message.from_user
    )

    text, keyboard = (
        build_shop_text_and_kb(
            message.from_user.id
        )
    )

    await message.reply_text(
        text,
        reply_markup=keyboard
    )


# ============================================================
# DAILY REWARD
# ============================================================

@app.on_message(
    filters.command("daily")
)
async def daily_cmd(
    _,
    message
):

    ensure_user(
        message.from_user
    )

    user = get_user(
        message.from_user.id
    )

    now = int(
        time.time()
    )

    last_daily = int(
        user["last_daily"]
        or 0
    )


    # 24 hour cooldown
    if (
        now - last_daily
        < 86400
    ):

        remaining = (
            86400
            -
            (
                now
                -
                last_daily
            )
        )

        return await message.reply_text(
            (
                "⏳ <b>Daily Already Claimed!</b>\n\n"
                f"Try again in "
                f"<b>{format_duration(remaining)}</b>."
            )
        )


    reward = int(
        get_global_config(
            "daily_points",
            50
        )
    )


    DB.execute(
        """
        UPDATE users
        SET
            points=points+?,
            last_daily=?
        WHERE user_id=?
        """,
        (
            reward,
            now,
            message.from_user.id
        )
    )


    DB.execute(
        """
        INSERT INTO score_history
        (
            user_id,
            chat_id,
            points,
            timestamp,
            tag
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            message.from_user.id,
            message.chat.id,
            reward,
            now,
            "daily"
        )
    )


    DB.commit()


    await message.reply_text(
        (
            "🎁 <b>DAILY REWARD</b>\n\n"
            f"⭐ You received "
            f"<b>+{reward}</b> points!\n\n"
            "⏰ Come back tomorrow for another reward."
        )
    )


# ============================================================
# GROUP BONUS
# ============================================================

@app.on_message(
    filters.command("bonus")
)
async def bonus_cmd(
    _,
    message
):

    if not is_group(message):

        return await message.reply_text(
            "❌ Group only."
        )


    ensure_user(
        message.from_user
    )


    row = DB.execute(
        """
        SELECT claimed
        FROM group_bonus
        WHERE chat_id=?
        """,
        (
            message.chat.id,
        )
    ).fetchone()


    if row and row["claimed"]:

        return await message.reply_text(
            "❌ The group bonus has already been claimed."
        )


    reward = int(
        get_global_config(
            "bonus_points",
            100
        )
    )


    DB.execute(
        """
        INSERT OR REPLACE INTO group_bonus
        (
            chat_id,
            claimed
        )
        VALUES (?, 1)
        """,
        (
            message.chat.id,
        )
    )


    DB.execute(
        """
        UPDATE users
        SET points=points+?
        WHERE user_id=?
        """,
        (
            reward,
            message.from_user.id
        )
    )


    DB.execute(
        """
        INSERT INTO score_history
        (
            user_id,
            chat_id,
            points,
            timestamp,
            tag
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            message.from_user.id,
            message.chat.id,
            reward,
            int(time.time()),
            "bonus"
        )
    )


    DB.commit()


    await message.reply_text(
        (
            "🎁 <b>GROUP BONUS</b>\n\n"
            f"👤 {get_mention(message.from_user)}\n"
            f"⭐ Reward: <b>+{reward}</b> points!"
        )
    )


# ============================================================
# ADD POINTS / STARS
# ============================================================

async def resolve_target_and_amount(
    message
):

    target = None
    amount = None


    # --------------------------------------------------------
    # Amount from command
    # --------------------------------------------------------

    args = message.command[1:]


    for arg in args:

        if arg.lstrip("-").isdigit():

            amount = int(arg)

            break


    # --------------------------------------------------------
    # Target from reply
    # --------------------------------------------------------

    if (
        message.reply_to_message
        and
        message.reply_to_message.from_user
    ):

        target = (
            message.reply_to_message
            .from_user
        )


    # --------------------------------------------------------
    # Target from username
    # --------------------------------------------------------

    if not target:

        for arg in args:

            if (
                not arg.lstrip("-").isdigit()
                and
                arg.startswith("@")
            ):

                try:

                    target = await app.get_users(
                        arg
                    )

                except Exception:

                    pass

                break


    # --------------------------------------------------------
    # Target from numeric ID
    # --------------------------------------------------------

    if not target:

        for arg in args:

            if arg.isdigit():

                try:

                    target = await app.get_users(
                        int(arg)
                    )

                except Exception:

                    pass

                if target:
                    break


    return (
        target,
        amount
    )


# ============================================================
# ADD POINTS
# ============================================================

@app.on_message(
    filters.command(
        [
            "addstar",
            "addpoints"
        ]
    )
)
async def addpoints_cmd(
    _,
    message
):

    if not is_owner(
        message.from_user.id
    ):

        return await message.reply_text(
            "❌ Owner only."
        )


    target, amount = (
        await resolve_target_and_amount(
            message
        )
    )


    if not target or amount is None:

        return await message.reply_text(
            (
                "Usage:\n"
                "<code>/addpoints @user 100</code>\n"
                "or reply to user with "
                "<code>/addpoints 100</code>"
            )
        )


    ensure_user(
        target
    )


    DB.execute(
        """
        UPDATE users
        SET points=points+?
        WHERE user_id=?
        """,
        (
            amount,
            target.id
        )
    )


    DB.execute(
        """
        INSERT INTO score_history
        (
            user_id,
            chat_id,
            points,
            timestamp,
            tag
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            target.id,
            message.chat.id,
            amount,
            int(time.time()),
            "admin"
        )
    )


    DB.commit()


    await message.reply_text(
        (
            "✅ Added points.\n\n"
            f"👤 {get_mention(target)}\n"
            f"⭐ <b>+{amount}</b> points"
        )
    )


# ============================================================
# DEDUCT POINTS
# ============================================================

@app.on_message(
    filters.command(
        [
            "deductstar",
            "deductpoints",
            "removestar"
        ]
    )
)
async def deductpoints_cmd(
    _,
    message
):

    if not is_owner(
        message.from_user.id
    ):

        return await message.reply_text(
            "❌ Owner only."
        )


    target, amount = (
        await resolve_target_and_amount(
            message
        )
    )


    if not target or amount is None:

        return await message.reply_text(
            (
                "Usage:\n"
                "<code>/deductpoints @user 100</code>"
            )
        )


    ensure_user(
        target
    )


    DB.execute(
        """
        UPDATE users
        SET points=MAX(0, points-?)
        WHERE user_id=?
        """,
        (
            amount,
            target.id
        )
    )


    DB.execute(
        """
        INSERT INTO score_history
        (
            user_id,
            chat_id,
            points,
            timestamp,
            tag
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            target.id,
            message.chat.id,
            -amount,
            int(time.time()),
            "admin"
        )
    )


    DB.commit()


    await message.reply_text(
        (
            "✅ Points deducted.\n\n"
            f"👤 {get_mention(target)}\n"
            f"⭐ <b>-{amount}</b> points"
        )
    )


# ============================================================
# SETTINGS
# ============================================================

@app.on_message(
    filters.command(
        [
            "settings",
            "setting"
        ]
    )
)
async def settings_cmd(
    _,
    message
):

    if not is_group(message):

        return await message.reply_text(
            "❌ This command can only be used in groups."
        )


    settings = get_settings(
        message.chat.id
    )


    event_status = (
        "🟢 ON"
        if settings["event_active"]
        else
        "🔴 OFF"
    )


    game_status = (
        "🟢 ON"
        if settings["is_active"]
        else
        "🔴 OFF"
    )


    auto_delete = (
        "🟢 ON"
        if settings["auto_delete"]
        else
        "🔴 OFF"
    )


    await message.reply_text(
        (
            "⚙️ <b>GROUP SETTINGS</b>\n\n"

            f"🎮 Game: <b>{game_status}</b>\n"
            f"🎯 Difficulty: "
            f"<b>{settings['default_diff']}</b>\n"
            f"🗑 Auto Delete: "
            f"<b>{auto_delete}</b>\n"
            f"🎉 Events: "
            f"<b>{event_status}</b>"
        )
    )


# ============================================================
# SET POINTS
# ============================================================

@app.on_message(
    filters.command("setpoints")
)
async def setpoints_cmd(
    _,
    message
):

    if not is_owner(
        message.from_user.id
    ):

        return await message.reply_text(
            "❌ Owner only."
        )


    if len(
        message.command
    ) < 3:

        return await message.reply_text(
            (
                "Usage:\n"
                "<code>/setpoints easy 10</code>\n"
                "<code>/setpoints medium 20</code>\n"
                "<code>/setpoints hard 30</code>"
            )
        )


    difficulty = (
        message.command[1]
        .lower()
    )


    if difficulty not in (
        "easy",
        "medium",
        "hard"
    ):

        return await message.reply_text(
            "❌ Difficulty must be easy, medium or hard."
        )


    try:

        value = int(
            message.command[2]
        )

    except ValueError:

        return await message.reply_text(
            "❌ Enter a valid number."
        )


    set_global_config(
        f"points_{difficulty}",
        value
    )


    await message.reply_text(
        (
            f"✅ <b>{difficulty.title()}</b> "
            f"points set to <b>{value}</b>."
        )
    )


# ============================================================
# SET HINT
# ============================================================

@app.on_message(
    filters.command("sethint")
)
async def sethint_cmd(
    _,
    message
):

    if not is_owner(
        message.from_user.id
    ):

        return await message.reply_text(
            "❌ Owner only."
        )


    if len(
        message.command
    ) < 3:

        return await message.reply_text(
            (
                "Usage:\n"
                "<code>/sethint easy 3</code>"
            )
        )


    difficulty = (
        message.command[1]
        .lower()
    )


    if difficulty not in (
        "easy",
        "medium",
        "hard"
    ):

        return await message.reply_text(
            "❌ Invalid difficulty."
        )


    try:

        value = int(
            message.command[2]
        )

    except ValueError:

        return await message.reply_text(
            "❌ Invalid number."
        )


    set_global_config(
        f"hints_{difficulty}",
        value
    )


    await message.reply_text(
        (
            f"💡 <b>{difficulty.title()}</b> "
            f"hints set to <b>{value}</b>."
        )
    )


# ============================================================
# SET DAILY
# ============================================================

@app.on_message(
    filters.command("setdaily")
)
async def setdaily_cmd(
    _,
    message
):

    if not is_owner(
        message.from_user.id
    ):

        return await message.reply_text(
            "❌ Owner only."
        )


    if len(
        message.command
    ) < 2:

        return await message.reply_text(
            "Usage: /setdaily 100"
        )


    try:

        value = int(
            message.command[1]
        )

    except ValueError:

        return await message.reply_text(
            "❌ Invalid number."
        )


    set_global_config(
        "daily_points",
        value
    )


    await message.reply_text(
        f"✅ Daily reward set to <b>{value}</b>."
    )


# ============================================================
# SET BONUS
# ============================================================

@app.on_message(
    filters.command("setbonus")
)
async def setbonus_cmd(
    _,
    message
):

    if not is_owner(
        message.from_user.id
    ):

        return await message.reply_text(
            "❌ Owner only."
        )


    if len(
        message.command
    ) < 2:

        return await message.reply_text(
            "Usage: /setbonus 100"
        )


    try:

        value = int(
            message.command[1]
        )

    except ValueError:

        return await message.reply_text(
            "❌ Invalid number."
        )


    set_global_config(
        "bonus_points",
        value
    )


    await message.reply_text(
        f"✅ Group bonus set to <b>{value}</b>."
    )


# ============================================================
# PRIVATE MODE
# ============================================================

@app.on_message(
    filters.command("private")
)
async def private_cmd(
    _,
    message
):

    ensure_user(
        message.from_user
    )


    DB.execute(
        """
        UPDATE users
        SET is_private=1
        WHERE user_id=?
        """,
        (
            message.from_user.id,
        )
    )


    DB.commit()


    await message.reply_text(
        (
            "🔒 <b>Private Mode Enabled</b>\n\n"
            "Your profile is now marked private."
        )
    )


# ============================================================
# PUBLIC MODE
# ============================================================

@app.on_message(
    filters.command("public")
)
async def public_cmd(
    _,
    message
):

    ensure_user(
        message.from_user
    )


    DB.execute(
        """
        UPDATE users
        SET is_private=0
        WHERE user_id=?
        """,
        (
            message.from_user.id,
        )
    )


    DB.commit()


    await message.reply_text(
        (
            "🌐 <b>Public Mode Enabled</b>\n\n"
            "Your profile is now public."
        )
    )


# ============================================================
# AUTH USER
# ============================================================

@app.on_message(
    filters.command("auth")
)
async def auth_cmd(
    _,
    message
):

    if not is_owner(
        message.from_user.id
    ):

        return await message.reply_text(
            "❌ Owner only."
        )


    target = None


    if (
        message.reply_to_message
        and
        message.reply_to_message.from_user
    ):

        target = (
            message.reply_to_message
            .from_user
        )


    if (
        not target
        and
        len(message.command) > 1
    ):

        try:

            target = await app.get_users(
                message.command[1]
            )

        except Exception:

            pass


    if not target:

        return await message.reply_text(
            "Reply to a user or use /auth @username."
        )


    DB.execute(
        """
        INSERT OR IGNORE INTO auth_users
        (user_id)
        VALUES (?)
        """,
        (
            target.id,
        )
    )


    DB.commit()


    await message.reply_text(
        (
            "🔐 <b>User Authorized</b>\n\n"
            f"👤 {get_mention(target)}"
        )
    )


# ============================================================
# UNAUTH USER
# ============================================================

@app.on_message(
    filters.command("unauth")
)
async def unauth_cmd(
    _,
    message
):

    if not is_owner(
        message.from_user.id
    ):

        return await message.reply_text(
            "❌ Owner only."
        )


    target = None


    if (
        message.reply_to_message
        and
        message.reply_to_message.from_user
    ):

        target = (
            message.reply_to_message
            .from_user
        )


    if (
        not target
        and
        len(message.command) > 1
    ):

        try:

            target = await app.get_users(
                message.command[1]
            )

        except Exception:

            pass


    if not target:

        return await message.reply_text(
            "Reply to a user or use /unauth @username."
        )


    DB.execute(
        """
        DELETE FROM auth_users
        WHERE user_id=?
        """,
        (
            target.id,
        )
    )


    DB.commit()


    await message.reply_text(
        (
            "🔓 <b>User Unauthorized</b>\n\n"
            f"👤 {get_mention(target)}"
        )
    )


# ============================================================
# AUTH LIST
# ============================================================

@app.on_message(
    filters.command("authlist")
)
async def authlist_cmd(
    _,
    message
):

    if not is_owner(
        message.from_user.id
    ):

        return


    rows = DB.execute(
        """
        SELECT user_id
        FROM auth_users
        ORDER BY user_id
        """
    ).fetchall()


    if not rows:

        return await message.reply_text(
            "🔐 No authorized users."
        )


    lines = [
        "🔐 <b>AUTHORIZED USERS</b>\n"
    ]


    for index, row in enumerate(
        rows,
        1
    ):

        lines.append(
            f"{index}. <code>{row['user_id']}</code>"
        )


    await message.reply_text(
        "\n".join(lines)
    )


# ============================================================
# ADD CUSTOM WORDS
# ============================================================

async def process_bulk_words_addition(
    message,
    difficulty="medium"
):

    if not is_owner(
        message.from_user.id
    ):

        return await message.reply_text(
            "❌ Owner only."
        )


    if not is_group(message):

        return await message.reply_text(
            "❌ Group only."
        )


    if not message.text:

        return


    parts = message.text.split(
        maxsplit=1
    )


    if len(parts) < 2:

        return await message.reply_text(
            (
                "Usage:\n"
                "<code>/addword word1 word2 word3</code>"
            )
        )


    raw_words = re.split(
        r"[\s,]+",
        parts[1].strip()
    )


    added = 0


    for raw_word in raw_words:

        word = clean_answer(
            raw_word
        )


        if not word:
            continue


        DB.execute(
            """
            INSERT INTO custom_words
            (
                chat_id,
                word,
                difficulty
            )
            VALUES (?, ?, ?)
            """,
            (
                message.chat.id,
                word,
                difficulty
            )
        )


        added += 1


    DB.commit()


    await message.reply_text(
        (
            "✅ <b>Words Added</b>\n\n"
            f"📝 Added: <b>{added}</b>\n"
            f"🎯 Difficulty: <b>{difficulty}</b>"
        )
    )


# ============================================================
# ADD WORD COMMANDS
# ============================================================

@app.on_message(
    filters.command(
        [
            "addword",
            "addwords"
        ]
    )
)
async def addword_cmd(
    _,
    message
):

    await process_bulk_words_addition(
        message,
        "medium"
    )


# ============================================================
# WORD LIST
# ============================================================

@app.on_message(
    filters.command(
        [
            "word",
            "words"
        ]
    )
)
async def words_cmd(
    _,
    message
):

    if not is_group(message):

        return await message.reply_text(
            "❌ Group only."
        )


    rows = DB.execute(
        """
        SELECT word, difficulty
        FROM custom_words
        WHERE chat_id=?
        ORDER BY difficulty, word
        """,
        (
            message.chat.id,
        )
    ).fetchall()


    if not rows:

        return await message.reply_text(
            "📝 No custom words added."
        )


    lines = [
        "📝 <b>CUSTOM WORDS</b>\n"
    ]


    for row in rows:

        lines.append(
            (
                f"• <code>{html.escape(row['word'])}</code>"
                f" — {row['difficulty']}"
            )
        )


    # Telegram message limit protection
    text = "\n".join(
        lines
    )


    if len(text) > 4000:

        text = (
            text[:3900]
            +
            "\n\n…"
        )


    await message.reply_text(
        text
    )


# ============================================================
# DELETE WORD
# ============================================================

@app.on_message(
    filters.command("delword")
)
async def delword_cmd(
    _,
    message
):

    if not is_owner(
        message.from_user.id
    ):

        return await message.reply_text(
            "❌ Owner only."
        )


    if not is_group(message):

        return await message.reply_text(
            "❌ Group only."
        )


    if len(
        message.command
    ) < 2:

        return await message.reply_text(
            "Usage: /delword word"
        )


    word = clean_answer(
        message.command[1]
    )


    DB.execute(
        """
        DELETE FROM custom_words
        WHERE chat_id=?
        AND word=?
        """,
        (
            message.chat.id,
            word
        )
    )


    DB.commit()


    await message.reply_text(
        (
            "🗑 <b>Word Deleted</b>\n\n"
            f"Word: <code>{html.escape(word)}</code>"
        )
    )


# ============================================================
# DELETE ALL WORDS
# ============================================================

@app.on_message(
    filters.command(
        [
            "delallword",
            "delallwords",
            "clearword",
            "clearwords"
        ]
    )
)
async def clearwords_cmd(
    _,
    message
):

    if not is_owner(
        message.from_user.id
    ):

        return await message.reply_text(
            "❌ Owner only."
        )


    if not is_group(message):

        return await message.reply_text(
            "❌ Group only."
        )


    DB.execute(
        """
        DELETE FROM custom_words
        WHERE chat_id=?
        """,
        (
            message.chat.id,
        )
    )


    DB.commit()


    await message.reply_text(
        "🗑 <b>All custom words cleared.</b>"
    )


# ============================================================
# OWNER BACKUP COMMANDS
# ============================================================

@app.on_message(
    filters.command(
        [
            "backup",
            "dbbackup",
            "getdb"
        ]
    )
)
async def backup_cmd(
    _,
    message
):

    if not is_owner(
        message.from_user.id
    ):

        return await message.reply_text(
            "❌ Owner only."
        )


    if not os.path.exists(
        DB_FILE
    ):

        return await message.reply_text(
            "❌ Database file not found."
        )


    try:

        await message.reply_document(
            DB_FILE,
            caption=(
                "🗄 <b>Jumble Database Backup</b>"
            )
        )

    except Exception as e:

        await message.reply_text(
            f"❌ Backup failed: {html.escape(str(e))}"
        )


# ============================================================
# EVENT LIST
# ============================================================

@app.on_message(
    filters.command(
        [
            "eventlist",
            "events"
        ]
    )
)
async def eventlist_cmd(
    _,
    message
):

    rows = DB.execute(
        """
        SELECT *
        FROM events_bank
        ORDER BY id DESC
        """
    ).fetchall()


    if not rows:

        return await message.reply_text(
            "🎉 <b>No events configured.</b>"
        )


    lines = [
        "🎉 <b>EVENT LIST</b>\n"
    ]


    for event in rows:

        status = (
            "🟢 ACTIVE"
            if event["is_active"]
            else
            "🔴 STOPPED"
        )


        lines.append(
            (
                f"🆔 <b>#{event['id']}</b>\n"
                f"📌 {html.escape(event['title'])}\n"
                f"📊 {status}\n"
                f"⭐ Reward: {event['reward_stars']}\n"
                f"✨ EXP: {event['reward_exp']}\n"
                f"⏱ Every: {event['interval_hrs']}h\n"
                f"🎯 Target: {event['target_type']}\n"
            )
        )


    text = "\n".join(
        lines
    )


    if len(text) > 4000:

        text = text[:3900] + "\n…"


    await message.reply_text(
        text
    )


# ============================================================
# START EVENT
# ============================================================

@app.on_message(
    filters.command("startevent")
)
async def startevent_cmd(
    _,
    message
):

    if not is_owner(
        message.from_user.id
    ):

        return await message.reply_text(
            "❌ Owner only."
        )


    if len(
        message.command
    ) < 2:

        return await message.reply_text(
            "Usage: /startevent event_id"
        )


    try:

        event_id = int(
            message.command[1]
        )

    except ValueError:

        return await message.reply_text(
            "❌ Invalid event ID."
        )


    event = DB.execute(
        """
        SELECT *
        FROM events_bank
        WHERE id=?
        """,
        (
            event_id,
        )
    ).fetchone()


    if not event:

        return await message.reply_text(
            "❌ Event not found."
        )


    DB.execute(
        """
        UPDATE events_bank
        SET
            is_active=1,
            next_run=?
        WHERE id=?
        """,
        (
            int(time.time()),
            event_id
        )
    )


    DB.commit()


    await message.reply_text(
        (
            "▶️ <b>Event Started</b>\n\n"
            f"🆔 Event ID: <b>{event_id}</b>"
        )
    )


# ============================================================
# STOP EVENT
# ============================================================

@app.on_message(
    filters.command("stopevent")
)
async def stopevent_cmd(
    _,
    message
):

    if not is_owner(
        message.from_user.id
    ):

        return await message.reply_text(
            "❌ Owner only."
        )


    if len(
        message.command
    ) < 2:

        return await message.reply_text(
            "Usage: /stopevent event_id"
        )


    try:

        event_id = int(
            message.command[1]
        )

    except ValueError:

        return await message.reply_text(
            "❌ Invalid event ID."
        )


    DB.execute(
        """
        UPDATE events_bank
        SET is_active=0
        WHERE id=?
        """,
        (
            event_id,
        )
    )


    DB.commit()


    await message.reply_text(
        (
            "⏹ <b>Event Stopped</b>\n\n"
            f"🆔 Event ID: <b>{event_id}</b>"
        )
    )


# ============================================================
# ADD EVENT WORD
# ============================================================

@app.on_message(
    filters.command("addeventword")
)
async def addeventword_cmd(
    _,
    message
):

    if not is_owner(
        message.from_user.id
    ):

        return await message.reply_text(
            "❌ Owner only."
        )


    if len(
        message.command
    ) < 2:

        return await message.reply_text(
            "Usage: /addeventword word"
        )


    word = clean_answer(
        message.command[1]
    )


    if not word:

        return await message.reply_text(
            "❌ Invalid word."
        )


    hint = "Event word"


    if len(
        message.command
    ) >= 3:

        hint = " ".join(
            message.command[2:]
        )


    DB.execute(
        """
        INSERT OR REPLACE INTO event_words
        (
            word,
            hint
        )
        VALUES (?, ?)
        """,
        (
            word,
            hint
        )
    )


    DB.commit()


    EVENT_WORDS.add(
        word
    )


    await message.reply_text(
        (
            "🎉 <b>Event Word Added</b>\n\n"
            f"📝 Word: <code>{html.escape(word)}</code>\n"
            f"💡 Hint: {html.escape(hint)}"
        )
    )


# ============================================================
# DELETE EVENT WORD
# ============================================================

@app.on_message(
    filters.command("deleventword")
)
async def deleventword_cmd(
    _,
    message
):

    if not is_owner(
        message.from_user.id
    ):

        return await message.reply_text(
            "❌ Owner only."
        )


    if len(
        message.command
    ) < 2:

        return await message.reply_text(
            "Usage: /deleventword word"
        )


    word = clean_answer(
        message.command[1]
    )


    DB.execute(
        """
        DELETE FROM event_words
        WHERE word=?
        """,
        (
            word,
        )
    )


    DB.commit()


    EVENT_WORDS.discard(
        word
    )


    await message.reply_text(
        (
            "🗑 <b>Event Word Deleted</b>\n\n"
            f"<code>{html.escape(word)}</code>"
        )
    )


# ============================================================
# EVENT WORD LIST
# ============================================================

@app.on_message(
    filters.command("eventwords")
)
async def eventwords_cmd(
    _,
    message
):

    rows = DB.execute(
        """
        SELECT word, hint
        FROM event_words
        ORDER BY word
        """
    ).fetchall()


    if not rows:

        return await message.reply_text(
            "🎉 No event words."
        )


    lines = [
        "🎉 <b>EVENT WORDS</b>\n"
    ]


    for row in rows:

        lines.append(
            (
                f"• <code>"
                f"{html.escape(row['word'])}"
                f"</code>"
                f" — "
                f"{html.escape(row['hint'] or '')}"
            )
        )


    text = "\n".join(
        lines
    )


    if len(text) > 4000:

        text = text[:3900] + "\n…"


    await message.reply_text(
        text
    )


# ============================================================
# SET EXP
# ============================================================

@app.on_message(
    filters.command("setexp")
)
async def setexp_cmd(
    _,
    message
):

    if not is_owner(
        message.from_user.id
    ):

        return await message.reply_text(
            "❌ Owner only."
        )


    if len(
        message.command
    ) < 3:

        return await message.reply_text(
            (
                "Usage:\n"
                "<code>/setexp easy 15</code>\n"
                "<code>/setexp medium 30</code>\n"
                "<code>/setexp hard 50</code>"
            )
        )


    difficulty = (
        message.command[1]
        .lower()
    )


    if difficulty not in (
        "easy",
        "medium",
        "hard"
    ):

        return await message.reply_text(
            "❌ Invalid difficulty."
        )


    try:

        exp = int(
            message.command[2]
        )

    except ValueError:

        return await message.reply_text(
            "❌ Invalid EXP amount."
        )


    set_global_config(
        f"exp_{difficulty}",
        exp
    )


    await message.reply_text(
        (
            f"✨ <b>{difficulty.title()}</b> "
            f"EXP reward set to "
            f"<b>{exp}</b>."
        )
    )


# ============================================================
# GLOBAL EXP PER LEVEL
# ============================================================

@app.on_message(
    filters.command("setglobalexp")
)
async def setglobalexp_cmd(
    _,
    message
):

    if not is_owner(
        message.from_user.id
    ):

        return await message.reply_text(
            "❌ Owner only."
        )


    if len(
        message.command
    ) < 2:

        return await message.reply_text(
            "Usage: /setglobalexp 500"
        )


    try:

        value = int(
            message.command[1]
        )

    except ValueError:

        return await message.reply_text(
            "❌ Invalid number."
        )


    if value <= 0:

        return await message.reply_text(
            "❌ EXP per level must be greater than 0."
        )


    set_global_config(
        "global_exp_per_lvl",
        value
    )


    # Recalculate all existing levels
    rows = DB.execute(
        """
        SELECT user_id, exp
        FROM users
        """
    ).fetchall()


    for row in rows:

        DB.execute(
            """
            UPDATE users
            SET level=?
            WHERE user_id=?
            """,
            (
                calculate_level(
                    row["exp"]
                ),
                row["user_id"]
            )
        )


    DB.commit()


    await message.reply_text(
        (
            "🏅 <b>Global EXP Level System Updated</b>\n\n"
            f"✨ EXP required per level: "
            f"<b>{value}</b>"
        )
    )


# ============================================================
# STORE EXP PRIZE
# ============================================================

@app.on_message(
    filters.command("storeexpprize")
)
async def storeexpprize_cmd(
    _,
    message
):

    if not is_owner(
        message.from_user.id
    ):

        return await message.reply_text(
            "❌ Owner only."
        )


    if len(
        message.command
    ) < 3:

        return await message.reply_text(
            (
                "Usage:\n"
                "<code>/storeexpprize cost reward</code>"
            )
        )


    try:

        cost = int(
            message.command[1]
        )

        reward = int(
            message.command[2]
        )

    except ValueError:

        return await message.reply_text(
            "❌ Invalid numbers."
        )


    set_global_config(
        "shop_exp_cost",
        cost
    )


    set_global_config(
        "shop_exp_reward",
        reward
    )


    await message.reply_text(
        (
            "🛒 <b>EXP SHOP UPDATED</b>\n\n"
            f"💰 Cost: <b>{cost}</b>\n"
            f"✨ Reward: <b>{reward}</b> EXP"
        )
    )


# ============================================================
# SET CARD
# ============================================================

@app.on_message(
    filters.command("setcard")
)
async def setcard_cmd(
    _,
    message
):

    if not is_owner(
        message.from_user.id
    ):

        return await message.reply_text(
            "❌ Owner only."
        )


    if len(
        message.command
    ) < 4:

        return await message.reply_text(
            (
                "Usage:\n"
                "<code>/setcard point price hours level</code>\n"
                "<code>/setcard level price hours level</code>"
            )
        )


    card_type = (
        message.command[1]
        .lower()
    )


    try:

        price = int(
            message.command[2]
        )

        hours = int(
            message.command[3]
        )

        required_level = (
            int(message.command[4])
            if len(message.command) >= 5
            else 1
        )

    except ValueError:

        return await message.reply_text(
            "❌ Invalid values."
        )


    if card_type == "point":

        set_global_config(
            "card_point_price",
            price
        )

        set_global_config(
            "card_point_hrs",
            hours
        )

        set_global_config(
            "card_point_req_lvl",
            required_level
        )


    elif card_type == "level":

        set_global_config(
            "card_level_price",
            price
        )

        set_global_config(
            "card_level_hrs",
            hours
        )

        set_global_config(
            "card_level_req_lvl",
            required_level
        )


    else:

        return await message.reply_text(
            "❌ Card type must be <code>point</code> or <code>level</code>."
        )


    await message.reply_text(
        (
            "💳 <b>Card Updated</b>\n\n"
            f"Type: <b>{card_type}</b>\n"
            f"Price: <b>{price}</b>\n"
            f"Duration: <b>{hours} hours</b>\n"
            f"Required Level: <b>{required_level}</b>"
        )
    )

# ============================================================
# PART 5/5 — EVENT WIZARD, CALCULATOR, LOG, TEXT HANDLER,
# CALLBACK ROUTER & MAIN
# ============================================================


# ------------------------------------------------------------
# EVENT SETUP WIZARD
# ------------------------------------------------------------

@app.on_message(filters.command(["setevent", "eventsetup"]))
async def setevent_cmd(client, message):
    if not is_owner(message.from_user.id):
        return await message.reply_text("❌ Only the bot owner can use this command.")

    chat_id = message.chat.id

    EVENT_WIZARD[chat_id] = {
        "step": "target",
        "target": None,
        "name": None,
        "description": None,
        "reward": None,
        "duration": None,
        "words": [],
    }

    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "👥 Current Chat",
                    callback_data=f"ev_target_chat:{chat_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    "❌ Cancel",
                    callback_data=f"ev_cancel_wizard:{chat_id}",
                )
            ],
        ]
    )

    await message.reply_text(
        "🎉 **Event Setup Wizard**\n\n"
        "Step 1/6 — Where should this event run?\n\n"
        "You can use the current chat or send the target chat ID.",
        reply_markup=kb,
    )


@app.on_message(filters.command("cancel"))
async def cancel_cmd(client, message):
    chat_id = message.chat.id

    if chat_id in EVENT_WIZARD:
        EVENT_WIZARD.pop(chat_id, None)
        return await message.reply_text("❌ Event setup cancelled.")

    if chat_id in JUMBLE_FIGHT:
        await finish_fight(chat_id, None, cancelled=True)
        return await message.reply_text("❌ Active fight cancelled.")

    game = DB.execute(
        "SELECT puzzle_id FROM games WHERE chat_id=?",
        (chat_id,),
    ).fetchone()

    if game:
        DB.execute(
            "DELETE FROM games WHERE chat_id=?",
            (chat_id,),
        )
        DB.execute(
            "DELETE FROM puzzle_hints WHERE puzzle_id=?",
            (game["puzzle_id"],),
        )
        DB.commit()

        try:
            await safe_delete_and_unpin(chat_id, game["puzzle_id"])
        except Exception:
            pass

        return await message.reply_text("❌ Current puzzle cancelled.")

    await message.reply_text("ℹ️ Nothing is currently running.")


# ------------------------------------------------------------
# EVENT WIZARD PROCESSOR
# ------------------------------------------------------------

async def process_event_wizard(message):
    chat_id = message.chat.id
    uid = message.from_user.id

    if not is_owner(uid):
        return False

    wizard = EVENT_WIZARD.get(chat_id)

    if not wizard:
        return False

    text = (message.text or "").strip()

    if text.startswith("/"):
        return False

    step = wizard.get("step")

    # STEP 1 — TARGET
    if step == "target":
        try:
            target = int(text)
        except ValueError:
            await message.reply_text(
                "❌ Invalid chat ID.\n\n"
                "Send a numeric Telegram chat ID."
            )
            return True

        wizard["target"] = target
        wizard["step"] = "name"

        await message.reply_text(
            "✅ Target saved.\n\n"
            "Step 2/6 — Send the **event name**."
        )
        return True

    # STEP 2 — NAME
    if step == "name":
        wizard["name"] = text[:100]
        wizard["step"] = "description"

        await message.reply_text(
            "✅ Event name saved.\n\n"
            "Step 3/6 — Send the **event description**."
        )
        return True

    # STEP 3 — DESCRIPTION
    if step == "description":
        wizard["description"] = text[:1000]
        wizard["step"] = "reward"

        await message.reply_text(
            "✅ Description saved.\n\n"
            "Step 4/6 — Send the **reward points**."
        )
        return True

    # STEP 4 — REWARD
    if step == "reward":
        try:
            reward = int(text)
            if reward < 0:
                raise ValueError
        except ValueError:
            await message.reply_text(
                "❌ Invalid reward.\n\n"
                "Send a positive number."
            )
            return True

        wizard["reward"] = reward
        wizard["step"] = "duration"

        await message.reply_text(
            "✅ Reward saved.\n\n"
            "Step 5/6 — Send event duration in minutes.\n"
            "Example: `60`"
        )
        return True

    # STEP 5 — DURATION
    if step == "duration":
        try:
            duration = int(text)
            if duration <= 0:
                raise ValueError
        except ValueError:
            await message.reply_text(
                "❌ Invalid duration.\n\n"
                "Send minutes greater than 0."
            )
            return True

        wizard["duration"] = duration
        wizard["step"] = "words"

        await message.reply_text(
            "✅ Duration saved.\n\n"
            "Step 6/6 — Send event words.\n\n"
            "Send one word per line, or comma-separated.\n"
            "Example:\n"
            "`apple`\n"
            "`banana`\n"
            "`orange`"
        )
        return True

    # STEP 6 — WORDS
    if step == "words":
        raw_words = re.split(r"[\n,]+", text)

        words = []
        for word in raw_words:
            word = clean_answer(word)
            if word and len(word) >= 2:
                words.append(word)

        words = list(dict.fromkeys(words))

        if not words:
            await message.reply_text(
                "❌ No valid words found.\n"
                "Please send at least one word."
            )
            return True

        wizard["words"] = words

        target = wizard["target"]
        name = wizard["name"]
        description = wizard["description"]
        reward = wizard["reward"]
        duration = wizard["duration"]

        try:
            DB.execute(
                """
                INSERT INTO events
                (chat_id,name,description,reward_stars,duration_minutes,
                 active,created_by,created_at)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    target,
                    name,
                    description,
                    reward,
                    duration,
                    1,
                    uid,
                    int(time.time()),
                ),
            )

            event_id = DB.execute(
                "SELECT last_insert_rowid() AS id"
            ).fetchone()["id"]

            for word in words:
                DB.execute(
                    """
                    INSERT OR IGNORE INTO event_words(event_id,word)
                    VALUES (?,?)
                    """,
                    (event_id, word),
                )

            DB.commit()

            EVENT_WIZARD.pop(chat_id, None)

            await message.reply_text(
                "🎉 **Event Created Successfully!**\n\n"
                f"🆔 Event ID: `{event_id}`\n"
                f"📛 Name: **{html.escape(name)}**\n"
                f"🎁 Reward: `{reward}` points\n"
                f"⏱ Duration: `{duration}` minutes\n"
                f"📝 Words: `{len(words)}`\n"
                f"🎯 Target: `{target}`",
                parse_mode=ParseMode.MARKDOWN,
            )

        except Exception as e:
            DB.rollback()
            await message.reply_text(
                f"❌ Failed to create event:\n`{html.escape(str(e))}`"
            )

        return True

    return False


# ------------------------------------------------------------
# CALCULATOR
# ------------------------------------------------------------

@app.on_message(filters.command(["calculate", "calc"]))
async def calculate_cmd(client, message):
    expression = message.text.split(maxsplit=1)

    if len(expression) < 2:
        return await message.reply_text(
            "🧮 **Calculator**\n\n"
            "Usage:\n"
            "`/calculate 25*4+10`\n"
            "`/calc 100/5`"
        )

    expr = expression[1].strip()

    if len(expr) > 100:
        return await message.reply_text("❌ Expression is too long.")

    if not re.fullmatch(r"[0-9+\-*/().% \^]+", expr):
        return await message.reply_text(
            "❌ Invalid characters in expression."
        )

    try:
        safe_expr = expr.replace("^", "**")

        result = eval(
            safe_expr,
            {
                "__builtins__": {},
            },
            {},
        )

        if isinstance(result, float):
            if result.is_integer():
                result = int(result)
            else:
                result = round(result, 8)

        await message.reply_text(
            f"🧮 `{html.escape(expr)}` = **{result}**"
        )

    except ZeroDivisionError:
        await message.reply_text("❌ Cannot divide by zero.")

    except Exception:
        await message.reply_text(
            "❌ Could not calculate that expression."
        )


# ------------------------------------------------------------
# LOG COMMAND
# ------------------------------------------------------------

@app.on_message(filters.command(["log", "logs"]))
async def log_cmd(client, message):
    if not is_owner(message.from_user.id):
        return await message.reply_text(
            "❌ Only the owner can view logs."
        )

    rows = DB.execute(
        """
        SELECT id,user_id,chat_id,action,points,created_at
        FROM score_history
        ORDER BY id DESC
        LIMIT 20
        """
    ).fetchall()

    if not rows:
        return await message.reply_text(
            "📜 No score logs available."
        )

    lines = ["📜 **Recent Score Logs**", ""]

    for row in rows:
        created = row["created_at"]

        try:
            created_text = time.strftime(
                "%d-%m-%Y %H:%M",
                time.localtime(created),
            )
        except Exception:
            created_text = str(created)

        lines.append(
            f"#{row['id']} | "
            f"User `{row['user_id']}` | "
            f"Chat `{row['chat_id']}`\n"
            f"Action: `{row['action']}` | "
            f"Points: `{row['points']}`\n"
            f"🕒 {created_text}"
        )

    await message.reply_text(
        "\n\n".join(lines)
    )


# ------------------------------------------------------------
# SETTINGS PANEL
# ------------------------------------------------------------

async def show_settings_panel(chat_id, message=None):
    settings = get_settings(chat_id)

    difficulty = settings.get("difficulty", "medium")
    active = int(settings.get("active", 1))
    auto_next = int(settings.get("auto_next", 1))
    event_active = int(settings.get("event_active", 1))

    text = (
        "⚙️ **Jumble Settings**\n\n"
        f"🎯 Difficulty: **{difficulty.title()}**\n"
        f"🎮 Game: **{'ON' if active else 'OFF'}**\n"
        f"🔄 Auto Next: **{'ON' if auto_next else 'OFF'}**\n"
        f"🎉 Events: **{'ON' if event_active else 'OFF'}**"
    )

    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🟢 Easy",
                    callback_data=f"set_diff_easy:{chat_id}",
                ),
                InlineKeyboardButton(
                    "🟡 Medium",
                    callback_data=f"set_diff_medium:{chat_id}",
                ),
                InlineKeyboardButton(
                    "🔴 Hard",
                    callback_data=f"set_diff_hard:{chat_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🎮 Game ON",
                    callback_data=f"set_active_on:{chat_id}",
                ),
                InlineKeyboardButton(
                    "🛑 Game OFF",
                    callback_data=f"set_active_off:{chat_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🔄 Auto ON",
                    callback_data=f"set_auto_on:{chat_id}",
                ),
                InlineKeyboardButton(
                    "⏹ Auto OFF",
                    callback_data=f"set_auto_off:{chat_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🎉 Events ON",
                    callback_data=f"set_event_on:{chat_id}",
                ),
                InlineKeyboardButton(
                    "🚫 Events OFF",
                    callback_data=f"set_event_off:{chat_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    "❌ Close",
                    callback_data="close_panel",
                )
            ],
        ]
    )

    if message:
        return await message.reply_text(
            text,
            reply_markup=kb,
        )

    try:
        return await app.send_message(
            chat_id,
            text,
            reply_markup=kb,
        )
    except Exception:
        return None


# ------------------------------------------------------------
# LEADERBOARD / WORD BROWSER PAGINATION CALLBACK HELPERS
# ------------------------------------------------------------

async def leaderboard_page(query, page):
    try:
        page = max(0, int(page))
    except Exception:
        page = 0

    limit = 10
    offset = page * limit

    rows = DB.execute(
        """
        SELECT user_id,points,level,exp
        FROM users
        ORDER BY points DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    ).fetchall()

    if not rows:
        return await query.answer(
            "No more players.",
            show_alert=True,
        )

    lines = [f"🏆 **Leaderboard — Page {page + 1}**", ""]

    for i, row in enumerate(rows, offset + 1):
        lines.append(
            f"{i}. `{row['user_id']}` — "
            f"⭐ {row['points']} | "
            f"Lv.{row['level']} | "
            f"XP {row['exp']}"
        )

    buttons = []

    nav = []

    if page > 0:
        nav.append(
            InlineKeyboardButton(
                "⬅️",
                callback_data=f"lb_{page - 1}",
            )
        )

    nav.append(
        InlineKeyboardButton(
            "🔄",
            callback_data=f"lb_{page}",
        )
    )

    if len(rows) == limit:
        nav.append(
            InlineKeyboardButton(
                "➡️",
                callback_data=f"lb_{page + 1}",
            )
        )

    buttons.append(nav)

    buttons.append(
        [
            InlineKeyboardButton(
                "❌ Close",
                callback_data="close_panel",
            )
        ]
    )

    try:
        await query.message.edit_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(buttons),
        )
    except MessageNotModified:
        pass


async def words_browser_page(query, page=0):
    try:
        page = max(0, int(page))
    except Exception:
        page = 0

    limit = 10
    offset = page * limit

    rows = DB.execute(
        """
        SELECT word,difficulty
        FROM custom_words
        ORDER BY id DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    ).fetchall()

    if not rows:
        return await query.answer(
            "No more words.",
            show_alert=True,
        )

    lines = [
        f"📚 **Custom Words — Page {page + 1}**",
        "",
    ]

    for row in rows:
        lines.append(
            f"• `{html.escape(row['word'])}` "
            f"— {row['difficulty']}"
        )

    nav = []

    if page > 0:
        nav.append(
            InlineKeyboardButton(
                "⬅️",
                callback_data=f"wb_{page - 1}",
            )
        )

    nav.append(
        InlineKeyboardButton(
            "🔄",
            callback_data=f"wb_{page}",
        )
    )

    if len(rows) == limit:
        nav.append(
            InlineKeyboardButton(
                "➡️",
                callback_data=f"wb_{page + 1}",
            )
        )

    buttons = [nav]

    buttons.append(
        [
            InlineKeyboardButton(
                "⬅️ Back",
                callback_data="back_to_words_menu",
            ),
            InlineKeyboardButton(
                "❌ Close",
                callback_data="close_panel",
            ),
        ]
    )

    try:
        await query.message.edit_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(buttons),
        )
    except MessageNotModified:
        pass


# ------------------------------------------------------------
# EVENT WIZARD CALLBACK HELPERS
# ------------------------------------------------------------

async def event_wizard_target(query, target_chat):
    uid = query.from_user.id

    if not is_owner(uid):
        return await query.answer(
            "Owner only.",
            show_alert=True,
        )

    try:
        target_chat = int(target_chat)
    except Exception:
        return await query.answer(
            "Invalid target.",
            show_alert=True,
        )

    current_chat = query.message.chat.id

    if current_chat not in EVENT_WIZARD:
        return await query.answer(
            "Wizard expired.",
            show_alert=True,
        )

    EVENT_WIZARD[current_chat]["target"] = target_chat
    EVENT_WIZARD[current_chat]["step"] = "name"

    await query.answer("Target selected.")

    try:
        await query.message.edit_text(
            "🎉 **Event Setup Wizard**\n\n"
            "Step 2/6 — Send the **event name**."
        )
    except Exception:
        pass


# ------------------------------------------------------------
# UNIFIED CALLBACK ROUTER
# ------------------------------------------------------------

@app.on_callback_query()
async def callback_router(client, query):
    data = query.data or ""
    uid = query.from_user.id
    chat_id = query.message.chat.id if query.message else None

    # --------------------------------------------------------
    # SHOP
    # --------------------------------------------------------

    if data == "open_shop_btn":
        text, kb = await build_shop_text_and_kb(uid)

        await query.answer()

        try:
            await query.message.edit_text(
                text,
                reply_markup=kb,
            )
        except Exception:
            pass

        return

    if data == "refresh_shop":
        text, kb = await build_shop_text_and_kb(uid)

        await query.answer("Shop refreshed.")

        try:
            await query.message.edit_text(
                text,
                reply_markup=kb,
            )
        except Exception:
            pass

        return

    if data == "close_panel":
        await query.answer()

        try:
            await query.message.delete()
        except Exception:
            try:
                await query.message.edit_text("❌ Closed.")
            except Exception:
                pass

        return

    # --------------------------------------------------------
    # NORMAL PUZZLE
    # --------------------------------------------------------

    if data == "hint":
        if not chat_id:
            return await query.answer(
                "Invalid chat.",
                show_alert=True,
            )

        game = DB.execute(
            "SELECT * FROM games WHERE chat_id=?",
            (chat_id,),
        ).fetchone()

        if not game:
            return await query.answer(
                "No active puzzle.",
                show_alert=True,
            )

        hint_row = DB.execute(
            "SELECT * FROM puzzle_hints WHERE puzzle_id=?",
            (game["puzzle_id"],),
        ).fetchone()

        if not hint_row:
            return await query.answer(
                "Hint unavailable.",
                show_alert=True,
            )

        used = int(hint_row["used"] or 0)

        if used:
            return await query.answer(
                "Hint already used.",
                show_alert=True,
            )

        word = game["word"]

        if len(word) <= 2:
            hint = word[0]
        else:
            reveal_count = max(1, len(word) // 3)
            indexes = list(range(len(word)))
            random.shuffle(indexes)
            reveal = set(indexes[:reveal_count])

            chars = []
            for i, ch in enumerate(word):
                if i in reveal:
                    chars.append(ch)
                else:
                    chars.append("_")

            hint = " ".join(chars)

        DB.execute(
            "UPDATE puzzle_hints SET used=1 WHERE puzzle_id=?",
            (game["puzzle_id"],),
        )
        DB.commit()

        await query.answer(
            f"💡 Hint: {hint}",
            show_alert=True,
        )

        return

    if data == "fight_hint":
        if not chat_id:
            return await query.answer(
                "Invalid chat.",
                show_alert=True,
            )

        fight = JUMBLE_FIGHT.get(chat_id)

        if not fight:
            return await query.answer(
                "No active fight.",
                show_alert=True,
            )

        uid_allowed = (
            fight["p1"].id,
            fight["p2"].id,
        )

        if uid not in uid_allowed:
            return await query.answer(
                "You are not in this fight.",
                show_alert=True,
            )

        word = fight["word"]

        if len(word) <= 2:
            hint = word[0]
        else:
            hint = word[0] + " _ " * (len(word) - 2) + word[-1]

        await query.answer(
            f"💡 {hint}",
            show_alert=True,
        )

        return

    if data == "skip":
        if not chat_id:
            return await query.answer(
                "Invalid chat.",
                show_alert=True,
            )

        game = DB.execute(
            "SELECT * FROM games WHERE chat_id=?",
            (chat_id,),
        ).fetchone()

        if not game:
            return await query.answer(
                "No active puzzle.",
                show_alert=True,
            )

        if game["message_id"]:
            try:
                await safe_delete_and_unpin(
                    chat_id,
                    game["message_id"],
                )
            except Exception:
                pass

        DB.execute(
            "DELETE FROM games WHERE chat_id=?",
            (chat_id,),
        )

        DB.execute(
            "DELETE FROM puzzle_hints WHERE puzzle_id=?",
            (game["puzzle_id"],),
        )

        DB.commit()

        await query.answer("⏭️ Skipped.")

        settings = get_settings(chat_id)

        if int(settings.get("active", 1)):
            await start_game(
                chat_id,
                settings.get("difficulty", "medium"),
            )

        return

    if data == "newword":
        if not chat_id:
            return await query.answer(
                "Invalid chat.",
                show_alert=True,
            )

        game = DB.execute(
            "SELECT * FROM games WHERE chat_id=?",
            (chat_id,),
        ).fetchone()

        if game:
            if game["message_id"]:
                try:
                    await safe_delete_and_unpin(
                        chat_id,
                        game["message_id"],
                    )
                except Exception:
                    pass

            DB.execute(
                "DELETE FROM games WHERE chat_id=?",
                (chat_id,),
            )

            DB.execute(
                "DELETE FROM puzzle_hints WHERE puzzle_id=?",
                (game["puzzle_id"],),
            )

            DB.commit()

        await query.answer("🆕 New word.")

        settings = get_settings(chat_id)

        if int(settings.get("active", 1)):
            await start_game(
                chat_id,
                settings.get("difficulty", "medium"),
            )

        return

    # --------------------------------------------------------
    # FIGHT ACCEPT / DECLINE
    # --------------------------------------------------------

    if data.startswith("f_accept:"):
        challenger_id = int(data.split(":", 1)[1])

        lobby = FIGHT_LOBBY.get(chat_id)

        if not lobby:
            return await query.answer(
                "Fight request expired.",
                show_alert=True,
            )

        if uid != lobby["target_id"]:
            return await query.answer(
                "This fight request is not for you.",
                show_alert=True,
            )

        FIGHT_LOBBY.pop(chat_id, None)

        await query.answer("Fight accepted!")

        await create_fight(
            chat_id,
            lobby["challenger_id"],
            lobby["target_id"],
            bet=0,
        )

        try:
            await query.message.edit_text(
                "⚔️ Fight accepted! Starting now..."
            )
        except Exception:
            pass

        return

    if data.startswith("f_decline:"):
        challenger_id = int(data.split(":", 1)[1])

        lobby = FIGHT_LOBBY.get(chat_id)

        if not lobby:
            return await query.answer(
                "Fight request expired.",
                show_alert=True,
            )

        if uid != lobby["target_id"]:
            return await query.answer(
                "Only the challenged player can decline.",
                show_alert=True,
            )

        FIGHT_LOBBY.pop(chat_id, None)

        await query.answer("Fight declined.")

        try:
            await query.message.edit_text(
                "❌ Fight declined."
            )
        except Exception:
            pass

        return

    # --------------------------------------------------------
    # BET FIGHT ACCEPT / DECLINE
    # --------------------------------------------------------

    if data.startswith("bf_accept:"):
        parts = data.split(":")

        if len(parts) < 2:
            return await query.answer(
                "Invalid request.",
                show_alert=True,
            )

        challenger_id = int(parts[1])

        lobby = FIGHT_LOBBY.get(chat_id)

        if not lobby:
            return await query.answer(
                "Bet fight request expired.",
                show_alert=True,
            )

        if uid != lobby["target_id"]:
            return await query.answer(
                "This request is not for you.",
                show_alert=True,
            )

        bet = int(lobby.get("bet", 0))

        challenger = await client.get_users(
            lobby["challenger_id"]
        )

        target = await client.get_users(
            lobby["target_id"]
        )

        ensure_user(challenger.id)
        ensure_user(target.id)

        c_user = get_user(challenger.id)
        t_user = get_user(target.id)

        if c_user["points"] < bet:
            FIGHT_LOBBY.pop(chat_id, None)
            return await query.answer(
                "Challenger no longer has enough points.",
                show_alert=True,
            )

        if t_user["points"] < bet:
            FIGHT_LOBBY.pop(chat_id, None)
            return await query.answer(
                "You don't have enough points.",
                show_alert=True,
            )

        DB.execute(
            "UPDATE users SET points=points-? WHERE user_id=?",
            (bet, challenger.id),
        )

        DB.execute(
            "UPDATE users SET points=points-? WHERE user_id=?",
            (bet, target.id),
        )

        DB.commit()

        FIGHT_LOBBY.pop(chat_id, None)

        await query.answer("Bet accepted!")

        await create_fight(
            chat_id,
            challenger.id,
            target.id,
            bet=bet,
        )

        try:
            await query.message.edit_text(
                f"💰 Bet fight accepted!\n"
                f"Stake: **{bet} points each**\n\n"
                f"⚔️ Starting..."
            )
        except Exception:
            pass

        return

    if data.startswith("bf_decline:"):
        lobby = FIGHT_LOBBY.get(chat_id)

        if not lobby:
            return await query.answer(
                "Request expired.",
                show_alert=True,
            )

        if uid != lobby["target_id"]:
            return await query.answer(
                "Only the challenged player can decline.",
                show_alert=True,
            )

        FIGHT_LOBBY.pop(chat_id, None)

        await query.answer("Bet fight declined.")

        try:
            await query.message.edit_text(
                "❌ Bet fight declined."
            )
        except Exception:
            pass

        return

    # --------------------------------------------------------
    # REBET
    # --------------------------------------------------------

    if data.startswith("rebet_challenge:"):
        loser_id = int(data.split(":", 1)[1])

        rebet = REBET_LOBBY.get(chat_id)

        if not rebet:
            return await query.answer(
                "Rebet request expired.",
                show_alert=True,
            )

        if uid != loser_id:
            return await query.answer(
                "Only the previous loser can rebet.",
                show_alert=True,
            )

        winner_id = rebet["winner_id"]
        original_bet = int(rebet.get("bet", 0))

        rebet_amount = max(
            1,
            int(original_bet * 0.25),
        )

        ensure_user(loser_id)
        ensure_user(winner_id)

        loser_user = get_user(loser_id)
        winner_user = get_user(winner_id)

        if loser_user["points"] < rebet_amount:
            return await query.answer(
                "You don't have enough points for the rebet.",
                show_alert=True,
            )

        if winner_user["points"] < rebet_amount:
            return await query.answer(
                "Opponent doesn't have enough points.",
                show_alert=True,
            )

        DB.execute(
            "UPDATE users SET points=points-? WHERE user_id=?",
            (rebet_amount, loser_id),
        )

        DB.execute(
            "UPDATE users SET points=points-? WHERE user_id=?",
            (rebet_amount, winner_id),
        )

        DB.commit()

        REBET_LOBBY.pop(chat_id, None)

        await query.answer("🔄 Rebet started!")

        await create_fight(
            chat_id,
            loser_id,
            winner_id,
            bet=rebet_amount,
        )

        try:
            await query.message.edit_text(
                f"🔄 **Rebet Fight!**\n\n"
                f"💰 Stake: `{rebet_amount}` points each\n"
                f"⚔️ Starting..."
            )
        except Exception:
            pass

        return

    # --------------------------------------------------------
    # SHOP PURCHASES
    # --------------------------------------------------------

    if data == "buy_card_point":
        ensure_user(uid)
        user = get_user(uid)

        price = int(GLOBAL_DEFAULTS["shop_point_card_price"])

        if user["points"] < price:
            return await query.answer(
                "Not enough points.",
                show_alert=True,
            )

        expires = int(time.time()) + int(
            GLOBAL_DEFAULTS["shop_point_card_duration"]
        )

        DB.execute(
            """
            UPDATE users
            SET points=points-?,
                point_card_exp=?
            WHERE user_id=?
            """,
            (price, expires, uid),
        )
        DB.commit()

        await query.answer(
            "🃏 2x Points Card purchased!",
            show_alert=True,
        )

        text, kb = await build_shop_text_and_kb(uid)

        try:
            await query.message.edit_text(
                text,
                reply_markup=kb,
            )
        except Exception:
            pass

        return

    if data == "buy_card_level":
        ensure_user(uid)
        user = get_user(uid)

        price = int(GLOBAL_DEFAULTS["shop_exp_card_price"])

        if user["points"] < price:
            return await query.answer(
                "Not enough points.",
                show_alert=True,
            )

        expires = int(time.time()) + int(
            GLOBAL_DEFAULTS["shop_exp_card_duration"]
        )

        DB.execute(
            """
            UPDATE users
            SET points=points-?,
                level_card_exp=?
            WHERE user_id=?
            """,
            (price, expires, uid),
        )
        DB.commit()

        await query.answer(
            "🃏 2x EXP Card purchased!",
            show_alert=True,
        )

        text, kb = await build_shop_text_and_kb(uid)

        try:
            await query.message.edit_text(
                text,
                reply_markup=kb,
            )
        except Exception:
            pass

        return

    if data == "buy_instant_exp":
        ensure_user(uid)
        user = get_user(uid)

        price = int(GLOBAL_DEFAULTS["shop_instant_exp_price"])
        exp_amount = int(GLOBAL_DEFAULTS["shop_instant_exp_amount"])

        if user["points"] < price:
            return await query.answer(
                "Not enough points.",
                show_alert=True,
            )

        new_exp = int(user["exp"]) + exp_amount
        new_level = calculate_level(new_exp)

        DB.execute(
            """
            UPDATE users
            SET points=points-?,
                exp=?,
                level=?
            WHERE user_id=?
            """,
            (
                price,
                new_exp,
                new_level,
                uid,
            ),
        )

        DB.commit()

        await query.answer(
            f"⚡ +{exp_amount} EXP added!",
            show_alert=True,
        )

        text, kb = await build_shop_text_and_kb(uid)

        try:
            await query.message.edit_text(
                text,
                reply_markup=kb,
            )
        except Exception:
            pass

        return

    # --------------------------------------------------------
    # EVENT WIZARD
    # --------------------------------------------------------

    if data.startswith("ev_target_chat:"):
        target = data.split(":", 1)[1]

        await event_wizard_target(
            query,
            target,
        )

        return

    if data.startswith("ev_cancel_wizard:"):
        if not is_owner(uid):
            return await query.answer(
                "Owner only.",
                show_alert=True,
            )

        EVENT_WIZARD.pop(chat_id, None)

        await query.answer(
            "Wizard cancelled."
        )

        try:
            await query.message.edit_text(
                "❌ Event setup cancelled."
            )
        except Exception:
            pass

        return

    if data.startswith("ev_restart_wizard:"):
        if not is_owner(uid):
            return await query.answer(
                "Owner only.",
                show_alert=True,
            )

        EVENT_WIZARD[chat_id] = {
            "step": "target",
            "target": None,
            "name": None,
            "description": None,
            "reward": None,
            "duration": None,
            "words": [],
        }

        await query.answer(
            "Wizard restarted."
        )

        try:
            await query.message.edit_text(
                "🎉 **Event Setup Wizard**\n\n"
                "Step 1/6 — Send target chat ID."
            )
        except Exception:
            pass

        return

    # --------------------------------------------------------
    # SETTINGS CALLBACKS
    # --------------------------------------------------------

    if data.startswith("set_diff_"):
        if not is_admin_or_owner(uid, chat_id):
            return await query.answer(
                "Admin/owner only.",
                show_alert=True,
            )

        parts = data.split(":")
        diff = parts[0].replace("set_diff_", "")

        if diff not in ("easy", "medium", "hard"):
            return await query.answer(
                "Invalid difficulty.",
                show_alert=True,
            )

        DB.execute(
            """
            INSERT INTO settings(chat_id,difficulty)
            VALUES (?,?)
            ON CONFLICT(chat_id)
            DO UPDATE SET difficulty=excluded.difficulty
            """,
            (chat_id, diff),
        )
        DB.commit()

        await query.answer(
            f"Difficulty set to {diff.title()}."
        )

        await show_settings_panel(
            chat_id,
            query.message,
        )

        return

    if data.startswith("set_active_"):
        if not is_admin_or_owner(uid, chat_id):
            return await query.answer(
                "Admin/owner only.",
                show_alert=True,
            )

        value = 1 if data.startswith("set_active_on") else 0

        DB.execute(
            """
            INSERT INTO settings(chat_id,active)
            VALUES (?,?)
            ON CONFLICT(chat_id)
            DO UPDATE SET active=excluded.active
            """,
            (chat_id, value),
        )
        DB.commit()

        await query.answer(
            "Game setting updated."
        )

        if value == 0:
            game = DB.execute(
                "SELECT * FROM games WHERE chat_id=?",
                (chat_id,),
            ).fetchone()

            if game:
                if game["message_id"]:
                    try:
                        await safe_delete_and_unpin(
                            chat_id,
                            game["message_id"],
                        )
                    except Exception:
                        pass

                DB.execute(
                    "DELETE FROM games WHERE chat_id=?",
                    (chat_id,),
                )

                DB.execute(
                    "DELETE FROM puzzle_hints WHERE puzzle_id=?",
                    (game["puzzle_id"],),
                )

                DB.commit()

        await show_settings_panel(
            chat_id,
            query.message,
        )

        return

    if data.startswith("set_auto_"):
        if not is_admin_or_owner(uid, chat_id):
            return await query.answer(
                "Admin/owner only.",
                show_alert=True,
            )

        value = 1 if data.startswith("set_auto_on") else 0

        DB.execute(
            """
            INSERT INTO settings(chat_id,auto_next)
            VALUES (?,?)
            ON CONFLICT(chat_id)
            DO UPDATE SET auto_next=excluded.auto_next
            """,
            (chat_id, value),
        )
        DB.commit()

        await query.answer(
            "Auto-next updated."
        )

        await show_settings_panel(
            chat_id,
            query.message,
        )

        return

    if data.startswith("set_event_"):
        if not is_admin_or_owner(uid, chat_id):
            return await query.answer(
                "Admin/owner only.",
                show_alert=True,
            )

        value = 1 if data.startswith("set_event_on") else 0

        DB.execute(
            """
            INSERT INTO settings(chat_id,event_active)
            VALUES (?,?)
            ON CONFLICT(chat_id)
            DO UPDATE SET event_active=excluded.event_active
            """,
            (chat_id, value),
        )
        DB.commit()

        await query.answer(
            "Event setting updated."
        )

        await show_settings_panel(
            chat_id,
            query.message,
        )

        return

    # --------------------------------------------------------
    # LEADERBOARD
    # --------------------------------------------------------

    if data.startswith("lb_"):
        page = data.split("_", 1)[1]
        await query.answer()
        await leaderboard_page(
            query,
            page,
        )
        return

    # --------------------------------------------------------
    # WORD BROWSER
    # --------------------------------------------------------

    if data.startswith("wb_"):
        page = data.split("_", 1)[1]
        await query.answer()
        await words_browser_page(
            query,
            page,
        )
        return

    if data == "back_to_words_menu":
        await query.answer()

        kb = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "📚 Browse Words",
                        callback_data="wb_0",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "❌ Close",
                        callback_data="close_panel",
                    )
                ],
            ]
        )

        try:
            await query.message.edit_text(
                "📚 **Words Menu**",
                reply_markup=kb,
            )
        except Exception:
            pass

        return

    # --------------------------------------------------------
    # NO-OP / UNKNOWN
    # --------------------------------------------------------

    if data.startswith("noop_page"):
        return await query.answer()

    await query.answer(
        "This button is no longer active.",
        show_alert=True,
    )


# ------------------------------------------------------------
# TEXT ANSWER HANDLER
# ------------------------------------------------------------

@app.on_message(filters.text)
async def unified_text_handler(client, message):
    text = (message.text or "").strip()

    if not text:
        return

    # Never process commands here.
    if text.startswith("/"):
        return

    uid = message.from_user.id
    chat_id = message.chat.id

    ensure_user(uid)

    # --------------------------------------------------------
    # EVENT WIZARD
    # --------------------------------------------------------

    if chat_id in EVENT_WIZARD:
        handled = await process_event_wizard(message)

        if handled:
            return

    # --------------------------------------------------------
    # FIGHT ANSWER
    # --------------------------------------------------------

    fight = JUMBLE_FIGHT.get(chat_id)

    if fight:
        allowed_players = {
            fight["p1"].id,
            fight["p2"].id,
        }

        if uid not in allowed_players:
            return

        answer = clean_answer(text)
        correct = clean_answer(fight["word"])

        if answer == correct:
            await finish_fight(
                chat_id,
                message.from_user,
            )
        else:
            try:
                await message.react("❌")
            except Exception:
                pass

        return

    # --------------------------------------------------------
    # EVENT GAME ANSWER
    # --------------------------------------------------------

    event_game = DB.execute(
        """
        SELECT eg.*, e.name AS event_name,
               e.reward_stars AS event_reward
        FROM event_games eg
        LEFT JOIN events e
        ON e.id = eg.event_id
        WHERE eg.chat_id=?
          AND eg.user_id=?
          AND eg.solved=0
        ORDER BY eg.id DESC
        LIMIT 1
        """,
        (
            chat_id,
            uid,
        ),
    ).fetchone()

    if event_game:
        answer = clean_answer(text)
        correct = clean_answer(event_game["word"])

        if answer == correct:
            reward = int(
                event_game["event_reward"] or
                GLOBAL_DEFAULTS["event_reward"]
            )

            exp_gain = int(
                GLOBAL_DEFAULTS["exp_per_correct"]
            )

            user = get_user(uid)

            if user:
                point_multiplier = 2 if (
                    int(user["point_card_exp"] or 0)
                    > int(time.time())
                ) else 1

                exp_multiplier = 2 if (
                    int(user["level_card_exp"] or 0)
                    > int(time.time())
                ) else 1

                reward *= point_multiplier
                exp_gain *= exp_multiplier

                new_points = int(user["points"]) + reward
                new_exp = int(user["exp"]) + exp_gain
                new_level = calculate_level(new_exp)

                DB.execute(
                    """
                    UPDATE users
                    SET points=?,
                        exp=?,
                        level=?,
                        streak=streak+1,
                        best_streak=
                            MAX(best_streak,streak+1)
                    WHERE user_id=?
                    """,
                    (
                        new_points,
                        new_exp,
                        new_level,
                        uid,
                    ),
                )

                DB.execute(
                    """
                    INSERT INTO score_history
                    (user_id,chat_id,action,points,created_at,tag)
                    VALUES (?,?,?,?,?,?)
                    """,
                    (
                        uid,
                        chat_id,
                        "event_win",
                        reward,
                        int(time.time()),
                        "event",
                    ),
                )

                DB.commit()

            DB.execute(
                """
                UPDATE event_games
                SET solved=1
                WHERE id=?
                """,
                (event_game["id"],),
            )

            DB.commit()

            await message.reply_text(
                f"🎉 **Correct!**\n\n"
                f"🏆 Event: {html.escape(event_game['event_name'] or 'Event')}\n"
                f"⭐ +{reward} points\n"
                f"✨ +{exp_gain} EXP\n"
                f"📈 Level: {new_level}"
            )

        else:
            try:
                await message.react("❌")
            except Exception:
                pass

        return

    # --------------------------------------------------------
    # NORMAL JUMBLE ANSWER
    # --------------------------------------------------------

    game = DB.execute(
        """
        SELECT *
        FROM games
        WHERE chat_id=?
        LIMIT 1
        """,
        (chat_id,),
    ).fetchone()

    if not game:
        return

    answer = clean_answer(text)
    correct = clean_answer(game["word"])

    if answer != correct:
        try:
            await message.react("❌")
        except Exception:
            pass
        return

    # --------------------------------------------------------
    # CORRECT ANSWER
    # --------------------------------------------------------

    user = get_user(uid)

    if not user:
        ensure_user(uid)
        user = get_user(uid)

    base_points = int(game["points"] or 0)
    base_exp = int(game["exp"] or 0)

    now = int(time.time())

    point_multiplier = 2 if (
        int(user["point_card_exp"] or 0) > now
    ) else 1

    exp_multiplier = 2 if (
        int(user["level_card_exp"] or 0) > now
    ) else 1

    earned_points = base_points * point_multiplier
    earned_exp = base_exp * exp_multiplier

    old_streak = int(user["streak"] or 0)
    new_streak = old_streak + 1

    new_points = int(user["points"]) + earned_points
    new_exp = int(user["exp"]) + earned_exp
    new_level = calculate_level(new_exp)

    DB.execute(
        """
        UPDATE users
        SET points=?,
            exp=?,
            level=?,
            streak=?,
            best_streak=MAX(best_streak,?)
        WHERE user_id=?
        """,
        (
            new_points,
            new_exp,
            new_level,
            new_streak,
            new_streak,
            uid,
        ),
    )

    DB.execute(
        """
        INSERT INTO score_history
        (user_id,chat_id,action,points,created_at,tag)
        VALUES (?,?,?,?,?,?)
        """,
        (
            uid,
            chat_id,
            "correct",
            earned_points,
            now,
            "jumble",
        ),
    )

    DB.execute(
        "DELETE FROM games WHERE chat_id=?",
        (chat_id,),
    )

    DB.execute(
        "DELETE FROM puzzle_hints WHERE puzzle_id=?",
        (game["puzzle_id"],),
    )

    DB.execute(
        """
        INSERT OR IGNORE INTO used_words
        (chat_id,word,used_at)
        VALUES (?,?,?)
        """,
        (
            chat_id,
            game["word"],
            now,
        ),
    )

    DB.commit()

    # Remove old puzzle.
    if game["message_id"]:
        try:
            await safe_delete_and_unpin(
                chat_id,
                game["message_id"],
            )
        except Exception:
            pass

    await message.reply_text(
        f"🎉 **Correct Answer!**\n\n"
        f"📝 Word: **{html.escape(game['word'])}**\n"
        f"⭐ +{earned_points} points\n"
        f"✨ +{earned_exp} EXP\n"
        f"🔥 Streak: {new_streak}\n"
        f"📈 Level: {new_level}"
    )

    settings = get_settings(chat_id)

    if int(settings.get("active", 1)) and int(
        settings.get("auto_next", 1)
    ):
        await asyncio.sleep(0.8)

        await start_game(
            chat_id,
            settings.get("difficulty", "medium"),
        )


# ------------------------------------------------------------
# EVENT SCHEDULER
# ------------------------------------------------------------

async def event_scheduler_loop():
    while True:
        try:
            now = int(time.time())

            events = DB.execute(
                """
                SELECT *
                FROM events
                WHERE active=1
                  AND (
                      started_at IS NULL
                      OR started_at<=?
                  )
                ORDER BY id ASC
                """,
                (now,),
            ).fetchall()

            for event in events:
                event_id = event["id"]
                target_chat = event["chat_id"]

                settings = get_settings(target_chat)

                if not int(settings.get("event_active", 1)):
                    continue

                # Existing event game?
                existing = DB.execute(
                    """
                    SELECT id
                    FROM event_games
                    WHERE event_id=?
                      AND chat_id=?
                      AND solved=0
                    LIMIT 1
                    """,
                    (
                        event_id,
                        target_chat,
                    ),
                ).fetchone()

                if existing:
                    continue

                words = DB.execute(
                    """
                    SELECT word
                    FROM event_words
                    WHERE event_id=?
                    ORDER BY RANDOM()
                    LIMIT 1
                    """,
                    (event_id,),
                ).fetchall()

                if not words:
                    continue

                word = words[0]["word"]
                puzzle = jumble_word(word)

                DB.execute(
                    """
                    INSERT INTO event_games
                    (event_id,chat_id,word,jumbled,solved,created_at)
                    VALUES (?,?,?,?,?,?)
                    """,
                    (
                        event_id,
                        target_chat,
                        word,
                        puzzle,
                        0,
                        now,
                    ),
                )

                DB.commit()

                try:
                    kb = InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "💡 Hint",
                                    callback_data="hint",
                                )
                            ]
                        ]
                    )

                    sent = await app.send_message(
                        target_chat,
                        f"🎉 **{html.escape(event['name'])}**\n\n"
                        f"{html.escape(event['description'] or '')}\n\n"
                        f"🔀 **Jumble:** `{puzzle}`\n\n"
                        f"🎁 Reward: `{event['reward_stars']}` points",
                        reply_markup=kb,
                    )

                    DB.execute(
                        """
                        UPDATE event_games
                        SET message_id=?
                        WHERE event_id=?
                          AND chat_id=?
                          AND solved=0
                        """,
                        (
                            sent.id,
                            event_id,
                            target_chat,
                        ),
                    )

                    DB.commit()

                except Exception:
                    pass

        except Exception:
            pass

        await asyncio.sleep(10)


# ------------------------------------------------------------
# SAFETY PATCHES / FALLBACK HELPERS
# ------------------------------------------------------------

async def safe_query_answer(query, text=None, show_alert=False):
    try:
        await query.answer(
            text or "",
            show_alert=show_alert,
        )
    except Exception:
        pass


# ------------------------------------------------------------
# STARTUP
# ------------------------------------------------------------

if __name__ == "__main__":
    print(
        "🚀 Advanced Jumble, Bet Fight, Level, "
        "Shop & Event Bot Started Successfully!"
    )

    loop = asyncio.get_event_loop()

    loop.create_task(
        resume_all_active_games()
    )

    loop.create_task(
        auto_backup_task()
    )

    loop.create_task(
        event_scheduler_loop()
    )

    app.run()


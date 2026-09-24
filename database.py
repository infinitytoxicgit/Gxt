import sqlite3
import time
from config import DB_NAME

DB = sqlite3.connect(DB_NAME, check_same_thread=False)
DB.row_factory = sqlite3.Row


def init_db():
    DB.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        name TEXT,
        points INTEGER DEFAULT 0,
        stars INTEGER DEFAULT 0,
        exp INTEGER DEFAULT 0,
        solved INTEGER DEFAULT 0,
        easy_solved INTEGER DEFAULT 0,
        medium_solved INTEGER DEFAULT 0,
        hard_solved INTEGER DEFAULT 0,
        best_streak INTEGER DEFAULT 0,
        streak INTEGER DEFAULT 0,
        fight_wins INTEGER DEFAULT 0,
        fight_losses INTEGER DEFAULT 0,
        bet_wins INTEGER DEFAULT 0,
        bet_losses INTEGER DEFAULT 0,
        is_private INTEGER DEFAULT 0,
        last_daily REAL DEFAULT 0,
        daily_claims INTEGER DEFAULT 0,
        point_boost_until REAL DEFAULT 0,
        exp_boost_until REAL DEFAULT 0
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

    CREATE TABLE IF NOT EXISTS settings (
        chat_id INTEGER PRIMARY KEY,
        easy INTEGER DEFAULT 120,
        medium INTEGER DEFAULT 300,
        hard INTEGER DEFAULT 600,
        default_diff TEXT DEFAULT 'medium',
        is_active INTEGER DEFAULT 1,
        auto_delete INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS bot_config (
        key TEXT PRIMARY KEY,
        value REAL
    );

    CREATE TABLE IF NOT EXISTS user_powers (
        user_id INTEGER,
        power_type TEXT,
        expires_at REAL,
        PRIMARY KEY(user_id, power_type)
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

    CREATE TABLE IF NOT EXISTS solve_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        chat_id INTEGER,
        points INTEGER,
        timestamp REAL
    );
    """)
    DB.commit()

    # Dynamic Column Migration for existing databases
    user_cols = [c[1] for c in DB.execute("PRAGMA table_info(users)").fetchall()]
    migrations = {
        "stars": "INTEGER DEFAULT 0",
        "exp": "INTEGER DEFAULT 0",
        "point_boost_until": "REAL DEFAULT 0",
        "exp_boost_until": "REAL DEFAULT 0",
        "easy_solved": "INTEGER DEFAULT 0",
        "medium_solved": "INTEGER DEFAULT 0",
        "hard_solved": "INTEGER DEFAULT 0",
        "daily_claims": "INTEGER DEFAULT 0",
        "last_daily": "REAL DEFAULT 0",
        "is_private": "INTEGER DEFAULT 0",
    }
    for col, col_type in migrations.items():
        if col not in user_cols:
            try:
                DB.execute(f"ALTER TABLE users ADD COLUMN {col} {col_type}")
            except Exception:
                pass

    # Purane points ko stars ke sath synchronize karein agar stars 0 hon
    DB.execute("UPDATE users SET stars = points WHERE stars = 0 AND points > 0")

    # EXP, Leveling, Points, Hints aur Power Shop ke Defaults
    defaults = {
        # EXP & Level Configs
        "exp_per_level": 500,
        "exp_easy": 15,
        "exp_medium": 25,
        "exp_hard": 40,

        # Points & Hints Configs
        "points_easy": 10,
        "points_medium": 20,
        "points_hard": 30,
        "hints_easy": 3,
        "hints_medium": 3,
        "hints_hard": 3,

        # Bonus & Daily
        "daily_bonus": 100,
        "daily_points": 100,
        "bonus_points": 100,
        "logging_enabled": 1,

        # Shop 2x Boosters Default Pricing & Durations (in seconds)
        "shop_stars2x_price": 200,
        "shop_stars2x_duration": 3600,   # 1 hour
        "shop_exp2x_price": 250,
        "shop_exp2x_duration": 3600,     # 1 hour
    }
    for k, v in defaults.items():
        DB.execute("INSERT OR IGNORE INTO bot_config (key, value) VALUES (?, ?)", (k, v))
    DB.commit()


init_db()


def get_global_config(key, default_val=0):
    row = DB.execute("SELECT value FROM bot_config WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default_val


def set_global_config(key, val):
    DB.execute("""
        INSERT INTO bot_config (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
    """, (key, val))
    DB.commit()


def ensure_user(user, first_name=None):
    if not user:
        return
    u_id = user.id if hasattr(user, "id") else int(user)
    u_name = user.username if hasattr(user, "username") else ""
    f_name = user.first_name if hasattr(user, "first_name") else (first_name or "Player")

    DB.execute("""
        INSERT INTO users(user_id, username, name)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            username=excluded.username,
            name=excluded.name
    """, (u_id, u_name or "", f_name))
    DB.commit()


def get_user(user_id):
    return DB.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()


def get_settings(chat_id):
    row = DB.execute("SELECT * FROM settings WHERE chat_id=?", (chat_id,)).fetchone()
    if not row:
        DB.execute("""
            INSERT INTO settings(chat_id, easy, medium, hard, default_diff, is_active, auto_delete)
            VALUES (?, 120, 300, 600, 'medium', 1, 0)
            ON CONFLICT(chat_id) DO NOTHING
        """, (chat_id,))
        DB.commit()
        row = DB.execute("SELECT * FROM settings WHERE chat_id=?", (chat_id,)).fetchone()
    return row


def set_settings(chat_id, key, value):
    valid_cols = ["easy", "medium", "hard", "default_diff", "is_active", "auto_delete"]
    if key in valid_cols:
        DB.execute(f"UPDATE settings SET {key}=? WHERE chat_id=?", (value, chat_id))
        DB.commit()


def get_top_players(limit=5):
    return DB.execute(
        "SELECT user_id, name, points, stars, exp, is_private FROM users ORDER BY stars DESC, points DESC LIMIT ?",
        (limit,),
    ).fetchall()


async def is_admin(chat_id, user_id):
    row = DB.execute("SELECT * FROM auth_users WHERE user_id=?", (user_id,)).fetchone()
    return bool(row)

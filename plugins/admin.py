import os
import sys
import subprocess
import time
from database import DB, get_settings, get_global_config, set_global_config, ensure_user, get_user
from helpers import is_admin_or_owner, is_authed, is_owner, delete_after, get_mention, is_group
from pyrogram import Client, filters
from pyrogram.enums import ChatType, ParseMode
from pyrogram.types import Message


# ============================================================
# 1. AUTO GIT UPDATE & RESTART (/update)
# ============================================================

@Client.on_message(filters.command("update"))
async def git_update_and_restart(client: Client, message: Message):
    if not message.from_user or not is_owner(message.from_user.id):
        return await message.reply_text("❌ Sirf Bot Owner hi bot ko update kar sakta hai.")

    status_msg = await message.reply_text("<blockquote>🔄 <b>Stashing local edits & pulling updates from GitHub...</b></blockquote>", parse_mode=ParseMode.HTML)

    try:
        # 1. Git stash local changes
        subprocess.run(["git", "stash"], capture_output=True, text=True, check=True)
        # 2. Git pull origin
        pull_res = subprocess.run(["git", "pull"], capture_output=True, text=True, check=True)
        output_txt = pull_res.stdout.strip() or "Already up to date."
    except Exception as err:
        return await status_msg.edit(f"<blockquote>❌ <b>Git Update Failed:</b>\n<code>{err}</code></blockquote>", parse_mode=ParseMode.HTML)

    await status_msg.edit(
        f"<blockquote>✅ <b>Git Update Success!</b>\n\n<code>{output_txt}</code>\n\n"
        f"🚀 <i>Restarting bot engine now...</i></blockquote>",
        parse_mode=ParseMode.HTML
    )

    # Clean restart of current python process
    time.sleep(1)
    os.execv(sys.executable, [sys.executable] + sys.argv)


# ============================================================
# 2. LOGGING CONTROL (/log)
# ============================================================

@Client.on_message(filters.command("log"))
async def log_toggle_cmd(_, message: Message):
    if not message.from_user or not is_owner(message.from_user.id):
        return await message.reply_text("❌ Sirf Bot Owner logging control kar sakta hai.")

    if len(message.command) < 2:
        curr = "Enabled" if get_global_config("logging_enabled", 1) else "Disabled"
        return await message.reply_text(
            f"<blockquote>Status: <b>{curr}</b>\nUsage: <code>/log enable</code> ya <code>/log disable</code></blockquote>",
            parse_mode=ParseMode.HTML
        )

    action = message.command[1].lower()
    if action in ("enable", "on", "1"):
        set_global_config("logging_enabled", 1)
        await message.reply_text("<blockquote>✅ <b>Channel Logging Enabled!</b></blockquote>", parse_mode=ParseMode.HTML)
    elif action in ("disable", "off", "0"):
        set_global_config("logging_enabled", 0)
        await message.reply_text("<blockquote>🚫 <b>Channel Logging Disabled!</b></blockquote>", parse_mode=ParseMode.HTML)
    else:
        await message.reply_text("Usage: <code>/log enable</code> ya <code>/log disable</code>")


# ============================================================
# 3. POINTS CALCULATION & BREAKDOWN (/calculate)
# ============================================================

@Client.on_message(filters.command(["calculate", "audit"]))
async def calculate_cmd(client: Client, message: Message):
    if not message.from_user or not is_authed(message.from_user.id):
        return await message.reply_text("❌ Sirf Auth Users & Owner is command ko access kar sakte hain.")

    target = None
    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user
    elif len(message.command) > 1:
        arg = message.command[1]
        try:
            target = await client.get_users(int(arg) if arg.isdigit() else arg)
        except Exception:
            return await message.reply_text("❌ User nahi mila.")
    else:
        target = message.from_user

    ensure_user(target)
    u = get_user(target.id)
    u_dict = dict(u) if u else {}

    e_pts = int(get_global_config("points_easy", 10))
    m_pts = int(get_global_config("points_medium", 20))
    h_pts = int(get_global_config("points_hard", 30))
    d_pts = int(get_global_config("daily_points", 100))

    e_count = u_dict.get("easy_solved", 0) or 0
    m_count = u_dict.get("medium_solved", 0) or 0
    h_count = u_dict.get("hard_solved", 0) or 0
    d_count = u_dict.get("daily_claims", 0) or 0

    adder_row = DB.execute("SELECT COUNT(*) as cnt FROM group_bonus WHERE user_id=?", (target.id,)).fetchone()
    b_count = adder_row["cnt"] if adder_row else 0
    b_pts = int(get_global_config("bonus_points", 100))

    total_easy_pts = e_count * e_pts
    total_med_pts = m_count * m_pts
    total_hard_pts = h_count * h_pts
    total_daily_pts = d_count * d_pts
    total_bonus_pts = b_count * b_pts

    mention = get_mention(target)
    wallet_pts = u_dict.get("stars", 0) if u_dict.get("stars", 0) > 0 else u_dict.get("points", 0)

    await message.reply_text(
        f"<blockquote>📊 <b>𝐏𝐎𝐈𝐍𝐓𝐒 𝐁𝐑𝐄𝐀𝐊𝐃𝐎𝐖𝐍 & 𝐂𝐀𝐋𝐂𝐔𝐋𝐀𝐓𝐈𝐎𝐍</b>\n\n"
        f"👤 <b>Player:</b> {mention} (<code>{target.id}</code>)\n\n"
        f"🟢 <b>Easy Words:</b> <code>{e_count}</code> × {e_pts} = <b>+{total_easy_pts} pts</b>\n"
        f"🟡 <b>Medium Words:</b> <code>{m_count}</code> × {m_pts} = <b>+{total_med_pts} pts</b>\n"
        f"🔴 <b>Hard Words:</b> <code>{h_count}</code> × {h_pts} = <b>+{total_hard_pts} pts</b>\n"
        f"🎁 <b>Daily Claims:</b> <code>{d_count} days</code> × {d_pts} = <b>+{total_daily_pts} pts</b>\n"
        f"👥 <b>Group Bonus:</b> <code>{b_count} groups</code> × {b_pts} = <b>+{total_bonus_pts} pts</b>\n\n"
        f"⭐ <b>𝐂𝐮𝐫𝐫𝐞𝐧𝐭 𝐖𝐚𝐥𝐥𝐞𝐭 𝐁𝐚𝐥𝐚𝐧𝐜𝐞:</b> <code>{wallet_pts} Stars/Points</code></blockquote>",
        parse_mode=ParseMode.HTML
    )


# ============================================================
# 4. LEVEL & EXP MANAGEMENT (/setlevel, /setexp)
# ============================================================

# Command: /setlevel 1000  (Sets 1 Level = 1000 EXP)
@Client.on_message(filters.command(["setlevel", "setlvl"]))
async def admin_set_level_exp(client: Client, message: Message):
    if not message.from_user or not is_owner(message.from_user.id):
        return await message.reply_text("❌ Only Bot Owner can change EXP per level formula.")

    if len(message.command) < 2 or not message.command[1].isdigit():
        return await message.reply_text("ℹ️ **Usage:** `/setlevel [EXP_amount]` (e.g. `/setlevel 1000`)")

    val = int(message.command[1])
    set_global_config("exp_per_level", val)
    await message.reply_text(
        f"<blockquote>✅ <b>Level Formula Updated!</b>\n1 Level = <code>{val} EXP</code></blockquote>",
        parse_mode=ParseMode.HTML
    )


# Command: /setexp easy 50 OR /setexp 1000
@Client.on_message(filters.command("setexp"))
async def admin_set_exp_cmd(client: Client, message: Message):
    if not message.from_user or not is_authed(message.from_user.id):
        return await message.reply_text("❌ Only Auth Users & Owner can configure EXP rewards.")

    args = message.command
    if len(args) == 2 and args[1].isdigit():
        val = int(args[1])
        set_global_config("exp_per_level", val)
        return await message.reply_text(f"<blockquote>✅ <b>Set 1 Level formula to:</b> <code>{val} EXP</code></blockquote>", parse_mode=ParseMode.HTML)

    if len(args) >= 3 and args[1].lower() in ["easy", "medium", "hard"] and args[2].isdigit():
        diff = args[1].lower()
        val = int(args[2])
        set_global_config(f"exp_{diff}", val)
        return await message.reply_text(f"<blockquote>✅ <code>{diff.title()}</code> reward set to: <b>+{val} EXP</b></blockquote>", parse_mode=ParseMode.HTML)

    return await message.reply_text("ℹ️ **Usage:** `/setexp 1000` OR `/setexp [easy/medium/hard] [EXP]`")


# ============================================================
# 5. REWARDS & BONUS CONFIG (/setbonus, /setdaily, /setpoints, /sethint)
# ============================================================

@Client.on_message(filters.command(["setbonus", "setdaily"]))
async def admin_set_daily_bonus(client: Client, message: Message):
    if not message.from_user or not is_authed(message.from_user.id):
        return await message.reply_text("❌ Only Auth Users & Owner can change daily bonus.")

    if len(message.command) < 2 or not message.command[1].isdigit():
        return await message.reply_text("ℹ️ **Usage:** `/setdaily [amount]` (e.g. `/setdaily 200`)")

    val = int(message.command[1])
    set_global_config("daily_bonus", val)
    set_global_config("daily_points", val)
    await message.reply_text(f"<blockquote>✅ <b>Daily Bonus Updated!</b>\nAmount: <code>+{val} Stars/Points</code></blockquote>", parse_mode=ParseMode.HTML)


@Client.on_message(filters.command(["setpoint", "setpoints"]))
async def admin_set_points(client: Client, message: Message):
    if not message.from_user or not is_authed(message.from_user.id):
        return await message.reply_text("❌ Only Auth Users & Owner can set puzzle points.")

    args = message.command
    if len(args) < 3 or args[1].lower() not in ["easy", "medium", "hard"] or not args[2].isdigit():
        return await message.reply_text("ℹ️ **Usage:** `/setpoints [easy/medium/hard] [value]`")

    diff = args[1].lower()
    val = int(args[2])
    set_global_config(f"points_{diff}", val)
    await message.reply_text(f"<blockquote>✅ <code>{diff.title()}</code> points set to: <b>+{val} pts</b></blockquote>", parse_mode=ParseMode.HTML)


@Client.on_message(filters.command(["sethint", "sethints"]))
async def admin_set_hints(client: Client, message: Message):
    if not message.from_user or not is_authed(message.from_user.id):
        return await message.reply_text("❌ Only Auth Users & Owner can set hint limits.")

    args = message.command
    if len(args) < 3 or args[1].lower() not in ["easy", "medium", "hard"] or not args[2].isdigit():
        return await message.reply_text("ℹ️ **Usage:** `/sethint [easy/medium/hard] [limit]`")

    diff = args[1].lower()
    val = int(args[2])
    set_global_config(f"hints_{diff}", val)
    await message.reply_text(f"<blockquote>✅ <code>{diff.title()}</code> hint limit set to: <b>{val} hints/word</b></blockquote>", parse_mode=ParseMode.HTML)


# ============================================================
# 6. AUTH USER MANAGEMENT (/auth, /unauth, /authlist)
# ============================================================

@Client.on_message(filters.command("auth"))
async def add_auth_user(client: Client, message: Message):
    if not message.from_user or not is_owner(message.from_user.id):
        return await message.reply_text("❌ Sirf Bot Owner auth users add kar sakta hai.")

    target = None
    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user
    elif len(message.command) > 1:
        arg = message.command[1]
        try:
            target = await client.get_users(int(arg) if arg.isdigit() else arg)
        except Exception:
            return await message.reply_text("❌ User nahi mila.")

    if not target:
        return await message.reply_text("ℹ️ **Usage:** `/auth @username` ya reply karein.")

    ensure_user(target)
    DB.execute("INSERT OR REPLACE INTO auth_users(user_id, username, name, added_at) VALUES (?, ?, ?, ?)",
               (target.id, target.username or "", target.first_name, time.time()))
    DB.commit()

    await message.reply_text(f"<blockquote>✅ <b>User Authorized!</b>\n👤 {get_mention(target)} (<code>{target.id}</code>)</blockquote>", parse_mode=ParseMode.HTML)


@Client.on_message(filters.command("unauth"))
async def remove_auth_user(client: Client, message: Message):
    if not message.from_user or not is_owner(message.from_user.id):
        return await message.reply_text("❌ Sirf Bot Owner auth users remove kar sakta hai.")

    target_id = None
    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
    elif len(message.command) > 1:
        arg = message.command[1]
        try:
            u = await client.get_users(int(arg) if arg.isdigit() else arg)
            target_id = u.id
        except Exception:
            return await message.reply_text("❌ User nahi mila.")

    if not target_id:
        return await message.reply_text("ℹ️ **Usage:** `/unauth @username` ya reply karein.")

    DB.execute("DELETE FROM auth_users WHERE user_id=?", (target_id,))
    DB.commit()
    await message.reply_text(f"<blockquote>🗑️ User <code>{target_id}</code> removed from Auth List!</blockquote>", parse_mode=ParseMode.HTML)


@Client.on_message(filters.command(["authlist", "auths"]))
async def list_auth_users(_, message: Message):
    if not message.from_user or not is_authed(message.from_user.id):
        return await message.reply_text("❌ Sirf Auth Users & Owner list dekh sakte hain.")

    rows = DB.execute("SELECT * FROM auth_users").fetchall()
    if not rows:
        return await message.reply_text("<blockquote>ℹ️ No authorized users registered yet.</blockquote>", parse_mode=ParseMode.HTML)

    items = []
    for idx, r in enumerate(rows, start=1):
        name = r["name"] or "User"
        items.append(f"{idx}. <b>{name}</b> (<code>{r['user_id']}</code>)")

    body = "\n".join(items)
    await message.reply_text(f"<blockquote>🛡️ <u><b>AUTHORIZED ADMINS</b></u>\n\n{body}</blockquote>", parse_mode=ParseMode.HTML)

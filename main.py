import asyncio
import os
import sys
import time
import importlib
import glob
import inspect
import traceback
from config import API_ID, API_HASH, BOT_TOKEN, OWNER_ID
from database import DB
from pyrogram import Client, idle, enums
from pyrogram.handlers import CallbackQueryHandler

app = Client(
    "advanced_jumble_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# =========================================================================
# ABSOLUTE MASTER COMMAND ROUTER
# =========================================================================
@app.on_message(group=-2)
async def direct_master_router(client, message):
    if not message.text:
        return

    raw = message.text.strip()
    if not (raw.startswith("/") or raw.startswith("!") or raw.startswith(".")):
        try:
            from plugins.answers import group_answer_handler
            await group_answer_handler(client, message)
        except Exception:
            pass
        return

    first_token = raw.split()[0]
    cmd = "/" + first_token[1:].lower().split("@")[0]

    # --- UI MODE TOGGLES ---
    if cmd in ("/rich", "/setrich"):
        from utils.rich import set_ui_mode
        set_ui_mode("rich")
        return await message.reply_text("<blockquote>✨ <b>RICH MODE ACTIVATED</b>\nAb se saare buttons native Rich Blocks me render honge!</blockquote>", parse_mode=enums.ParseMode.HTML)

    if cmd in ("/inline", "/setinline"):
        from utils.rich import set_ui_mode
        set_ui_mode("inline")
        return await message.reply_text("<blockquote>🔘 <b>INLINE MODE ACTIVATED</b>\nAb se saare buttons classic inline me render honge!</blockquote>", parse_mode=enums.ParseMode.HTML)

    # --- CALCULATE ---
    if cmd in ("/calculate", "/calc", "/math"):
        expr = raw[len(first_token):].strip()
        if not expr:
            return await message.reply_text("🧮 <b>Usage:</b> <code>/calculate 25 * 4 + 10</code>", parse_mode=enums.ParseMode.HTML)
        allowed = set("0123456789+-*/(). %^")
        if not all(c in allowed for c in expr):
            return await message.reply_text("❌ Sirf basic math allowed hai!")
        try:
            ans = eval(expr.replace("^", "**"), {"__builtins__": None}, {})
            from utils.rich import send_jumble_rich
            return await send_jumble_rich(client, message.chat.id, f"<blockquote>🧮 <b>Result :</b> <code>{ans}</code></blockquote>")
        except Exception as e:
            return await message.reply_text(f"❌ Error: <code>{e}</code>", parse_mode=enums.ParseMode.HTML)

    # --- STATS ---
    if cmd in ("/stats", "/mystats", "/profile", "/score"):
        try:
            from plugins.basic import stats_cmd
            return await stats_cmd(client, message)
        except Exception as e:
            print(f"[Stats Error]: {e}")
            traceback.print_exc()
            return await message.reply_text(f"❌ Stats error: {e}")

    # --- LEADERBOARD ---
    if cmd in ("/leaderboard", "/lb", "/top"):
        try:
            from plugins.basic import leaderboard_cmd
            return await leaderboard_cmd(client, message)
        except Exception as e:
            print(f"[Leaderboard Error]: {e}")
            traceback.print_exc()
            return

    # --- GAME CONTROLS ---
    if cmd in ("/jumble", "/startgame"):
        from plugins.game_core import start_game_cmd
        return await start_game_cmd(client, message)

    if cmd in ("/puzzle", "/current"):
        from plugins.game_core import puzzle_cmd
        return await puzzle_cmd(client, message)

    if cmd in ("/skip", "/next"):
        from plugins.game_core import skip_cmd
        return await skip_cmd(client, message)

    if cmd in ("/end", "/stop"):
        from plugins.game_core import end_game_cmd
        return await end_game_cmd(client, message)

    # --- SHOP, WORDS, SETTINGS ---
    if cmd in ("/shop", "/powershop", "/store"):
        from plugins.shop import open_shop_cmd
        return await open_shop_cmd(client, message)

    if cmd in ("/word", "/words", "/wordbank"):
        from plugins.words import words_panel_cmd
        return await words_panel_cmd(client, message)

    if cmd in ("/settings", "/setting"):
        from plugins.settings import settings_cmd
        return await settings_cmd(client, message)

    if cmd in ("/update", "/restart"):
        await message.reply_text("🔄 <b>Restarting...</b>", parse_mode=enums.ParseMode.HTML)
        os.system("git pull")
        time.sleep(1)
        os.execl(sys.executable, sys.executable, *sys.argv)
        return

async def register_callbacks_only():
    plugin_files = sorted(glob.glob("plugins/*.py"))
    for file_path in plugin_files:
        mod_name = file_path.replace("/", ".").replace("\\", ".")[:-3]
        if mod_name.endswith("__init__"):
            continue
        try:
            mod = importlib.import_module(mod_name)
            for attr_name in dir(mod):
                attr = getattr(mod, attr_name)
                if hasattr(attr, "handlers") and isinstance(getattr(attr, "handlers"), list):
                    for handler, group in getattr(attr, "handlers"):
                        if isinstance(handler, CallbackQueryHandler):
                            res = app.add_handler(handler, group)
                            if inspect.isawaitable(res):
                                await res
        except Exception as e:
            print(f"Error loading callback from {mod_name}: {e}")

async def main():
    print("🚀 Bot starting...")
    await app.start()
    me = await app.get_me()
    print(f"✅ Online as @{me.username}")
    await register_callbacks_only()
    await idle()
    await app.stop()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())

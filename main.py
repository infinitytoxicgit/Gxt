import asyncio
import os
import time
import importlib
import glob
import inspect
import traceback
from config import API_ID, API_HASH, BOT_TOKEN, OWNER_ID
from database import DB
from pyrogram import Client, idle, enums

app = Client(
    "advanced_jumble_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

async def auto_backup_task():
    await asyncio.sleep(10)
    while True:
        try:
            DB.commit()
            if os.path.exists("jumble_game.db"):
                await app.send_document(
                    chat_id=int(OWNER_ID),
                    document="jumble_game.db",
                    caption=f"🤖 <b>Auto Backup:</b> <code>{time.strftime('%Y-%m-%d %H:%M:%S')}</code>",
                    parse_mode=enums.ParseMode.HTML
                )
        except Exception as e:
            print(f"[Auto Backup Error]: {e}")
        await asyncio.sleep(21600)

async def resume_all_active_games():
    from plugins.game_core import start_game
    from helpers import ACTIVE_FIGHTS

    await asyncio.sleep(3)
    try:
        rows = DB.execute("SELECT chat_id, default_diff FROM settings WHERE is_active = 1 AND chat_id != 0").fetchall()
        for row in rows:
            c_id = row["chat_id"]
            diff = row["default_diff"] or "easy"
            if c_id in ACTIVE_FIGHTS:
                continue
            try:
                DB.execute("DELETE FROM games WHERE chat_id=?", (c_id,))
                DB.commit()
                await start_game(app, c_id, diff, c_id)
                await asyncio.sleep(0.5)
            except Exception as e:
                print(f"[Auto-Resume Error in {c_id}]: {e}")
    except Exception as err:
        print(f"[Resume Query Error]: {err}")

# =========================================================================
# DIRECT MASTER ROUTER: A to Z COMMAND MATRIX
# =========================================================================
@app.on_message()
async def direct_master_router(client, message):
    if not message.text:
        return

    raw = message.text.strip()
    # Normalize prefixes: /, !, .
    if not (raw.startswith("/") or raw.startswith("!") or raw.startswith(".")):
        # Message is an answer candidate -> Route to answers plugin
        try:
            from plugins.answers import group_answer_handler
            await group_answer_handler(client, message)
        except Exception:
            pass
        return

    # Extract command without prefix and without @bot_username
    first_token = raw.split()[0]
    cmd = "/" + first_token[1:].lower().split("@")[0]

    # 1. CORE JUMBLE GAME COMMANDS
    if cmd in ("/jumble", "/startgame", "/play"):
        try:
            from plugins.game_core import start_game_cmd
            await start_game_cmd(client, message)
        except Exception as e:
            print(f"🔥 Error in {cmd}: {e}")
            traceback.print_exc()
        return

    if cmd in ("/puzzle", "/current", "/puz"):
        try:
            from plugins.game_core import puzzle_cmd
            await puzzle_cmd(client, message)
        except Exception as e:
            print(f"🔥 Error in {cmd}: {e}")
            traceback.print_exc()
        return

    if cmd in ("/skip", "/next"):
        try:
            from plugins.game_core import skip_cmd
            await skip_cmd(client, message)
        except Exception as e:
            print(f"🔥 Error in {cmd}: {e}")
            traceback.print_exc()
        return

    if cmd in ("/end", "/stop", "/stopgame"):
        try:
            from plugins.game_core import end_game_cmd
            await end_game_cmd(client, message)
        except Exception as e:
            print(f"🔥 Error in {cmd}: {e}")
            traceback.print_exc()
        return

    # 2. POWER SHOP COMMANDS
    if cmd in ("/shop", "/powershop", "/store", "/power"):
        try:
            from plugins.shop import open_shop_cmd
            await open_shop_cmd(client, message)
        except Exception as e:
            print(f"🔥 Error in {cmd}: {e}")
            traceback.print_exc()
        return

    # 3. WORDS BANK COMMANDS
    if cmd in ("/word", "/words", "/wordbank"):
        try:
            from plugins.words import words_panel_cmd
            await words_panel_cmd(client, message)
        except Exception as e:
            print(f"🔥 Error in {cmd}: {e}")
            traceback.print_exc()
        return

    if cmd in ("/addword", "/addwords"):
        try:
            from plugins.words import add_word_cmd
            await add_word_cmd(client, message)
        except Exception as e:
            print(f"🔥 Error in {cmd}: {e}")
            traceback.print_exc()
        return

    if cmd in ("/delword", "/delwords", "/remword"):
        try:
            from plugins.words import del_word_cmd
            await del_word_cmd(client, message)
        except Exception as e:
            print(f"🔥 Error in {cmd}: {e}")
            traceback.print_exc()
        return

    # 4. LEADERBOARDS & RANKINGS
    if cmd in ("/leaderboard", "/lb", "/top", "/ranks"):
        try:
            try:
                from plugins.leaderboard import leaderboard_cmd
                await leaderboard_cmd(client, message)
            except ImportError:
                from plugins.basic import leaderboard_cmd
                await leaderboard_cmd(client, message)
        except Exception as e:
            print(f"🔥 Error in {cmd}: {e}")
            traceback.print_exc()
        return

    # 5. USER PROFILE & STATS
    if cmd in ("/stats", "/mystats", "/profile", "/me"):
        try:
            from plugins.basic import stats_cmd
            await stats_cmd(client, message)
        except Exception as e:
            print(f"🔥 Error in {cmd}: {e}")
            traceback.print_exc()
        return

    # 6. GROUP SETTINGS & CONFIGURATION
    if cmd in ("/settings", "/setting", "/config"):
        try:
            from plugins.settings import settings_cmd
            await settings_cmd(client, message)
        except Exception as e:
            print(f"🔥 Error in {cmd}: {e}")
            traceback.print_exc()
        return

    # 7. DAILY REWARD & STREAKS
    if cmd in ("/daily", "/claim", "/reward"):
        try:
            from plugins.daily import daily_reward_cmd
            await daily_reward_cmd(client, message)
        except Exception as e:
            print(f"🔥 Error in {cmd}: {e}")
            traceback.print_exc()
        return

    # 8. 1v1 FIGHT & DUEL
    if cmd in ("/fight", "/duel", "/challenge"):
        try:
            from plugins.fight import fight_challenge_cmd
            await fight_challenge_cmd(client, message)
        except Exception as e:
            print(f"🔥 Error in {cmd}: {e}")
            traceback.print_exc()
        return

    if cmd in ("/surrender", "/ff", "/cancelfight"):
        try:
            from plugins.fight import surrender_fight_cmd
            await surrender_fight_cmd(client, message)
        except Exception as e:
            print(f"🔥 Error in {cmd}: {e}")
            traceback.print_exc()
        return

    # 9. START & HELP
    if cmd in ("/start", "/help", "/rules"):
        try:
            from plugins.start import start_cmd
            await start_cmd(client, message)
        except Exception as e:
            print(f"🔥 Error in {cmd}: {e}")
            traceback.print_exc()
        return

    # 10. BASIC & MATH / CALCULATE
    if cmd in ("/calculate", "/calc", "/math"):
        try:
            from plugins.basic import calculate_cmd
            await calculate_cmd(client, message)
        except Exception as e:
            print(f"🔥 Error in {cmd}: {e}")
            traceback.print_exc()
        return

    if cmd in ("/ping", "/alive"):
        try:
            from plugins.basic import ping_cmd
            await ping_cmd(client, message)
        except Exception as e:
            print(f"🔥 Error in {cmd}: {e}")
            traceback.print_exc()
        return

    # 11. ADMIN & OWNER OPERATIONS
    if cmd in ("/broadcast", "/gcast"):
        try:
            from plugins.admin import broadcast_cmd
            await broadcast_cmd(client, message)
        except Exception as e:
            print(f"🔥 Error in {cmd}: {e}")
            traceback.print_exc()
        return

    if cmd in ("/update", "/pull", "/restart"):
        try:
            from plugins.admin import update_bot_cmd
            await update_bot_cmd(client, message)
        except Exception as e:
            print(f"🔥 Error in {cmd}: {e}")
            traceback.print_exc()
        return

    if cmd in ("/backup", "/dbbackup"):
        try:
            from plugins.backup import manual_backup_cmd
            await manual_backup_cmd(client, message)
        except Exception as e:
            print(f"🔥 Error in {cmd}: {e}")
            traceback.print_exc()
        return

    if cmd in ("/setexp", "/setstars", "/setpoints", "/resetuser"):
        try:
            from plugins.admin import admin_manage_user_cmd
            await admin_manage_user_cmd(client, message)
        except Exception as e:
            print(f"🔥 Error in {cmd}: {e}")
            traceback.print_exc()
        return

    # 12. UNMATCHED COMMAND FALLBACK TO REGISTERED HANDLERS
    message.continue_propagation()


async def register_plugins():
    print("📦 Explicitly Registering All Plugins & Callback Handlers...")
    plugin_files = sorted(glob.glob("plugins/*.py"))
    for file_path in plugin_files:
        mod_name = file_path.replace("/", ".").replace("\\", ".")[:-3]
        if mod_name.endswith("__init__"):
            continue
        try:
            mod = importlib.import_module(mod_name)
            for attr_name in dir(mod):
                attr = getattr(mod, attr_name)
                # Register callback queries and other handlers
                if hasattr(attr, "handlers") and isinstance(getattr(attr, "handlers"), list):
                    for handler, group in getattr(attr, "handlers"):
                        res = app.add_handler(handler, group)
                        if inspect.isawaitable(res):
                            await res
            print(f"  ✅ {mod_name:<25} ready")
        except Exception as e:
            print(f"  ❌ Error loading {mod_name}: {e}")

async def main():
    print("🚀 Modular Jumble Bot Starting...")
    await app.start()
    bot_me = await app.get_me()
    print(f"✅ Bot Online as @{bot_me.username} (ID: {bot_me.id})")

    await register_plugins()

    asyncio.create_task(resume_all_active_games())
    asyncio.create_task(auto_backup_task())

    await idle()
    await app.stop()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())

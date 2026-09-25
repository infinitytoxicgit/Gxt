import asyncio
import os
import time
import importlib
import glob
from config import API_ID, API_HASH, BOT_TOKEN, OWNER_ID
from database import DB
from pyrogram import Client, idle, enums

app = Client(
    "advanced_jumble_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

def register_plugins():
    print("📦 Explicitly Registering All Plugins to app...")
    plugin_files = sorted(glob.glob("plugins/*.py"))
    total_handlers = 0

    for file_path in plugin_files:
        mod_name = file_path.replace("/", ".").replace("\\", ".")[:-3]
        if mod_name.endswith("__init__"):
            continue
        try:
            mod = importlib.import_module(mod_name)
            file_handlers = 0
            for attr_name in dir(mod):
                attr = getattr(mod, attr_name)
                # Check for handlers declared via @Client.on_message / @Client.on_callback_query
                if hasattr(attr, "handlers") and isinstance(getattr(attr, "handlers"), list):
                    for handler, group in getattr(attr, "handlers"):
                        app.add_handler(handler, group)
                        file_handlers += 1
                        total_handlers += 1
            print(f"  ✅ {mod_name:<25} -> {file_handlers} handlers bound")
        except Exception as e:
            print(f"  ❌ Failed to load {mod_name}: {e}")

    print(f"🎯 Total Handlers Active in Dispatcher: {total_handlers}\n")


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


async def main():
    print("🚀 Modular Jumble Bot Starting...")
    register_plugins()

    await app.start()
    bot_me = await app.get_me()
    print(f"✅ Bot Online as @{bot_me.username} (ID: {bot_me.id})")

    asyncio.create_task(resume_all_active_games())
    asyncio.create_task(auto_backup_task())

    await idle()
    await app.stop()


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())

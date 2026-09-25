import asyncio
import os
import time
import importlib
import glob
from config import API_ID, API_HASH, BOT_TOKEN, OWNER_ID
from database import DB
from pyrogram import Client, idle, enums

# Disable Pyrogram's buggy auto-plugin loader and load manually with full binding
app = Client(
    "advanced_jumble_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

def load_all_plugins():
    print("📦 Loading and binding all plugins to app...")
    plugin_files = glob.glob("plugins/*.py")
    for file_path in plugin_files:
        module_name = file_path.replace("/", ".").replace("\\", ".")[:-3]
        if module_name.endswith("__init__"):
            continue
        try:
            mod = importlib.import_module(module_name)
            # Find all Pyrogram handlers declared in the module
            count = 0
            for attr in dir(mod):
                obj = getattr(mod, attr)
                # Check if it has pyrogram handler attributes
                if hasattr(obj, "handlers"):
                    for handler, group in getattr(obj, "handlers"):
                        app.add_handler(handler, group)
                        count += 1
            print(f"  ✅ {module_name} linked successfully ({count} handlers bound)")
        except Exception as e:
            print(f"  ❌ Error loading {module_name}: {e}")

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

# Live incoming logger to ensure bot is actually receiving Telegram updates
@app.on_message(group=-1)
async def incoming_update_tracker(client, message):
    chat_type = str(message.chat.type).replace("ChatType.", "")
    sender = message.from_user.first_name if message.from_user else "Unknown"
    text = message.text or "[Non-text message]"
    print(f"📨 [RECEIVE] Chat: {message.chat.id} ({chat_type}) | User: {sender} | Msg: {text}")
    message.continue_propagation()

async def main():
    print("🚀 Modular Jumble Bot Starting...")
    load_all_plugins()
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

import asyncio
import os
import time
import importlib
import glob
import inspect
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

# DIRECT ROUTER: Har command ko seedha execute karega bina kisi filter block ke!
@app.on_message()
async def direct_master_router(client, message):
    if not message.text:
        return

    raw = message.text.strip()
    cmd = raw.split()[0].lower().split("@")[0]

    # 1. Shop Commands
    if cmd in ("/shop", "/powershop", "/store"):
        print(f"⚡ [ROUTED DIRECTLY]: Executing /shop for {message.chat.id}")
        try:
            from plugins.shop import open_shop_cmd
            await open_shop_cmd(client, message)
        except Exception as e:
            import traceback
            print(f"🔥 Error executing /shop: {e}")
            traceback.print_exc()
        return

    # 2. Word Bank Commands
    if cmd in ("/word", "/words", "/wordbank"):
        print(f"⚡ [ROUTED DIRECTLY]: Executing /word for {message.chat.id}")
        try:
            from plugins.words import words_panel_cmd
            await words_panel_cmd(client, message)
        except Exception as e:
            import traceback
            print(f"🔥 Error executing /word: {e}")
            traceback.print_exc()
        return

    # 3. Add Word
    if cmd in ("/addword", "/addwords"):
        print(f"⚡ [ROUTED DIRECTLY]: Executing /addword for {message.chat.id}")
        try:
            from plugins.words import add_word_cmd
            await add_word_cmd(client, message)
        except Exception as e:
            import traceback
            print(f"🔥 Error executing /addword: {e}")
            traceback.print_exc()
        return

    # 4. Del Word
    if cmd in ("/delword", "/delwords"):
        print(f"⚡ [ROUTED DIRECTLY]: Executing /delword for {message.chat.id}")
        try:
            from plugins.words import del_word_cmd
            await del_word_cmd(client, message)
        except Exception as e:
            import traceback
            print(f"🔥 Error executing /delword: {e}")
            traceback.print_exc()
        return

    # 5. Jumble Game Trigger
    if cmd in ("/jumble", "/startgame"):
        print(f"⚡ [ROUTED DIRECTLY]: Executing /jumble for {message.chat.id}")
        try:
            from plugins.game_core import start_game_cmd
            await start_game_cmd(client, message)
        except Exception as e:
            import traceback
            print(f"🔥 Error executing /jumble: {e}")
            traceback.print_exc()
        return

    # 6. Stats & Profile
    if cmd in ("/stats", "/mystats", "/profile"):
        print(f"⚡ [ROUTED DIRECTLY]: Executing /stats for {message.chat.id}")
        try:
            from plugins.basic import stats_cmd
            await stats_cmd(client, message)
        except Exception as e:
            import traceback
            print(f"🔥 Error executing /stats: {e}")
            traceback.print_exc()
        return

    # 7. Answer Listener Pass-through (Agar command nahi hai toh check answer)
    try:
        from plugins.answers import group_answer_handler
        await group_answer_handler(client, message)
    except Exception as e:
        pass


async def register_plugins():
    print("📦 Explicitly Registering All Callbacks & Extra Plugins...")
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

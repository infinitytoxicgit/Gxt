import asyncio
import os
import time
from config import API_ID, API_HASH, BOT_TOKEN, OWNER_ID
from database import DB
from helpers import ACTIVE_FIGHTS
from plugins.game_core import start_game
from pyrogram import Client, idle

app = Client(
    "advanced_jumble_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    plugins=dict(root="plugins")
)

async def auto_backup_task():
    while True:
        await asyncio.sleep(21600)  # Har 6 ghante me auto-backup
        try:
            if os.path.exists("jumble_game.db"):
                await app.send_document(
                    chat_id=OWNER_ID,
                    document="jumble_game.db",
                    caption=f"🤖 <b>Auto Backup:</b> {time.strftime('%Y-%m-%d %H:%M:%S')}"
                )
        except Exception as e:
            print(f"Backup failed: {e}")

async def resume_all_active_games():
    # Bot connect hone ke liye 3 second wait
    await asyncio.sleep(3)
    try:
        # Jin groups me Game Status: Running (is_active = 1) hai
        rows = DB.execute("SELECT chat_id, default_diff FROM settings WHERE is_active = 1 AND chat_id != 0").fetchall()
        for row in rows:
            c_id = row["chat_id"]
            diff = row["default_diff"] or "medium"
            
            # Agar group me koi 1v1 fight active hai toh regular loop mat chhedo
            if c_id in ACTIVE_FIGHTS:
                continue

            try:
                # Purana stuck game delete karke fresh round start karo
                DB.execute("DELETE FROM games WHERE chat_id=?", (c_id,))
                DB.commit()
                await start_game(app, c_id, diff, c_id)
                await asyncio.sleep(0.5)  # FloodWait safety delay
            except Exception as e:
                print(f"[Auto-Resume Error in {c_id}]: {e}")
    except Exception as err:
        print(f"[Resume Query Error]: {err}")

async def main():
    print("🚀 Modular Jumble Bot Starting...")
    await app.start()
    bot_me = await app.get_me()
    print(f"✅ Bot Online as @{bot_me.username} (ID: {bot_me.id})")

    # 1. Sabhi active groups ke sessions unke mode ke hisab se resume karo
    asyncio.create_task(resume_all_active_games())

    # 2. Database Backup task
    asyncio.create_task(auto_backup_task())

    await idle()
    await app.stop()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())

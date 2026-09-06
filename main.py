import asyncio
import os
import time
from config import API_ID, API_HASH, BOT_TOKEN, OWNER_ID
from database import DB
from plugins.game_core import start_game
from pyrogram import Client

app = Client(
    "advanced_jumble_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    plugins=dict(root="plugins")
)

async def auto_backup_task():
    while True:
        await asyncio.sleep(21600)  # Every 6 hours
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
    await asyncio.sleep(3)
    rows = DB.execute("SELECT chat_id, default_diff FROM settings WHERE is_active = 1 AND chat_id != 0").fetchall()
    for row in rows:
        c_id = row["chat_id"]
        diff = row["default_diff"] or "medium"
        try:
            DB.execute("DELETE FROM games WHERE chat_id=?", (c_id,))
            DB.commit()
            await start_game(app, c_id, diff, c_id)
            await asyncio.sleep(0.8)
        except Exception as e:
            print(f"Auto-resume error in {c_id}: {e}")

if __name__ == "__main__":
    print("🚀 Modular Jumble Bot Starting...")
    loop = asyncio.get_event_loop()
    loop.create_task(resume_all_active_games())
    loop.create_task(auto_backup_task())
    app.run()

import asyncio
import os
import sys
import time
from config import API_ID, API_HASH, BOT_TOKEN, OWNER_ID
from database import DB
from pyrogram import Client, idle, enums

app = Client(
    "advanced_jumble_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    max_concurrent_transmissions=2,
    plugins=dict(root="plugins")
)

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
                await asyncio.sleep(1.0)
            except Exception as e:
                print(f"[Auto-Resume Error in {c_id}]: {e}")
    except Exception as err:
        print(f"[Resume Query Error]: {err}")

async def main():
    print("🚀 Bot starting native Rich engine...")
    await app.start()
    me = await app.get_me()
    print(f"✅ Online as @{me.username} (ID: {me.id})")

    asyncio.create_task(resume_all_active_games())

    await idle()
    await app.stop()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())

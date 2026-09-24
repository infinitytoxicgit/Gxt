import asyncio
import os
import time
from config import API_ID, API_HASH, BOT_TOKEN, OWNER_ID
from database import DB
from helpers import ACTIVE_FIGHTS
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

async def main():
    print("🚀 Modular Jumble Bot Starting...")
    await app.start()
    bot_me = await app.get_me()
    print(f"✅ Bot Online as @{bot_me.username} (ID: {bot_me.id})")

    # Background backup task
    asyncio.create_task(auto_backup_task())

    await idle()
    await app.stop()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())

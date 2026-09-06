import os
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv("API_ID", "35218869"))
API_HASH = os.getenv("API_HASH", "80baadcfd00a39a0ff1f5f529d23156f")
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "8564072723"))

# Log Channel / Group ID
LOG_CHANNEL = int(os.getenv("LOG_CHANNEL", "-1003515360437"))

START_IMG = "https://graph.org/file/7c0c03d68308f0c5dad42-ddb933df03f0ff0632.jpg"
SUPPORT_GC = "https://t.me/Roohi_Soul_Gc"
ADD_ME_URL = "https://t.me/Jumbles_Words_Bot?startgroup=true"
MUSIC_BOT_URL = "https://t.me/Roohi_Queen_Bot?start=_tgr_yN-6yUs4ZmRh"

DB_NAME = "jumble_game.db"

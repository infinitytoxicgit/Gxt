import os
import urllib.request
from pyrogram import Client, filters, enums, types
from pyrogram.types import Message
from database import ensure_user, get_user
from helpers import get_mention
from utils.rich import send_jumble_rich

# Naya image URL
START_BANNER_URL = "https://graph.org/file/ffb08ae20a8b09595d9ee-0798422a09215f7dc2.jpg"
LOCAL_BANNER_PATH = "cache/start_banner.jpg"


def get_cached_banner():
    # Agar local cache me valid image hai toh wahi use karo
    if os.path.isfile(LOCAL_BANNER_PATH) and os.path.getsize(LOCAL_BANNER_PATH) > 1000:
        return LOCAL_BANNER_PATH

    os.makedirs("cache", exist_ok=True)
    try:
        # Browser user-agent ke saath download karo taaki CDN block na kare
        req = urllib.request.Request(
            START_BANNER_URL,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
        )
        with urllib.request.urlopen(req, timeout=10) as resp, open(LOCAL_BANNER_PATH, "wb") as f:
            f.write(resp.read())

        if os.path.isfile(LOCAL_BANNER_PATH) and os.path.getsize(LOCAL_BANNER_PATH) > 1000:
            return LOCAL_BANNER_PATH
    except Exception as e:
        print(f"[Banner Download Error]: {e}")

    return None


@Client.on_message(filters.command("start") & filters.private)
async def dm_start_handler(client: Client, message: Message):
    ensure_user(message.from_user)
    u = get_user(message.from_user.id)
    u_dict = dict(u) if u else {}
    stars = u_dict.get("stars", 0) if u_dict.get("stars", 0) > 0 else u_dict.get("points", 0)

    welcome_text = (
        "<blockquote>🧩 <u><b>WELCOME TO ADVANCED JUMBLE BOT!</b></u></blockquote>\n\n"
        f"👋 Welcome {get_mention(message.from_user)}!\n\n"
        "<blockquote>🎮 <b>Game Commands (Groups) :</b>\n"
        "• <code>/jumble</code> ya <code>/word</code> - Start/Check active puzzle\n"
        "• <code>/jumblefight @user</code> - 1v1 Battle Mode (10-50 Rounds)\n"
        "• <code>/jumblebetfight [mode] [amt] @user</code> - 1v1 Bet Battle\n"
        "• <code>/settings</code> - Group Admin Panel (Timers, Modes)</blockquote>\n\n"
        "<blockquote>🎁 <b>Free Points & Rewards :</b>\n"
        "• <code>/daily</code> - Claim Daily Bonus Points in DM (Every 24h)\n"
        "• <code>/bonus</code> - Claim Group Addition Bonus (When Bot is Added as Admin)</blockquote>\n\n"
        "<blockquote>🛡️ <b>Privacy Settings :</b>\n"
        "• <code>/private</code> - Hide ID/Tag on Leaderboard (Name only)\n"
        "• <code>/public</code> - Show Tag & ID on Leaderboard</blockquote>\n\n"
        "<blockquote>📊 <b>Stats & Rankings :</b>\n"
        f"⭐ <b>Your Balance:</b> <code>{stars} Stars/Points</code>\n"
        "• <code>/stats</code> - Your Performance Matrix & EXP Bar\n"
        "• <code>/leaderboard</code> - Daily, Weekly, Monthly & Global Ranks\n"
        "• <code>/shop</code> - Buy 2x Stars & 2x EXP Boosters</blockquote>"
    )

    bot_info = await client.get_me()
    buttons = [
        [
            types.RichMessageButton(
                text="➕ Add Me to Your Group",
                style=enums.ButtonStyle.SUCCESS,
                url=f"https://t.me/{bot_info.username}?startgroup=true",
            )
        ],
        [
            types.RichMessageButton(
                text="🛍️ Power Shop",
                style=enums.ButtonStyle.PRIMARY,
                callback_data="open_shop_direct",
            ),
            types.RichMessageButton(
                text="👤 My Stats",
                style=enums.ButtonStyle.DEFAULT,
                callback_data="show_my_stats",
            ),
        ]
    ]

    banner_file = get_cached_banner()
    await send_jumble_rich(client, message.chat.id, welcome_text, buttons, photo=banner_file)


@Client.on_message(filters.command("help") & filters.private)
async def dm_help_handler(client: Client, message: Message):
    help_text = (
        "<blockquote>📖 <u><b>JUMBLE BOT COMMAND GUIDE</b></u></blockquote>\n\n"
        "<blockquote>🎮 <b>Main Commands :</b>\n"
        "• <code>/jumble</code> ya <code>/word</code> - Trigger puzzle in group\n"
        "• <code>/daily</code> - Claim daily reward (DM only)\n"
        "• <code>/bonus</code> - Claim group admin bonus (Once per group)\n"
        "• <code>/stats</code> - View stats with performance matrix\n"
        "• <code>/leaderboard</code> - View timeframe charts (24h/Wk/Mo/Yr)\n"
        "• <code>/shop</code> - Open 2x Boosters store\n"
        "• <code>/public</code> & <code>/private</code> - Toggle tag privacy</blockquote>\n\n"
        "<blockquote>🛡️ <b>Admin/Auth Commands :</b>\n"
        "• <code>/setdaily [amount]</code> - Set daily stars\n"
        "• <code>/setbonus [amount]</code> - Set group addition bonus\n"
        "• <code>/addstar @user [amount]</code> - Add stars to player\n"
        "• <code>/deductstar @user [amount]</code> - Deduct stars from player</blockquote>"
    )
    banner_file = get_cached_banner()
    await send_jumble_rich(client, message.chat.id, help_text, photo=banner_file)

import asyncio
from pyrogram import Client, filters, enums, types
from pyrogram.types import Message
from database import ensure_user, get_user
from helpers import get_mention
from utils.rich import send_jumble_rich

@Client.on_message(filters.command("start") & filters.private)
async def dm_start_handler(client: Client, message: Message):
    ensure_user(message.from_user)
    u = get_user(message.from_user.id)
    u_dict = dict(u) if u else {}
    stars = u_dict.get("stars", 0) if u_dict.get("stars", 0) > 0 else u_dict.get("points", 0)

    welcome_text = (
        "<blockquote>🎮 <u><b>𝐉𝐔𝐌𝐁𝐋𝐄 𝐖𝐎𝐑𝐃 𝐆𝐀𝐌𝐄 𝐁𝐎𝐓</b></u></blockquote>\n\n"
        f"👋 Welcome {get_mention(message.from_user)}!\n\n"
        "<blockquote>⚡ <b>Quick Overview :</b>\n"
        f"⭐ <b>Your Balance:</b> <code>{stars} Stars</code>\n"
        "🧩 <b>Puzzles:</b> Add me to your group to start unscrambling!\n"
        "⚔️ <b>Fights:</b> Challenge friends in 1v1 Duels & Bet Fights!</blockquote>\n\n"
        "<blockquote>📚 <b>Useful Commands :</b>\n"
        "• <code>/stats</code> — Check your Rank & EXP Slider\n"
        "• <code>/shop</code> — Open Power Shop (2x Boosters)\n"
        "• <code>/leaderboard</code> — View Global Top Solvers\n"
        "• <code>/daily</code> — Claim Free Daily Stars Reward</blockquote>"
    )

    buttons = [
        [
            types.RichMessageButton(
                text="➕ Add Me to Your Group",
                style=enums.ButtonStyle.SUCCESS,
                url=f"https://t.me/{(await client.get_me()).username}?startgroup=true",
            )
        ],
        [
            types.RichMessageButton(
                text="🛍️ Power Shop",
                style=enums.ButtonStyle.PRIMARY,
                callback_data=f"buy_shop|menu|{message.from_user.id}",
            ),
            types.RichMessageButton(
                text="👤 My Stats",
                style=enums.ButtonStyle.DEFAULT,
                callback_data="show_my_stats",
            ),
        ]
    ]

    await send_jumble_rich(client, message.chat.id, welcome_text, buttons)


@Client.on_message(filters.command("help") & filters.private)
async def dm_help_handler(client: Client, message: Message):
    help_text = (
        "<blockquote>📖 <u><b>𝐉𝐔𝐌𝐁𝐋𝐄 𝐁𝐎𝐓 𝐆𝐔𝐈𝐃𝐄</b></u></blockquote>\n\n"
        "<blockquote><b>🎮 Game Commands (Groups) :</b>\n"
        "• <code>/jumble</code> — Manually trigger a puzzle\n"
        "• <code>/fight</code> — Challenge someone to 10 rounds\n"
        "• <code>/betfight [easy/medium/hard] [amt] @user</code>\n"
        "• <code>/settings</code> — Admin Group Dashboard</blockquote>\n\n"
        "<blockquote><b>👤 Player Commands :</b>\n"
        "• <code>/stats</code> — View EXP bar & details\n"
        "• <code>/daily</code> — Daily streak bonus\n"
        "• <code>/shop</code> — Buy 2x Boosters</blockquote>"
    )
    await send_jumble_rich(client, message.chat.id, help_text)

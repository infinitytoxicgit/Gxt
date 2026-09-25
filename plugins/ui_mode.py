from pyrogram import Client, filters, enums
from pyrogram.types import Message
from utils.rich import set_ui_mode, get_ui_mode

@Client.on_message(filters.command(["rich", "setrich"], prefixes=["/", "!", "."]))
async def switch_rich_mode(client: Client, message: Message):
    set_ui_mode("rich")
    await message.reply_text(
        "<blockquote>✨ <b>RICH MODE ACTIVATED</b>\n\n"
        "• Sabhi cards, puzzles aur leaderboard ab <b>Rich UI Blocks</b> me aayenge!</blockquote>",
        parse_mode=enums.ParseMode.HTML
    )

@Client.on_message(filters.command(["inline", "setinline"], prefixes=["/", "!", "."]))
async def switch_inline_mode(client: Client, message: Message):
    set_ui_mode("inline")
    await message.reply_text(
        "<blockquote>🔘 <b>INLINE MODE ACTIVATED</b>\n\n"
        "• Sabhi buttons standard <b>Inline Keyboard</b> me switch ho gaye hain!</blockquote>",
        parse_mode=enums.ParseMode.HTML
    )

@Client.on_message(filters.command(["uimode"], prefixes=["/", "!", "."]))
async def check_ui_mode(client: Client, message: Message):
    curr = get_ui_mode()
    await message.reply_text(f"ℹ️ Current UI mode: <b>{curr.upper()}</b>", parse_mode=enums.ParseMode.HTML)

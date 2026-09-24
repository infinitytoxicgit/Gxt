from pyrogram import Client, filters, enums, types
from pyrogram.types import Message
from database import DB
from helpers import is_admin_or_owner
from word_bank import WORDS
from utils.rich import send_jumble_rich

# /word ya /words Panel
@Client.on_message(filters.command(["word", "words", "wordbank"]))
async def words_panel_cmd(client: Client, message: Message):
    if not await is_admin_or_owner(message.chat, message.from_user.id):
        return await message.reply_text("❌ Only Owner/Admin can view word database.")

    # Count words from DB and word_bank
    custom_counts = {}
    for d in ["easy", "medium", "hard"]:
        cnt = DB.execute("SELECT COUNT(*) as c FROM custom_words WHERE difficulty=?", (d,)).fetchone()["c"]
        custom_counts[d] = cnt

    total_easy = len(WORDS.get("easy", [])) + custom_counts["easy"]
    total_med = len(WORDS.get("medium", [])) + custom_counts["medium"]
    total_hard = len(WORDS.get("hard", [])) + custom_counts["hard"]

    caption = (
        "<blockquote>📚 <u><b>𝐉𝐔𝐌𝐁𝐋𝐄 𝐖𝐎𝐑𝐃 𝐁𝐀𝐍𝐊 𝐏𝐀𝐍𝐄𝐋</b></u>\n\n"
        f"🟢 <b>Easy Words :</b> <code>{total_easy}</code> (Custom: {custom_counts['easy']})\n"
        f"🟡 <b>Medium Words :</b> <code>{total_med}</code> (Custom: {custom_counts['medium']})\n"
        f"🔴 <b>Hard Words :</b> <code>{total_hard}</code> (Custom: {custom_counts['hard']})\n\n"
        "<b>Management Commands:</b>\n"
        "• <code>/addword easy apple</code>\n"
        "• <code>/addword medium guitar</code>\n"
        "• <code>/delword easy apple</code></blockquote>"
    )
    await send_jumble_rich(client, message.chat.id, caption)


# /addword easy python
@Client.on_message(filters.command(["addword", "newcustomword"]))
async def add_word_cmd(client: Client, message: Message):
    if not await is_admin_or_owner(message.chat, message.from_user.id):
        return await message.reply_text("❌ Only Owner/Admin can add words.")

    if len(message.command) < 3:
        return await message.reply_text("ℹ️ **Usage:** `/addword [easy/medium/hard] [word]`")

    diff = message.command[1].lower()
    word = message.command[2].strip().lower()

    if diff not in ["easy", "medium", "hard"]:
        return await message.reply_text("❌ Difficulty must be: `easy`, `medium`, or `hard`.")

    if not word.isalpha():
        return await message.reply_text("❌ Word me sirf alphabets hone chahiye.")

    try:
        DB.execute("INSERT INTO custom_words(difficulty, word) VALUES(?, ?)", (diff, word))
        DB.commit()
        if diff in WORDS and word not in WORDS[diff]:
            WORDS[diff].append(word)
        await message.reply_text(f"✅ Word <code>{word.upper()}</code> added to <b>{diff.upper()}</b> bank!", parse_mode=enums.ParseMode.HTML)
    except Exception:
        await message.reply_text("❌ Yeh word already database me exist karta hai.")


# /delword easy python
@Client.on_message(filters.command(["delword", "removeword"]))
async def del_word_cmd(client: Client, message: Message):
    if not await is_admin_or_owner(message.chat, message.from_user.id):
        return await message.reply_text("❌ Only Owner/Admin can delete words.")

    if len(message.command) < 3:
        return await message.reply_text("ℹ️ **Usage:** `/delword [easy/medium/hard] [word]`")

    diff = message.command[1].lower()
    word = message.command[2].strip().lower()

    cur = DB.execute("DELETE FROM custom_words WHERE difficulty=? AND word=?", (diff, word))
    DB.commit()

    if cur.rowcount > 0:
        if diff in WORDS and word in WORDS[diff]:
            WORDS[diff].remove(word)
        await message.reply_text(f"🗑️ Word <code>{word.upper()}</code> removed from database!", parse_mode=enums.ParseMode.HTML)
    else:
        await message.reply_text("❌ Yeh word custom words list me nahi mila.")

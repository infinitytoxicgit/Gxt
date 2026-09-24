import math
from pyrogram import Client, filters, enums, types
from pyrogram.types import Message, CallbackQuery
from database import DB
from helpers import is_admin_or_owner
from word_bank import WORDS
from utils.rich import send_jumble_rich, edit_jumble_rich

WORDS_PER_PAGE = 15

def get_words_for_diff(difficulty: str):
    builtin = WORDS.get(difficulty, [])
    rows = DB.execute("SELECT word FROM custom_words WHERE difficulty=?", (difficulty,)).fetchall()
    custom = [r["word"] for r in rows]
    # Unique combined list
    combined = sorted(list(set(builtin + custom)))
    return combined

def build_words_page(difficulty: str, page: int = 1):
    all_words = get_words_for_diff(difficulty)
    total_words = len(all_words)
    total_pages = max(1, math.ceil(total_words / WORDS_PER_PAGE))
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * WORDS_PER_PAGE
    page_words = all_words[start_idx : start_idx + WORDS_PER_PAGE]

    lines = []
    for i, w in enumerate(page_words, start=start_idx + 1):
        lines.append(f"<code>{i:02d}.</code> <b>{w.upper()}</b>")

    words_body = "\n".join(lines) if lines else "<i>No words found.</i>"

    caption = (
        f"<blockquote>📚 <u><b>{difficulty.upper()} WORDS BANK (Page {page}/{total_pages})</b></u>\n\n"
        f"Total Words in Database : <b>{total_words}</b>\n\n"
        f"{words_body}</blockquote>\n\n"
        f"<blockquote>Use <code>/addword {difficulty} [word]</code> or <code>/delword {difficulty} [word]</code></blockquote>"
    )

    nav_row = []
    if page > 1:
        nav_row.append(types.RichMessageButton(text="◀️ Prev", style=enums.ButtonStyle.PRIMARY, callback_data=f"wpage|{difficulty}|{page - 1}"))
    
    nav_row.append(types.RichMessageButton(text=f"📄 {page}/{total_pages}", style=enums.ButtonStyle.DEFAULT, callback_data="noop"))
    
    if page < total_pages:
        nav_row.append(types.RichMessageButton(text="Next ▶️", style=enums.ButtonStyle.PRIMARY, callback_data=f"wpage|{difficulty}|{page + 1}"))

    buttons = [
        nav_row,
        [
            types.RichMessageButton(text="🟢 Easy", style=enums.ButtonStyle.SUCCESS if difficulty == "easy" else enums.ButtonStyle.DANGER, callback_data="wpage|easy|1"),
            types.RichMessageButton(text="🟡 Medium", style=enums.ButtonStyle.SUCCESS if difficulty == "medium" else enums.ButtonStyle.DANGER, callback_data="wpage|medium|1"),
            types.RichMessageButton(text="🔴 Hard", style=enums.ButtonStyle.SUCCESS if difficulty == "hard" else enums.ButtonStyle.DANGER, callback_data="wpage|hard|1"),
        ],
        [
            types.RichMessageButton(text="❌ Close Panel", style=enums.ButtonStyle.DANGER, callback_data="wpage_close")
        ]
    ]
    return caption, buttons


# Command: /word or /words
@Client.on_message(filters.command(["word", "words", "wordbank"]))
async def words_panel_cmd(client: Client, message: Message):
    if not await is_admin_or_owner(message.chat, message.from_user.id):
        return await message.reply_text("❌ Only Owner/Admin can view word database.")

    caption, buttons = build_words_page("easy", 1)
    await send_jumble_rich(client, message.chat.id, caption, buttons)


@Client.on_callback_query(filters.regex(r"^(wpage|wpage_close)"))
async def words_pagination_callback(client: Client, query: CallbackQuery):
    if query.data == "wpage_close":
        await query.message.delete()
        return await query.answer("Closed!")

    data = query.data.split("|")
    diff = data[1]
    page = int(data[2])

    caption, buttons = build_words_page(diff, page)
    await query.answer()
    return await edit_jumble_rich(client, query.message.chat.id, query.message.id, caption, buttons)


# /addword easy apple
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
        await message.reply_text(f"<blockquote>✅ Word <code>{word.upper()}</code> added to <b>{diff.upper()}</b> bank!</blockquote>", parse_mode=enums.ParseMode.HTML)
    except Exception:
        await message.reply_text("❌ Yeh word already database me exist karta hai.")


# /delword easy apple
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
        await message.reply_text(f"<blockquote>🗑️ Word <code>{word.upper()}</code> removed from database!</blockquote>", parse_mode=enums.ParseMode.HTML)
    else:
        await message.reply_text("❌ Yeh word custom words list me nahi mila.")

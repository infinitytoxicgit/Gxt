import math
import re
from pyrogram import Client, filters, enums, types
from pyrogram.types import Message, CallbackQuery
from database import DB
from helpers import is_admin_or_owner, is_owner, is_authed, delete_after
from word_bank import WORDS
from utils.rich import send_jumble_rich, edit_jumble_rich

WORDS_PER_PAGE = 15
VALID_DIFFS = ("easy", "medium", "hard")


def get_words_for_diff(difficulty: str):
    difficulty = difficulty.lower()
    builtin = WORDS.get(difficulty, [])
    rows = DB.execute("SELECT word FROM custom_words WHERE difficulty=?", (difficulty,)).fetchall()
    custom = [r["word"] for r in rows]
    combined = sorted(list(set(builtin + custom)))
    return combined


def build_words_page(difficulty: str, page: int = 1):
    difficulty = difficulty.lower()
    all_words = get_words_for_diff(difficulty)
    total_words = len(all_words)
    total_pages = max(1, math.ceil(total_words / WORDS_PER_PAGE))
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * WORDS_PER_PAGE
    page_words = all_words[start_idx : start_idx + WORDS_PER_PAGE]

    lines = []
    for i, w in enumerate(page_words, start=start_idx + 1):
        # <code> tag par Telegram me tap karte hi word instant copy ho jata hai
        lines.append(f"<b>{i:02d}.</b> <code>{w.upper()}</code>")

    words_body = "\n".join(lines) if lines else "<i>No words found.</i>"

    caption = (
        f"<blockquote>📚 <u><b>{difficulty.upper()} WORDS BANK (Page {page}/{total_pages})</b></u>\n\n"
        f"Total Words in Database : <b>{total_words}</b>\n"
        f"💡 <i>Tap any word code block to copy instantly!</i></blockquote>\n\n"
        f"<blockquote>{words_body}</blockquote>\n\n"
        "<blockquote>➕ <b>Bulk Add :</b> <code>/addword [mode] word1 word2 word3</code>\n"
        "➖ <b>Bulk Del :</b> <code>/delword [mode] word1 word2 word3</code></blockquote>"
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
            types.RichMessageButton(text="🟢 Easy" if difficulty == "easy" else "🔴 Easy", style=enums.ButtonStyle.SUCCESS if difficulty == "easy" else enums.ButtonStyle.DANGER, callback_data="wpage|easy|1"),
            types.RichMessageButton(text="🟢 Medium" if difficulty == "medium" else "🔴 Medium", style=enums.ButtonStyle.SUCCESS if difficulty == "medium" else enums.ButtonStyle.DANGER, callback_data="wpage|medium|1"),
            types.RichMessageButton(text="🟢 Hard" if difficulty == "hard" else "🔴 Hard", style=enums.ButtonStyle.SUCCESS if difficulty == "hard" else enums.ButtonStyle.DANGER, callback_data="wpage|hard|1"),
        ],
        [
            types.RichMessageButton(text="❌ Close Panel", style=enums.ButtonStyle.DANGER, callback_data="wpage_close")
        ]
    ]
    return caption, buttons


# ============================================================
# WORDS BANK PANEL VIEWER
# ============================================================

@Client.on_message(filters.command(["wordbank", "wordsbank", "jumblewords"]), group=0)
async def words_panel_cmd(client: Client, message: Message):
    if not (is_owner(message.from_user.id) or is_authed(message.from_user.id) or await is_admin_or_owner(message.chat, message.from_user.id)):
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


# ============================================================
# BULK ADD WORDS COMMAND (/addword, /addwords)
# ============================================================

@Client.on_message(filters.command(["addword", "addwords"]), group=0)
async def bulk_add_words_cmd(client: Client, message: Message):
    if not (is_owner(message.from_user.id) or is_authed(message.from_user.id) or await is_admin_or_owner(message.chat, message.from_user.id)):
        return await message.reply_text("❌ Sirf Admin/Owner hi words add kar sakte hain.")

    args = message.text.split()[1:]
    if len(args) < 2:
        return await message.reply_text(
            "<blockquote>📖 <b>BULK ADD WORDS USAGE :</b>\n\n"
            "<code>/addword [easy|medium|hard] [word1] [word2] [word3] ...</code>\n\n"
            "<b>Example :</b>\n"
            "<code>/addword easy apple kind from home ball</code>\n"
            "<code>/addword hard helicopter, microscope, galaxy</code></blockquote>",
            parse_mode=enums.ParseMode.HTML
        )

    diff = args[0].lower()
    if diff not in VALID_DIFFS:
        return await message.reply_text(f"❌ Invalid difficulty! Choose from: <code>{', '.join(VALID_DIFFS)}</code>")

    # Extract all words separated by space, comma or newline
    raw_words_text = " ".join(args[1:])
    candidates = re.findall(r"[a-zA-Z]+", raw_words_text)

    if not candidates:
        return await message.reply_text("❌ Koi valid word nahi mila! Only alphabets allowed.")

    builtin = set(w.lower() for w in WORDS.get(diff, []))
    existing_custom = set(
        r["word"].lower() for r in DB.execute("SELECT word FROM custom_words WHERE difficulty=?", (diff,)).fetchall()
    )

    added = []
    skipped = []

    for w in candidates:
        w_clean = w.lower().strip()
        if len(w_clean) < 3:
            continue
        if w_clean in builtin or w_clean in existing_custom or w_clean in added:
            skipped.append(w_clean.upper())
            continue

        try:
            DB.execute("INSERT INTO custom_words (word, difficulty) VALUES (?, ?)", (w_clean, diff))
            added.append(w_clean.upper())
            existing_custom.add(w_clean)
        except Exception:
            pass

    DB.commit()

    copyable_added = " ".join([f"<code>{w}</code>" for w in added]) if added else "<i>None</i>"
    
    reply_msg = (
        f"<blockquote>✅ <b>BULK ADD SUMMARY ({diff.upper()})</b>\n\n"
        f"🟢 <b>Added ({len(added)}) :</b> {copyable_added}\n"
        f"⚪ <b>Skipped/Duplicate ({len(skipped)})</b>\n\n"
        f"💡 <i>Words have been saved into database successfully!</i></blockquote>"
    )
    await message.reply_text(reply_msg, parse_mode=enums.ParseMode.HTML)


# ============================================================
# BULK DELETE WORDS COMMAND (/delword, /delwords)
# ============================================================

@Client.on_message(filters.command(["delword", "delwords"]), group=0)
async def bulk_del_words_cmd(client: Client, message: Message):
    if not (is_owner(message.from_user.id) or is_authed(message.from_user.id) or await is_admin_or_owner(message.chat, message.from_user.id)):
        return await message.reply_text("❌ Sirf Admin/Owner hi words delete kar sakte hain.")

    args = message.text.split()[1:]
    if len(args) < 2:
        return await message.reply_text(
            "<blockquote>🗑️ <b>BULK DELETE WORDS USAGE :</b>\n\n"
            "<code>/delword [easy|medium|hard] [word1] [word2] ...</code>\n\n"
            "<b>Example :</b>\n"
            "<code>/delword easy apple kind home</code></blockquote>",
            parse_mode=enums.ParseMode.HTML
        )

    diff = args[0].lower()
    if diff not in VALID_DIFFS:
        return await message.reply_text(f"❌ Invalid difficulty! Choose from: <code>{', '.join(VALID_DIFFS)}</code>")

    raw_words_text = " ".join(args[1:])
    candidates = re.findall(r"[a-zA-Z]+", raw_words_text)

    if not candidates:
        return await message.reply_text("❌ Koi word nahi mila!")

    deleted = []
    not_found = []

    for w in candidates:
        w_clean = w.lower().strip()
        cur = DB.execute("DELETE FROM custom_words WHERE difficulty=? AND word=?", (diff, w_clean))
        if cur.rowcount > 0:
            deleted.append(w_clean.upper())
        else:
            not_found.append(w_clean.upper())

    DB.commit()

    copyable_del = " ".join([f"<code>{w}</code>" for w in deleted]) if deleted else "<i>None</i>"

    reply_msg = (
        f"<blockquote>🗑️ <b>BULK DELETE SUMMARY ({diff.upper()})</b>\n\n"
        f"🔴 <b>Deleted ({len(deleted)}) :</b> {copyable_del}\n"
        f"⚪ <b>Not Found in Custom DB ({len(not_found)})</b>\n\n"
        f"💡 <i>(Built-in code bank words cannot be deleted via DB)</i></blockquote>"
    )
    await message.reply_text(reply_msg, parse_mode=enums.ParseMode.HTML)

from pyrogram import Client, filters, enums, types
from pyrogram.types import Message, CallbackQuery
from database import DB, get_settings
from helpers import is_admin_or_owner
from utils.rich import send_jumble_rich, html_to_rich_blocks

def build_settings_card(chat_id: int, chat_title: str):
    raw_s = get_settings(chat_id)
    s = dict(raw_s) if raw_s else {}

    is_active = bool(s.get("is_active", 1))
    auto_del = bool(s.get("auto_delete", 0))
    cur_diff = str(s.get("default_diff", "medium")).lower()

    easy_t = s.get("easy", 120)
    med_t = s.get("medium", 300)
    hard_t = s.get("hard", 600)

    # Status indicators
    st_text = "🟢 Active (Running)" if is_active else "🔴 Inactive (Stopped)"
    del_text = "🟢 Enabled" if auto_del else "🔴 Disabled"

    caption = (
        f"<blockquote>⚙️ <b>𝐉ᴜᴍʙʟᴇ 𝐆ʀᴏᴜᴘ 𝐒ᴇᴛᴛɪɴɢs</b>\n\n"
        f"👥 <b>Group :</b> <code>{chat_title}</code>\n"
        f"🆔 <b>Chat ID :</b> <code>{chat_id}</code>\n\n"
        f"⚡ <b>Game Status :</b> {st_text}\n"
        f"🗑️ <b>Auto Delete :</b> {del_text}\n"
        f"🎯 <b>Default Mode :</b> <code>{cur_diff.title()}</code>\n"
        f"⏱️ <b>Round Timers :</b> Easy: <code>{easy_t}s</code> | Med: <code>{med_t}s</code> | Hard: <code>{hard_t}s</code></blockquote>\n\n"
        f"<blockquote><i>Click buttons to toggle settings:</i></blockquote>"
    )

    # Dynamic Green (Active/ON) and Red (Inactive/OFF)
    state_btn_style = enums.ButtonStyle.SUCCESS if is_active else enums.ButtonStyle.DANGER
    state_btn_label = "🟢 Game: Running" if is_active else "🔴 Game: Stopped"

    del_btn_style = enums.ButtonStyle.SUCCESS if auto_del else enums.ButtonStyle.DANGER
    del_btn_label = "🗑️ AutoDel: ON" if auto_del else "🗑️ AutoDel: OFF"

    buttons = [
        [
            types.RichMessageButton(
                text=state_btn_label,
                style=state_btn_style,
                callback_data=f"set_toggle_active|{chat_id}",
            ),
            types.RichMessageButton(
                text=del_btn_label,
                style=del_btn_style,
                callback_data=f"set_toggle_autodel|{chat_id}",
            ),
        ],
        [
            types.RichMessageButton(
                text=f"{'🟢' if cur_diff=='easy' else '🔴'} Easy",
                style=enums.ButtonStyle.SUCCESS if cur_diff == "easy" else enums.ButtonStyle.DANGER,
                callback_data=f"set_diff|easy|{chat_id}",
            ),
            types.RichMessageButton(
                text=f"{'🟢' if cur_diff=='medium' else '🔴'} Medium",
                style=enums.ButtonStyle.SUCCESS if cur_diff == "medium" else enums.ButtonStyle.DANGER,
                callback_data=f"set_diff|medium|{chat_id}",
            ),
            types.RichMessageButton(
                text=f"{'🟢' if cur_diff=='hard' else '🔴'} Hard",
                style=enums.ButtonStyle.SUCCESS if cur_diff == "hard" else enums.ButtonStyle.DANGER,
                callback_data=f"set_diff|hard|{chat_id}",
            ),
        ],
        [
            types.RichMessageButton(
                text="⏱️ Configure Timers",
                style=enums.ButtonStyle.PRIMARY,
                callback_data=f"set_menu_timers|{chat_id}",
            ),
            types.RichMessageButton(
                text="❌ Close",
                style=enums.ButtonStyle.DANGER,
                callback_data=f"set_close_panel|{chat_id}",
            ),
        ]
    ]
    return caption, buttons


def build_timers_card(chat_id: int):
    raw_s = get_settings(chat_id)
    s = dict(raw_s) if raw_s else {}
    cur_diff = s.get("default_diff", "medium")
    cur_val = s.get(cur_diff, 120)

    caption = (
        f"<blockquote>⏱️ <b>Configure {cur_diff.title()} Timers</b>\n\n"
        f"Select round time limit for <code>{cur_diff.upper()}</code> mode:\n"
        f"Selected: <b>{cur_val}s</b> (Green is active)</blockquote>"
    )

    options = [30, 45, 60, 120, 300, 600]
    row1 = []
    row2 = []
    for opt in options[:3]:
        style = enums.ButtonStyle.SUCCESS if cur_val == opt else enums.ButtonStyle.DANGER
        row1.append(types.RichMessageButton(text=f"{'🟢' if cur_val==opt else '🔴'} {opt}s", style=style, callback_data=f"set_timer_val|{cur_diff}|{opt}|{chat_id}"))
    for opt in options[3:]:
        style = enums.ButtonStyle.SUCCESS if cur_val == opt else enums.ButtonStyle.DANGER
        row2.append(types.RichMessageButton(text=f"{'🟢' if cur_val==opt else '🔴'} {opt}s", style=style, callback_data=f"set_timer_val|{cur_diff}|{opt}|{chat_id}"))

    buttons = [
        row1,
        row2,
        [
            types.RichMessageButton(text="🔙 Back to Settings", style=enums.ButtonStyle.PRIMARY, callback_data=f"set_back_main|{chat_id}")
        ]
    ]
    return caption, buttons


# Command: /settings
@Client.on_message(filters.command(["settings", "setting", "jumblesettings"]))
async def settings_cmd(client: Client, message: Message):
    if not await is_admin_or_owner(message.chat, message.from_user.id):
        return await message.reply_text("❌ Sirf group admins hi settings access kar sakte hain.")

    chat_id = message.chat.id
    caption, buttons = build_settings_card(chat_id, message.chat.title or "Group")
    await send_jumble_rich(client, chat_id, caption, buttons)


# Settings Callbacks
@Client.on_callback_query(filters.regex(r"^set_"))
async def settings_callback_router(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    chat_id = query.message.chat.id

    if not await is_admin_or_owner(query.message.chat, user_id):
        return await query.answer("❌ Sirf group admins settings change kar sakte hain!", show_alert=True)

    data = query.data.split("|")
    action = data[0]

    if action == "set_toggle_active":
        s = dict(get_settings(chat_id))
        new_val = 0 if s.get("is_active", 1) else 1
        DB.execute("UPDATE settings SET is_active=? WHERE chat_id=?", (new_val, chat_id))
        DB.commit()
        await query.answer(f"Game Status: {'Running' if new_val else 'Stopped'}")

    elif action == "set_toggle_autodel":
        s = dict(get_settings(chat_id))
        new_val = 0 if s.get("auto_delete", 0) else 1
        DB.execute("UPDATE settings SET auto_delete=? WHERE chat_id=?", (new_val, chat_id))
        DB.commit()
        await query.answer(f"Auto-Delete: {'Enabled' if new_val else 'Disabled'}")

    elif action == "set_diff":
        diff = data[1]
        DB.execute("UPDATE settings SET default_diff=? WHERE chat_id=?", (diff, chat_id))
        DB.commit()
        await query.answer(f"Mode set to {diff.upper()}")

    elif action == "set_menu_timers":
        caption, buttons = build_timers_card(chat_id)
        blocks = html_to_rich_blocks(caption)
        for r in buttons:
            blocks.append(types.InputRichBlockButtons(buttons=r))
        return await query.message.edit_rich_message(rich_message=types.InputRichMessage(blocks=blocks))

    elif action == "set_timer_val":
        diff = data[1]
        secs = int(data[2])
        DB.execute(f"UPDATE settings SET {diff}=? WHERE chat_id=?", (secs, chat_id))
        DB.commit()
        await query.answer(f"Timer set to {secs}s!")
        caption, buttons = build_timers_card(chat_id)
        blocks = html_to_rich_blocks(caption)
        for r in buttons:
            blocks.append(types.InputRichBlockButtons(buttons=r))
        return await query.message.edit_rich_message(rich_message=types.InputRichMessage(blocks=blocks))

    elif action == "set_close_panel":
        await query.message.delete()
        return await query.answer("Settings closed.")

    # Redraw Main Settings Page
    caption, buttons = build_settings_card(chat_id, query.message.chat.title or "Group")
    blocks = html_to_rich_blocks(caption)
    for r in buttons:
        blocks.append(types.InputRichBlockButtons(buttons=r))
    await query.message.edit_rich_message(rich_message=types.InputRichMessage(blocks=blocks))

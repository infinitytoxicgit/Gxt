from pyrogram import Client, filters, enums, types
from pyrogram.types import Message, CallbackQuery
from database import DB, get_settings, is_admin
from utils.rich import send_jumble_rich

def get_settings_panel(chat_id: int, chat_title: str = "Group"):
    s = dict(get_settings(chat_id))
    
    is_active = bool(s.get("is_active", 1))
    auto_del = bool(s.get("auto_delete", 0))
    cur_diff = str(s.get("default_diff", "medium")).lower()
    
    easy_t = s.get("easy", 120)
    med_t = s.get("medium", 300)
    hard_t = s.get("hard", 600)
    
    # Text Representation
    status_icon = "🟢 Running" if is_active else "🔴 Stopped"
    del_icon = "🟢 Enabled" if auto_del else "🔴 Disabled"
    
    caption = (
        "<blockquote><emoji id=5895705279416241926>⚙️</emoji> <u><b>𝐉ᴜᴍʙʟᴇ 𝐆ʀᴏᴜᴘ 𝐒ᴇᴛᴛɪɴɢs</b></u></blockquote>\n\n"
        "<blockquote expandable>"
        f"👥 <b>Group Title :</b> <code>{chat_title}</code>\n"
        f"🆔 <b>Chat ID :</b> <code>{chat_id}</code>\n\n"
        f"⚡ <b>Engine Status :</b> {status_icon}\n"
        f"🗑️ <b>Auto Delete :</b> {del_icon}\n"
        f"🎯 <b>Active Difficulty :</b> <code>{cur_diff.title()}</code>\n"
        f"⏱️ <b>Configured Timers :</b> Easy: <code>{easy_t}s</code> | Med: <code>{med_t}s</code> | Hard: <code>{hard_t}s</code>\n\n"
        "<i>Click below pill buttons to toggle states live!</i></blockquote>"
    )
    
    # Dynamic Button Colors: Green if ON / Active, Red if OFF / Inactive
    btn_status_style = enums.ButtonStyle.SUCCESS if is_active else enums.ButtonStyle.DANGER
    btn_status_text = "🟢 State: RUNNING" if is_active else "🔴 State: STOPPED"
    
    btn_del_style = enums.ButtonStyle.SUCCESS if auto_del else enums.ButtonStyle.DANGER
    btn_del_text = "🗑️ AutoDel: ON" if auto_del else "🗑️ AutoDel: OFF"

    buttons = [
        [
            types.RichMessageButton(
                text=btn_status_text,
                style=btn_status_style,
                callback_data=f"set_toggle_engine|{chat_id}",
            ),
            types.RichMessageButton(
                text=btn_del_text,
                style=btn_del_style,
                callback_data=f"set_toggle_autodel|{chat_id}",
            ),
        ],
        [
            types.RichMessageButton(
                text=f"{'🟢' if cur_diff=='easy' else '🔴'} Easy ({easy_t}s)",
                style=enums.ButtonStyle.SUCCESS if cur_diff == "easy" else enums.ButtonStyle.DANGER,
                callback_data=f"set_select_diff|easy|{chat_id}",
            ),
            types.RichMessageButton(
                text=f"{'🟢' if cur_diff=='medium' else '🔴'} Med ({med_t}s)",
                style=enums.ButtonStyle.SUCCESS if cur_diff == "medium" else enums.ButtonStyle.DANGER,
                callback_data=f"set_select_diff|medium|{chat_id}",
            ),
            types.RichMessageButton(
                text=f"{'🟢' if cur_diff=='hard' else '🔴'} Hard ({hard_t}s)",
                style=enums.ButtonStyle.SUCCESS if cur_diff == "hard" else enums.ButtonStyle.DANGER,
                callback_data=f"set_select_diff|hard|{chat_id}",
            ),
        ],
        [
            types.RichMessageButton(
                text="⏱️ Choose Timers",
                style=enums.ButtonStyle.PRIMARY,
                callback_data=f"set_submenu_timers|{chat_id}",
            )
        ]
    ]
    return caption, buttons

def get_timers_panel(chat_id: int):
    s = dict(get_settings(chat_id))
    cur_diff = s.get("default_diff", "medium")
    cur_t = s.get(cur_diff, 120)

    caption = (
        "<blockquote>⏱️ <u><b>𝐂𝐇𝐎𝐎𝐒𝐄 𝐑𝐎𝐔𝐍𝐃 𝐓𝐈𝐌𝐄𝐑𝐒</b></u></blockquote>\n\n"
        f"Mode: <code>{cur_diff.title()}</code> | Current: <code>{cur_t}s</code>\n"
        "<i>Green represents currently selected duration:</i>"
    )

    options = [30, 45, 60, 120, 300, 600]
    row1 = []
    row2 = []
    for opt in options[:3]:
        style = enums.ButtonStyle.SUCCESS if cur_t == opt else enums.ButtonStyle.DANGER
        row1.append(types.RichMessageButton(text=f"{'🟢' if cur_t==opt else '🔴'} {opt}s", style=style, callback_data=f"set_apply_timer|{cur_diff}|{opt}|{chat_id}"))
    for opt in options[3:]:
        style = enums.ButtonStyle.SUCCESS if cur_t == opt else enums.ButtonStyle.DANGER
        row2.append(types.RichMessageButton(text=f"{'🟢' if cur_t==opt else '🔴'} {opt}s", style=style, callback_data=f"set_apply_timer|{cur_diff}|{opt}|{chat_id}"))

    buttons = [
        row1,
        row2,
        [
            types.RichMessageButton(text="🔙 Back to Settings", style=enums.ButtonStyle.PRIMARY, callback_data=f"set_back_main|{chat_id}")
        ]
    ]
    return caption, buttons


# /settings Command Handler
@Client.on_message(filters.command(["settings", "setting", "jumblesettings"]))
async def settings_cmd(client: Client, message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return await message.reply_text("❌ Only Group Admins can open settings.")

    chat_id = message.chat.id
    caption, buttons = get_settings_panel(chat_id, message.chat.title or "Group")
    await send_jumble_rich(client, chat_id, caption, buttons)


# Settings Callbacks Processor
@Client.on_callback_query(filters.regex(r"^set_"))
async def settings_callbacks_handler(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    chat_id = query.message.chat.id
    
    if not await is_admin(chat_id, user_id):
        return await query.answer("❌ Only Admins can modify settings!", show_alert=True)

    data = query.data.split("|")
    action = data[0]

    if action == "set_toggle_engine":
        s = dict(get_settings(chat_id))
        new_val = 0 if s.get("is_active", 1) else 1
        DB.execute("UPDATE settings SET is_active=? WHERE chat_id=?", (new_val, chat_id))
        DB.commit()
        await query.answer(f"Engine set to {'Running' if new_val else 'Stopped'}")

    elif action == "set_toggle_autodel":
        s = dict(get_settings(chat_id))
        new_val = 0 if s.get("auto_delete", 0) else 1
        DB.execute("UPDATE settings SET auto_delete=? WHERE chat_id=?", (new_val, chat_id))
        DB.commit()
        await query.answer(f"Auto-Delete set to {'Enabled' if new_val else 'Disabled'}")

    elif action == "set_select_diff":
        diff = data[1]
        DB.execute("UPDATE settings SET default_diff=? WHERE chat_id=?", (diff, chat_id))
        DB.commit()
        await query.answer(f"Difficulty changed to {diff.upper()}")

    elif action == "set_submenu_timers":
        caption, buttons = get_timers_panel(chat_id)
        # Edit using Rich Message
        try:
            from utils.rich import html_to_rich_blocks
            blocks = html_to_rich_blocks(caption)
            for row in buttons:
                blocks.append(types.InputRichBlockButtons(buttons=row))
            return await query.message.edit_rich_message(rich_message=types.InputRichMessage(blocks=blocks))
        except Exception:
            return await query.answer("Opening timers...")

    elif action == "set_apply_timer":
        diff = data[1]
        secs = int(data[2])
        DB.execute(f"UPDATE settings SET {diff}=? WHERE chat_id=?", (secs, chat_id))
        DB.commit()
        await query.answer(f"Timer set to {secs}s for {diff.upper()}!")
        caption, buttons = get_timers_panel(chat_id)
        from utils.rich import html_to_rich_blocks
        blocks = html_to_rich_blocks(caption)
        for row in buttons:
            blocks.append(types.InputRichBlockButtons(buttons=row))
        return await query.message.edit_rich_message(rich_message=types.InputRichMessage(blocks=blocks))

    # Redraw Main Settings Page
    caption, buttons = get_settings_panel(chat_id, query.message.chat.title or "Group")
    from utils.rich import html_to_rich_blocks
    blocks = html_to_rich_blocks(caption)
    for row in buttons:
        blocks.append(types.InputRichBlockButtons(buttons=row))
    await query.message.edit_rich_message(rich_message=types.InputRichMessage(blocks=blocks))

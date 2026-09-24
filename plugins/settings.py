from pyrogram import Client, filters, enums, types
from pyrogram.types import Message, CallbackQuery
from database import DB, get_settings
from helpers import is_admin_or_owner
from utils.rich import send_jumble_rich, edit_jumble_rich


async def check_admin_safe(chat, user_id: int) -> bool:
    try:
        res = await is_admin_or_owner(chat, user_id)
        if res is not None:
            return bool(res)
    except TypeError:
        try:
            return bool(await is_admin_or_owner(chat.id, user_id))
        except Exception:
            pass
    except Exception:
        pass

    try:
        member = await chat.get_member(user_id)
        return member.status in (enums.ChatMemberStatus.OWNER, enums.ChatMemberStatus.ADMINISTRATOR)
    except Exception:
        return False


def build_settings_card(chat_id: int, chat_title: str):
    raw_s = get_settings(chat_id)
    s = dict(raw_s) if raw_s else {}

    is_active = bool(s.get("is_active", 1))
    auto_del = bool(s.get("auto_delete", 0))
    cur_diff = str(s.get("default_diff", "medium")).lower()

    easy_t = s.get("easy", 120)
    med_t = s.get("medium", 300)
    hard_t = s.get("hard", 600)

    st_text = "🟢 Running" if is_active else "🔴 Stopped"
    del_text = "🟢 Enabled" if auto_del else "🔴 Disabled"

    caption = (
        "<blockquote>⚙️ <u><b>JUMBLE GROUP SETTINGS</b></u></blockquote>\n\n"
        f"<blockquote>👥 <b>Group :</b> <code>{chat_title}</code>\n"
        f"🆔 <b>Chat ID :</b> <code>{chat_id}</code></blockquote>\n\n"
        f"<blockquote>⚡ <b>Game Status :</b> {st_text}\n"
        f"🗑️ <b>Auto Delete :</b> {del_text}\n"
        f"🎯 <b>Default Mode :</b> <code>{cur_diff.title()}</code>\n"
        f"⏱️ <b>Round Timers :</b> Easy: <code>{easy_t}s</code> | Med: <code>{med_t}s</code> | Hard: <code>{hard_t}s</code></blockquote>\n\n"
        "<blockquote><i>Tap buttons below to toggle options live:</i></blockquote>"
    )

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
                text="🟢 Easy" if cur_diff == "easy" else "🔴 Easy",
                style=enums.ButtonStyle.SUCCESS if cur_diff == "easy" else enums.ButtonStyle.DANGER,
                callback_data=f"set_diff|easy|{chat_id}",
            ),
            types.RichMessageButton(
                text="🟢 Medium" if cur_diff == "medium" else "🔴 Medium",
                style=enums.ButtonStyle.SUCCESS if cur_diff == "medium" else enums.ButtonStyle.DANGER,
                callback_data=f"set_diff|medium|{chat_id}",
            ),
            types.RichMessageButton(
                text="🟢 Hard" if cur_diff == "hard" else "🔴 Hard",
                style=enums.ButtonStyle.SUCCESS if cur_diff == "hard" else enums.ButtonStyle.DANGER,
                callback_data=f"set_diff|hard|{chat_id}",
            ),
        ],
        [
            types.RichMessageButton(
                text="⏱️ Choose Timers",
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
    cur_diff = str(s.get("default_diff", "medium")).lower()
    cur_val = int(s.get(cur_diff, 120))

    caption = (
        f"<blockquote>⏱️ <u><b>CHOOSE ROUND TIMERS ({cur_diff.upper()})</b></u></blockquote>\n\n"
        f"<blockquote>Selected Duration: <b>{cur_val}s</b>\n"
        f"Active timer is <b>Green</b>, others are <b>Red</b>. Tap to change:</blockquote>"
    )

    timer_choices = [30, 45, 60, 90, 120, 180, 300, 600]
    row1, row2, row3 = [], [], []

    for idx, opt in enumerate(timer_choices):
        is_selected = (cur_val == opt)
        style = enums.ButtonStyle.SUCCESS if is_selected else enums.ButtonStyle.DANGER
        label = f"🟢 {opt}s" if is_selected else f"🔴 {opt}s"
        btn = types.RichMessageButton(
            text=label,
            style=style,
            callback_data=f"set_timer_val|{cur_diff}|{opt}|{chat_id}"
        )
        if idx < 3:
            row1.append(btn)
        elif idx < 6:
            row2.append(btn)
        else:
            row3.append(btn)

    buttons = [
        row1,
        row2,
        row3,
        [
            types.RichMessageButton(
                text="🔙 Back to Settings",
                style=enums.ButtonStyle.PRIMARY,
                callback_data=f"set_back_main|{chat_id}"
            )
        ]
    ]
    return caption, buttons


# ============================================================
# COMMAND & CALLBACK ROUTER
# ============================================================

@Client.on_message(filters.command(["settings", "setting", "jumblesettings"]))
async def settings_cmd(client: Client, message: Message):
    if message.chat.type == enums.ChatType.PRIVATE:
        return await message.reply_text("ℹ️ `/settings` group ke andar use karein.")

    if not await check_admin_safe(message.chat, message.from_user.id):
        return await message.reply_text("❌ Sirf Group Admins settings access kar sakte hain.")

    chat_id = message.chat.id
    caption, buttons = build_settings_card(chat_id, message.chat.title or "Group")
    await send_jumble_rich(client, chat_id, caption, buttons)


@Client.on_callback_query(filters.regex(r"^set_"))
async def settings_callback_router(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    chat_id = query.message.chat.id

    if not await check_admin_safe(query.message.chat, user_id):
        return await query.answer("❌ Sirf group admins hi click kar sakte hain!", show_alert=True)

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
        await query.answer(f"Auto-Delete: {'ON' if new_val else 'OFF'}")

    elif action == "set_diff":
        diff = data[1]
        DB.execute("UPDATE settings SET default_diff=? WHERE chat_id=?", (diff, chat_id))
        DB.commit()
        await query.answer(f"Mode set to: {diff.upper()}")

    elif action == "set_menu_timers":
        caption, buttons = build_timers_card(chat_id)
        await query.answer()
        return await edit_jumble_rich(client, chat_id, query.message.id, caption, buttons)

    elif action == "set_timer_val":
        diff = data[1]
        secs = int(data[2])
        DB.execute(f"UPDATE settings SET {diff}=? WHERE chat_id=?", (secs, chat_id))
        DB.commit()
        await query.answer(f"{diff.upper()} Timer: {secs}s!")
        caption, buttons = build_timers_card(chat_id)
        return await edit_jumble_rich(client, chat_id, query.message.id, caption, buttons)

    elif action == "set_back_main":
        await query.answer()

    elif action == "set_close_panel":
        await query.message.delete()
        return await query.answer("Closed!")

    # Redraw Main Settings Page
    caption, buttons = build_settings_card(chat_id, query.message.chat.title or "Group")
    await edit_jumble_rich(client, chat_id, query.message.id, caption, buttons)

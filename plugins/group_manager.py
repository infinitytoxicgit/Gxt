import asyncio
import time
from pyrogram import Client, filters, enums
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from config import OWNER_ID
from database import DB, get_settings
from helpers import is_owner, is_authed
from plugins.game_core import start_game

# ============================================================
# DATA FETCHERS
# ============================================================

def get_groups_by_status(is_active_flag: int):
    """0 = Inactive / Stopped, 1 = Active / Playing"""
    try:
        rows = DB.execute("""
            SELECT chat_id, default_diff, auto_delete 
            FROM settings 
            WHERE chat_id < 0 AND is_active = ?
            ORDER BY chat_id ASC
        """, (is_active_flag,)).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []

def get_group_counts():
    try:
        act = DB.execute("SELECT COUNT(*) FROM settings WHERE chat_id < 0 AND is_active = 1").fetchone()
        inact = DB.execute("SELECT COUNT(*) FROM settings WHERE chat_id < 0 AND is_active = 0").fetchone()
        return (act[0] if act else 0), (inact[0] if inact else 0)
    except Exception:
        return 0, 0

# ============================================================
# CHART & PANEL BUILDER
# ============================================================

def build_global_settings_view(view_mode: str = "inactive", page: int = 1):
    active_count, inactive_count = get_group_counts()
    
    flag = 0 if view_mode == "inactive" else 1
    target_groups = get_groups_by_status(flag)
    total_items = len(target_groups)

    # 5 groups per page
    per_page = 5
    total_pages = max(1, (total_items + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    current_batch = target_groups[start_idx:end_idx]

    mode_title = "🔴 IDLING / STOPPED GROUPS" if flag == 0 else "🟢 ACTIVE PLAYING GROUPS"

    caption = (
        f"<blockquote>🎛️ <u><b>GLOBAL GROUP ENGINE SETTINGS</b></u>\n"
        f"<i>Managing Category: <b>{mode_title}</b></i></blockquote>\n\n"
        f"<blockquote>📊 <b>DATABASE OVERVIEW :</b>\n"
        f"• 🟢 <b>Total Active Groups :</b> <code>{active_count}</code>\n"
        f"• 🔴 <b>Total Inactive Groups :</b> <code>{inactive_count}</code>\n"
        f"• 📑 <b>Page :</b> <code>{page}/{total_pages}</code></blockquote>\n\n"
    )

    caption += f"<blockquote>📋 <b>GROUPS ROSTER ({mode_title}) :</b>\n"
    if not current_batch:
        caption += "• <i>Is category me koi group nahi mila!</i></blockquote>"
    else:
        for idx, g in enumerate(current_batch, start=start_idx + 1):
            del_icon = "🟢 ON" if g.get("auto_delete") else "🔴 OFF"
            diff = str(g.get("default_diff", "medium")).title()
            st_text = "🟢 Active" if flag == 1 else "🔴 Stopped"
            caption += (
                f"<b>{idx}.</b> ID: <code>{g['chat_id']}</code>\n"
                f"   ├ Mode: <code>{diff}</code> | Auto-Del: <code>{del_icon}</code>\n"
                f"   └ State: <b>{st_text}</b>\n"
            )
        caption += "</blockquote>\n\n"

    caption += (
        "<blockquote>⚡ <b>ONE-CLICK ACTION GUIDE :</b>\n"
        "• <b>Auto-Start :</b> Selected category groups ko instantly start karega.\n"
        "• <b>Stop All :</b> Selected category ke chalte games ko rok dega.\n"
        "• <b>Auto-Del :</b> Bulk me auto-delete ON/OFF toggle karega.</blockquote>"
    )

    # Category Switcher Buttons
    switch_act_btn = InlineKeyboardButton(f"{'✅ ' if flag==1 else ''}🟢 Active ({active_count})", callback_data="mgr_switch_active_1")
    switch_inact_btn = InlineKeyboardButton(f"{'✅ ' if flag==0 else ''}🔴 Inactive ({inactive_count})", callback_data="mgr_switch_inactive_1")

    # Mass Action Buttons
    if flag == 0:
        action_btn1 = InlineKeyboardButton(f"🚀 Start All ({total_items})", callback_data="mgr_action_start_all")
        action_btn2 = InlineKeyboardButton("🗑️ Auto-Del ON (All)", callback_data="mgr_action_autodel_on")
    else:
        action_btn1 = InlineKeyboardButton(f"⏹️ Stop All ({total_items})", callback_data="mgr_action_stop_all")
        action_btn2 = InlineKeyboardButton("🗑️ Auto-Del OFF (All)", callback_data="mgr_action_autodel_off")

    kb = [
        [switch_inact_btn, switch_act_btn],
        [action_btn1, action_btn2],
        [
            InlineKeyboardButton("🎯 Easy All", callback_data=f"mgr_setmode_easy_{view_mode}"),
            InlineKeyboardButton("🎯 Medium All", callback_data=f"mgr_setmode_medium_{view_mode}"),
            InlineKeyboardButton("🎯 Hard All", callback_data=f"mgr_setmode_hard_{view_mode}")
        ],
        [
            InlineKeyboardButton("⬅️ Prev", callback_data=f"mgr_page_{view_mode}_{page - 1}"),
            InlineKeyboardButton(f"📄 {page}/{total_pages}", callback_data="mgr_noop"),
            InlineKeyboardButton("Next ➡️", callback_data=f"mgr_page_{view_mode}_{page + 1}")
        ],
        [
            InlineKeyboardButton("🔄 Refresh", callback_data=f"mgr_page_{view_mode}_{page}"),
            InlineKeyboardButton("❌ Close", callback_data="mgr_close")
        ]
    ]

    return caption, InlineKeyboardMarkup(kb)

# ============================================================
# COMMAND HANDLER: /setglobalsettings & /inactivegroups
# ============================================================

@Client.on_message(filters.command(["setglobalsettings", "globalsettings", "inactivegroups", "idlegroups"], prefixes=["/", "!", "."]))
async def global_settings_cmd(client: Client, message: Message):
    if not message.from_user:
        return

    uid = message.from_user.id
    if int(uid) != int(OWNER_ID) and not is_owner(uid) and not is_authed(uid):
        return await message.reply_text(
            "<blockquote>❌ <b>Access Denied :</b> Only Owner & Authorized Admins can open Global Group Settings.</blockquote>",
            parse_mode=enums.ParseMode.HTML
        )

    # Check argument: /setglobalsettings active  ya  /setglobalsettings inactive
    args = message.command[1:] if len(message.command) > 1 else []
    view_mode = "inactive"
    if args and "act" in args[0].lower() and "inact" not in args[0].lower():
        view_mode = "active"

    caption, markup = build_global_settings_view(view_mode=view_mode, page=1)
    await message.reply_text(caption, reply_markup=markup, parse_mode=enums.ParseMode.HTML)

# ============================================================
# CALLBACK ROUTER
# ============================================================

@Client.on_callback_query(filters.regex(r"^mgr_"))
async def global_settings_callback(client: Client, query: CallbackQuery):
    uid = query.from_user.id
    if int(uid) != int(OWNER_ID) and not is_owner(uid) and not is_authed(uid):
        return await query.answer("❌ You are not authorized!", show_alert=True)

    data = query.data

    if data == "mgr_close":
        try:
            await query.message.delete()
        except Exception:
            pass
        return await query.answer("Panel closed.")

    if data == "mgr_noop":
        return await query.answer("Page indicator", show_alert=False)

    # Category Switch
    if data.startswith("mgr_switch_"):
        target_mode = data.split("_")[2]
        caption, markup = build_global_settings_view(view_mode=target_mode, page=1)
        try:
            await query.message.edit_text(caption, reply_markup=markup, parse_mode=enums.ParseMode.HTML)
        except Exception:
            pass
        return await query.answer()

    # Pagination
    if data.startswith("mgr_page_"):
        parts = data.split("_")
        mode = parts[2]
        page_num = int(parts[3])
        caption, markup = build_global_settings_view(view_mode=mode, page=page_num)
        try:
            await query.message.edit_text(caption, reply_markup=markup, parse_mode=enums.ParseMode.HTML)
        except Exception:
            pass
        return await query.answer()

    # Bulk Mode Change
    if data.startswith("mgr_setmode_"):
        parts = data.split("_")
        diff = parts[2]
        target_mode = parts[3]
        flag = 0 if target_mode == "inactive" else 1

        DB.execute("UPDATE settings SET default_diff = ? WHERE chat_id < 0 AND is_active = ?", (diff, flag))
        DB.commit()
        await query.answer(f"✅ Mode set to {diff.title()} for all {target_mode} groups!", show_alert=True)
        
        caption, markup = build_global_settings_view(view_mode=target_mode, page=1)
        try:
            await query.message.edit_text(caption, reply_markup=markup, parse_mode=enums.ParseMode.HTML)
        except Exception:
            pass
        return

    # Bulk Auto-Delete ON for Inactive
    if data == "mgr_action_autodel_on":
        DB.execute("UPDATE settings SET auto_delete = 1 WHERE chat_id < 0 AND is_active = 0")
        DB.commit()
        await query.answer("✅ Auto-Delete set to ON for all Inactive groups!", show_alert=True)
        caption, markup = build_global_settings_view(view_mode="inactive", page=1)
        try:
            await query.message.edit_text(caption, reply_markup=markup, parse_mode=enums.ParseMode.HTML)
        except Exception:
            pass
        return

    # Bulk Auto-Delete OFF for Active
    if data == "mgr_action_autodel_off":
        DB.execute("UPDATE settings SET auto_delete = 0 WHERE chat_id < 0 AND is_active = 1")
        DB.commit()
        await query.answer("✅ Auto-Delete turned OFF for all Active groups!", show_alert=True)
        caption, markup = build_global_settings_view(view_mode="active", page=1)
        try:
            await query.message.edit_text(caption, reply_markup=markup, parse_mode=enums.ParseMode.HTML)
        except Exception:
            pass
        return

    # Stop All Active Groups
    if data == "mgr_action_stop_all":
        DB.execute("UPDATE settings SET is_active = 0 WHERE chat_id < 0 AND is_active = 1")
        DB.commit()
        await query.answer("⏹️ Stopped all active groups!", show_alert=True)
        caption, markup = build_global_settings_view(view_mode="inactive", page=1)
        try:
            await query.message.edit_text(caption, reply_markup=markup, parse_mode=enums.ParseMode.HTML)
        except Exception:
            pass
        return

    # Start All Inactive Groups
    if data == "mgr_action_start_all":
        groups = get_groups_by_status(0)
        if not groups:
            return await query.answer("⚠️ No inactive groups found to start!", show_alert=True)

        await query.answer("🚀 Starting all stopped groups in background...", show_alert=False)

        DB.execute("UPDATE settings SET is_active = 1, auto_delete = 1 WHERE chat_id < 0 AND is_active = 0")
        DB.commit()

        asyncio.create_task(run_mass_starter(client, groups))

        await query.message.reply_text(
            f"<blockquote>🚀 <b>MASS START INITIATED!</b>\n\n"
            f"• <b>Groups Starting :</b> <code>{len(groups)}</code>\n"
            f"• <b>Auto-Delete :</b> 🟢 <b>ON</b>\n"
            f"• <b>Active Groups :</b> 🟢 <b>Safe</b>\n\n"
            f"Puzzles are being dispatched (0.5s interval).</blockquote>",
            parse_mode=enums.ParseMode.HTML
        )

        caption, markup = build_global_settings_view(view_mode="active", page=1)
        try:
            await query.message.edit_text(caption, reply_markup=markup, parse_mode=enums.ParseMode.HTML)
        except Exception:
            pass
        return

# Background Dispatcher
async def run_mass_starter(client: Client, groups: list):
    for g in groups:
        chat_id = g["chat_id"]
        diff = g.get("default_diff") or "medium"
        try:
            DB.execute("DELETE FROM games WHERE chat_id = ?", (chat_id,))
            DB.commit()
            await start_game(client, chat_id, diff, chat_id)
            await asyncio.sleep(0.5)
        except Exception as e:
            print(f"[Mass Start Err: {chat_id}] {e}")

import asyncio
import time
from pyrogram import Client, filters, enums, types
from pyrogram.types import Message, CallbackQuery
from config import OWNER_ID
from database import DB, get_settings
from helpers import is_owner, is_authed
from plugins.game_core import start_game
from utils.rich import send_jumble_rich, edit_jumble_rich

# ============================================================
# DATA FETCHERS FOR INACTIVE GROUPS
# ============================================================

def get_inactive_groups_list():
    """Sirf un groups ko nikalega jahan game stopped (is_active = 0) hai"""
    try:
        rows = DB.execute("""
            SELECT chat_id, default_diff, auto_delete 
            FROM settings 
            WHERE chat_id < 0 AND is_active = 0
            ORDER BY chat_id ASC
        """).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []

def get_active_groups_count():
    try:
        row = DB.execute("SELECT COUNT(*) FROM settings WHERE chat_id < 0 AND is_active = 1").fetchone()
        return row[0] if row else 0
    except Exception:
        return 0

# ============================================================
# RICH PANEL BUILDER
# ============================================================

def build_inactive_manager_view(page: int = 1):
    inactive_groups = get_inactive_groups_list()
    active_count = get_active_groups_count()
    total_inactive = len(inactive_groups)

    # Pagination: 1 page par 5 groups ka control chart
    per_page = 5
    total_pages = max(1, (total_inactive + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    current_batch = inactive_groups[start_idx:end_idx]

    caption = (
        "<blockquote>🎛️ <u><b>𝐈𝐃𝐋𝐈𝐍𝐆 𝐆𝐑𝐎𝐔𝐏𝐒 𝐌𝐀𝐒𝐒 𝐌𝐀𝐍𝐀𝐆𝐄𝐑</b></u>\n"
        "<i>Selective batch launcher & control for stopped groups</i></blockquote>\n\n"
        "<blockquote>📊 <b>STATUS OVERVIEW :</b>\n"
        f"• 🟢 <b>Currently Active Groups :</b> <code>{active_count}</code> (Untouched)\n"
        f"• 🔴 <b>Stopped / Idling Groups :</b> <code>{total_inactive}</code>\n"
        f"• 📄 <b>Displaying Page :</b> <code>{page}/{total_pages}</code></blockquote>\n\n"
    )

    caption += "<blockquote>📋 <b>IDLING GROUPS ROSTER :</b>\n"
    if not current_batch:
        caption += "• <i>Sabhi groups me game already chal raha hai!</i></blockquote>"
    else:
        for idx, g in enumerate(current_batch, start=start_idx + 1):
            del_icon = "🟢 ON" if g.get("auto_delete") else "🔴 OFF"
            mode = str(g.get("default_diff", "medium")).title()
            caption += (
                f"<b>{idx}.</b> ID: <code>{g['chat_id']}</code>\n"
                f"   ├ Mode: <code>{mode}</code> | Auto-Del: <code>{del_icon}</code>\n"
                f"   └ Status: 🔴 <b>Stopped</b>\n"
            )
        caption += "</blockquote>\n\n"

    caption += (
        "<blockquote>⚡ <b>MASS ACTIONS GUIDE :</b>\n"
        "• <b>Start All Inactive :</b> Idling groups ko unke current mode me start karega.\n"
        "• <b>Auto-Del All ON :</b> Idling groups ka Auto-Delete turant ON kar dega.\n"
        "• <b>Set Mode All :</b> Sirf idling groups ka default difficulty set karega.</blockquote>"
    )

    # Interactive Rich Buttons
    buttons = [
        # Global Quick Launchers for Inactive Groups
        [
            types.RichMessageButton(
                text=f"🚀 Auto-Start All ({total_inactive})",
                style=enums.ButtonStyle.SUCCESS,
                callback_data="mass_start_all_inactive"
            ),
            types.RichMessageButton(
                text="🗑️ Auto-Del ON (All)",
                style=enums.ButtonStyle.PRIMARY,
                callback_data="mass_autodel_on_inactive"
            )
        ],
        [
            types.RichMessageButton(
                text="🎯 Easy All",
                style=enums.ButtonStyle.SECONDARY,
                callback_data="mass_mode_easy"
            ),
            types.RichMessageButton(
                text="🎯 Medium All",
                style=enums.ButtonStyle.SECONDARY,
                callback_data="mass_mode_medium"
            ),
            types.RichMessageButton(
                text="🎯 Hard All",
                style=enums.ButtonStyle.SECONDARY,
                callback_data="mass_mode_hard"
            )
        ],
        # Pagination Bar
        [
            types.RichMessageButton(
                text="⬅️ Previous",
                style=enums.ButtonStyle.PRIMARY,
                callback_data=f"page_inactive_{page - 1}"
            ),
            types.RichMessageButton(
                text=f"📄 {page}/{total_pages}",
                style=enums.ButtonStyle.SECONDARY,
                callback_data="noop_inactive"
            ),
            types.RichMessageButton(
                text="Next ➡️",
                style=enums.ButtonStyle.PRIMARY,
                callback_data=f"page_inactive_{page + 1}"
            )
        ],
        [
            types.RichMessageButton(
                text="🔄 Refresh List",
                style=enums.ButtonStyle.SUCCESS,
                callback_data=f"page_inactive_{page}"
            ),
            types.RichMessageButton(
                text="❌ Close Panel",
                style=enums.ButtonStyle.DANGER,
                callback_data="close_inactive_panel"
            )
        ]
    ]

    return caption, buttons

# ============================================================
# COMMAND HANDLERS
# ============================================================

@Client.on_message(filters.command(["inactivegroups", "idlegroups", "massstart", "startidle"], prefixes=["/", "!", "."]))
async def idle_groups_manager_cmd(client: Client, message: Message):
    if not message.from_user:
        return

    uid = message.from_user.id
    if int(uid) != int(OWNER_ID) and not is_owner(uid) and not is_authed(uid):
        return await message.reply_text(
            "<blockquote>❌ <b>Access Denied :</b> Only Owner & Authorized Admins can manage idling groups.</blockquote>",
            parse_mode=enums.ParseMode.HTML
        )

    caption, buttons = build_inactive_manager_view(page=1)
    await send_jumble_rich(client, message.chat.id, caption, rich_buttons_rows=buttons)

# ============================================================
# CALLBACK ROUTER FOR INACTIVE GROUPS MANAGEMENT
# ============================================================

@Client.on_callback_query(filters.regex(r"^(mass_|page_inactive_|close_inactive_panel|noop_inactive)"))
async def inactive_groups_callback(client: Client, query: CallbackQuery):
    uid = query.from_user.id
    if int(uid) != int(OWNER_ID) and not is_owner(uid) and not is_authed(uid):
        return await query.answer("❌ You are not authorized to perform mass group operations!", show_alert=True)

    data = query.data

    if data == "close_inactive_panel":
        try:
            await query.message.delete()
        except Exception:
            pass
        return await query.answer("Panel closed.")

    if data == "noop_inactive":
        return await query.answer("Pagination counter", show_alert=False)

    # Page Navigation
    if data.startswith("page_inactive_"):
        page_num = int(data.split("_")[2])
        caption, buttons = build_inactive_manager_view(page=page_num)
        try:
            await edit_jumble_rich(client, query.message.chat.id, query.message.id, caption, rich_buttons_rows=buttons)
        except Exception:
            pass
        return await query.answer()

    # 1. Mass Auto-Delete ON for Inactive Groups
    if data == "mass_autodel_on_inactive":
        DB.execute("UPDATE settings SET auto_delete = 1 WHERE chat_id < 0 AND is_active = 0")
        DB.commit()
        await query.answer("✅ Auto-Delete ON set for all idling groups!", show_alert=True)
        caption, buttons = build_inactive_manager_view(page=1)
        try:
            await edit_jumble_rich(client, query.message.chat.id, query.message.id, caption, rich_buttons_rows=buttons)
        except Exception:
            pass
        return

    # 2. Mass Mode Change for Inactive Groups
    if data.startswith("mass_mode_"):
        mode = data.split("_")[2]
        DB.execute("UPDATE settings SET default_diff = ? WHERE chat_id < 0 AND is_active = 0", (mode,))
        DB.commit()
        await query.answer(f"✅ Mode set to {mode.title()} for all idling groups!", show_alert=True)
        caption, buttons = build_inactive_manager_view(page=1)
        try:
            await edit_jumble_rich(client, query.message.chat.id, query.message.id, caption, rich_buttons_rows=buttons)
        except Exception:
            pass
        return

    # 3. Mass Auto-Start All Inactive Groups (Running 3 Groups safe rahenge)
    if data == "mass_start_all_inactive":
        inactive_groups = get_inactive_groups_list()
        if not inactive_groups:
            return await query.answer("⚠️ No stopped groups found to launch!", show_alert=True)

        await query.answer("🚀 Launching puzzles in all idling groups...", show_alert=False)

        # Database me state update karein aur auto_delete ko ensure karein
        DB.execute("UPDATE settings SET is_active = 1, auto_delete = 1 WHERE chat_id < 0 AND is_active = 0")
        DB.commit()

        # Background task me sequence se launch karein taaki Telegram flood wait na aaye
        asyncio.create_task(background_mass_starter(client, inactive_groups))

        await query.message.reply_text(
            f"<blockquote>🚀 <b>MASS LAUNCH INITIATED!</b>\n\n"
            f"• <b>Total Targets :</b> <code>{len(inactive_groups)} groups</code>\n"
            f"• <b>Auto-Delete :</b> 🟢 <b>ON</b>\n"
            f"• <b>Active Groups :</b> 🟢 <b>Safe & Untouched</b>\n\n"
            f"Puzzles are being dispatched sequentially (0.5s interval).</blockquote>",
            parse_mode=enums.ParseMode.HTML
        )

        caption, buttons = build_inactive_manager_view(page=1)
        try:
            await edit_jumble_rich(client, query.message.chat.id, query.message.id, caption, rich_buttons_rows=buttons)
        except Exception:
            pass
        return

# Background Worker to safely spawn puzzles
async def background_mass_starter(client: Client, groups: list):
    for g in groups:
        chat_id = g["chat_id"]
        diff = g.get("default_diff") or "medium"
        try:
            DB.execute("DELETE FROM games WHERE chat_id = ?", (chat_id,))
            DB.commit()
            await start_game(client, chat_id, diff, chat_id)
            await asyncio.sleep(0.5)
        except Exception as e:
            print(f"[Mass Start Error for {chat_id}]: {e}")

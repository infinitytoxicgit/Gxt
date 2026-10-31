import json
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from config import OWNER_ID
from helpers import is_owner, is_authed
from database import DB, get_global_config

# Helper: Set global config in DB
def set_global_config(key: str, value):
    try:
        DB.execute("""
            INSERT INTO global_config (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """, (str(key), str(value)))
        DB.commit()
        return True
    except Exception as e:
        print(f"[Set Config Error]: {e}")
        return False

# Security check: Owner or Authed Admin
def is_privileged_user(user_id: int) -> bool:
    try:
        if int(user_id) == int(OWNER_ID):
            return True
    except Exception:
        pass
    try:
        if is_owner(user_id) or is_authed(user_id):
            return True
    except Exception:
        pass
    return False


# 1. Command: Change Item Price
# Usage: /setshopprice stars2x 300  OR  /setshopprice exp2x 350
@Client.on_message(filters.command(["setshopprice", "setprice"], prefixes=["/", "!", "."]), group=-1)
async def set_shop_price_cmd(client: Client, message: Message):
    if not message.from_user or not is_privileged_user(message.from_user.id):
        return await message.reply_text("❌ <b>Access Denied :</b> Only Owner/Admins can configure shop prices.", parse_mode=enums.ParseMode.HTML)

    args = message.text.strip().split()
    if len(args) < 3:
        return await message.reply_text(
            "<blockquote>💰 <b>SET SHOP PRICE :</b>\n\n"
            "• <code>/setshopprice stars2x &lt;amount&gt;</code>\n"
            "• <code>/setshopprice exp2x &lt;amount&gt;</code>\n\n"
            "<b>Example :</b> <code>/setshopprice stars2x 300</code></blockquote>",
            parse_mode=enums.ParseMode.HTML
        )

    item = args[1].lower()
    try:
        price = int(args[2])
        if price < 0:
            return await message.reply_text("❌ Price negative nahi ho sakta!")
    except ValueError:
        return await message.reply_text("❌ Valid numeric price enter karein!")

    if item in ["stars2x", "stars", "2x_stars"]:
        set_global_config("shop_stars2x_price", price)
        item_name = "2x Stars Booster"
    elif item in ["exp2x", "exp", "2x_exp"]:
        set_global_config("shop_exp2x_price", price)
        item_name = "2x EXP Booster"
    else:
        return await message.reply_text("❌ Unknown item! Valid items: <code>stars2x</code>, <code>exp2x</code>", parse_mode=enums.ParseMode.HTML)

    await message.reply_text(
        f"<blockquote>✅ <b>Price Updated!</b>\n\n"
        f"🛍️ <b>Item :</b> {item_name}\n"
        f"⭐ <b>New Price :</b> <code>{price}</code> Stars</blockquote>",
        parse_mode=enums.ParseMode.HTML
    )


# 2. Command: Change Booster Duration (in minutes)
# Usage: /setshopdur stars2x 60  OR  /setshopdur exp2x 120
@Client.on_message(filters.command(["setshopdur", "setduration"], prefixes=["/", "!", "."]), group=-1)
async def set_shop_duration_cmd(client: Client, message: Message):
    if not message.from_user or not is_privileged_user(message.from_user.id):
        return await message.reply_text("❌ <b>Access Denied :</b> Only Owner/Admins can configure booster durations.", parse_mode=enums.ParseMode.HTML)

    args = message.text.strip().split()
    if len(args) < 3:
        return await message.reply_text(
            "<blockquote>⏳ <b>SET BOOSTER DURATION :</b>\n\n"
            "• <code>/setshopdur stars2x &lt;minutes&gt;</code>\n"
            "• <code>/setshopdur exp2x &lt;minutes&gt;</code>\n\n"
            "<b>Example :</b> <code>/setshopdur stars2x 60</code> (for 1 hour)</blockquote>",
            parse_mode=enums.ParseMode.HTML
        )

    item = args[1].lower()
    try:
        minutes = int(args[2])
        if minutes <= 0:
            return await message.reply_text("❌ Duration kam se kam 1 minute honi chahiye!")
    except ValueError:
        return await message.reply_text("❌ Valid numeric minutes enter karein!")

    duration_secs = minutes * 60

    if item in ["stars2x", "stars", "2x_stars"]:
        set_global_config("shop_stars2x_duration", duration_secs)
        item_name = "2x Stars Booster"
    elif item in ["exp2x", "exp", "2x_exp"]:
        set_global_config("shop_exp2x_duration", duration_secs)
        item_name = "2x EXP Booster"
    else:
        return await message.reply_text("❌ Unknown item! Valid items: <code>stars2x</code>, <code>exp2x</code>", parse_mode=enums.ParseMode.HTML)

    await message.reply_text(
        f"<blockquote>✅ <b>Duration Updated!</b>\n\n"
        f"🛍️ <b>Item :</b> {item_name}\n"
        f"⏳ <b>New Validity :</b> <code>{minutes}</code> Minutes ({duration_secs}s)</blockquote>",
        parse_mode=enums.ParseMode.HTML
    )


# 3. Command: Enable / Disable (Add / Remove) Items from Shop
# Usage: /toggleshop stars2x  OR  /toggleshop exp2x
@Client.on_message(filters.command(["toggleshop", "itemstatus"], prefixes=["/", "!", "."]), group=-1)
async def toggle_shop_item_cmd(client: Client, message: Message):
    if not message.from_user or not is_privileged_user(message.from_user.id):
        return await message.reply_text("❌ <b>Access Denied :</b> Only Owner/Admins can modify shop items.", parse_mode=enums.ParseMode.HTML)

    args = message.text.strip().split()
    if len(args) < 2:
        return await message.reply_text(
            "<blockquote>🔄 <b>TOGGLE SHOP ITEMS (ADD/REMOVE) :</b>\n\n"
            "• <code>/toggleshop stars2x</code>\n"
            "• <code>/toggleshop exp2x</code></blockquote>",
            parse_mode=enums.ParseMode.HTML
        )

    item = args[1].lower()
    if item in ["stars2x", "stars", "2x_stars"]:
        cfg_key = "shop_stars2x_enabled"
        name = "2x Stars Booster"
    elif item in ["exp2x", "exp", "2x_exp"]:
        cfg_key = "shop_exp2x_enabled"
        name = "2x EXP Booster"
    else:
        return await message.reply_text("❌ Unknown item! Valid items: <code>stars2x</code>, <code>exp2x</code>", parse_mode=enums.ParseMode.HTML)

    current_status = str(get_global_config(cfg_key, "true")).lower() == "true"
    new_status = not current_status
    set_global_config(cfg_key, "true" if new_status else "false")

    status_str = "🟢 <b>VISIBLE IN SHOP (Added)</b>" if new_status else "🔴 <b>HIDDEN FROM SHOP (Removed)</b>"
    await message.reply_text(
        f"<blockquote>🛍️ <b>Item Visibility Changed :</b>\n\n"
        f"📦 <b>Item :</b> {name}\n"
        f"📊 <b>Status :</b> {status_str}</blockquote>",
        parse_mode=enums.ParseMode.HTML
    )


# 4. Command: View Current Shop Settings & Inventory
# Usage: /shopcfg
@Client.on_message(filters.command(["shopcfg", "shopsettings"], prefixes=["/", "!", "."]), group=-1)
async def view_shop_config_cmd(client: Client, message: Message):
    if not message.from_user or not is_privileged_user(message.from_user.id):
        return await message.reply_text("❌ <b>Access Denied!</b>", parse_mode=enums.ParseMode.HTML)

    stars_cost = get_global_config("shop_stars2x_price", 200)
    stars_dur = int(get_global_config("shop_stars2x_duration", 3600)) // 60
    stars_enabled = "🟢 Active" if str(get_global_config("shop_stars2x_enabled", "true")).lower() == "true" else "🔴 Disabled"

    exp_cost = get_global_config("shop_exp2x_price", 250)
    exp_dur = int(get_global_config("shop_exp2x_duration", 3600)) // 60
    exp_enabled = "🟢 Active" if str(get_global_config("shop_exp2x_enabled", "true")).lower() == "true" else "🔴 Disabled"

    text = (
        "<blockquote>⚙️ <u><b>CURRENT SHOP CONFIGURATION</b></u></blockquote>\n\n"
        f"⭐ <b>2x Stars Booster :</b>\n"
        f"• Status: {stars_enabled}\n"
        f"• Price: <code>{stars_cost}</code> Stars\n"
        f"• Duration: <code>{stars_dur}</code> Mins\n\n"
        f"⚡ <b>2x EXP Booster :</b>\n"
        f"• Status: {exp_enabled}\n"
        f"• Price: <code>{exp_cost}</code> Stars\n"
        f"• Duration: <code>{exp_dur}</code> Mins\n\n"
        "<blockquote>💡 <i>Use <code>/setshopprice</code>, <code>/setshopdur</code>, and <code>/toggleshop</code> to edit.</i></blockquote>"
    )
    await message.reply_text(text, parse_mode=enums.ParseMode.HTML)

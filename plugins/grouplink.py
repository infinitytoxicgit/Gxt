from pyrogram import Client, filters, enums
from pyrogram.types import Message, LinkPreviewOptions
from config import OWNER_ID
from helpers import is_owner, is_authed

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


@Client.on_message(filters.command(["link", "invitelink", "getlink"], prefixes=["/", "!", "."]), group=-1)
async def generate_group_link_cmd(client: Client, message: Message):
    if not message.from_user:
        return

    user_id = message.from_user.id
    if not is_privileged_user(user_id):
        return await message.reply_text(
            "<blockquote>❌ <b>Access Denied :</b> Only Owner & Authorized Admins can generate group links.</blockquote>",
            parse_mode=enums.ParseMode.HTML
        )

    tokens = message.text.strip().split()
    target_chat_id = None

    if len(tokens) >= 2:
        try:
            target_chat_id = int(tokens[1])
        except ValueError:
            return await message.reply_text("❌ Valid numeric Group ID enter karein! (e.g. <code>/link -1001234567890</code>)", parse_mode=enums.ParseMode.HTML)
    else:
        # Agar ID nahi di aur group me likha hai to current group ka nikalega
        if message.chat.type in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP):
            target_chat_id = message.chat.id
        else:
            return await message.reply_text(
                "<blockquote>🔗 <b>GROUP LINK GENERATOR :</b>\n\n"
                "• <b>Usage in DM :</b> <code>/link &lt;group_id&gt;</code>\n"
                "• <b>Usage in Group :</b> <code>/link</code></blockquote>",
                parse_mode=enums.ParseMode.HTML
            )

    status_msg = await message.reply_text("⚡ <i>Fetching / Generating invite link...</i>", parse_mode=enums.ParseMode.HTML)

    try:
        chat = await client.get_chat(target_chat_id)
        invite_link = None

        # 1. Public Username link
        if chat.username:
            invite_link = f"https://t.me/{chat.username}"

        # 2. Primary existing invite link
        elif chat.invite_link:
            invite_link = chat.invite_link

        # 3. Export new invite link agar bot ke paas admin rights hain
        else:
            try:
                invite_link = await client.export_chat_invite_link(target_chat_id)
            except Exception:
                # Agar export fail ho toh create_chat_invite_link try karega
                created = await client.create_chat_invite_link(target_chat_id)
                invite_link = created.invite_link

        title = getattr(chat, "title", "Unknown Group")
        members = getattr(chat, "members_count", 0)

        response_text = (
            f"<blockquote>🔗 <u><b>GROUP INVITE LINK</b></u></blockquote>\n\n"
            f"🏰 <b>Title :</b> <b>{title}</b>\n"
            f"🆔 <b>Chat ID :</b> <code>{target_chat_id}</code>\n"
            f"👥 <b>Members :</b> <code>{members}</code>\n\n"
            f"🌐 <b>Invite URL :</b>\n👉 {invite_link}"
        )

        # Pyrogram v2+ support: link_preview_options se preview disable kiya gaya hai
        await status_msg.edit_text(
            response_text,
            parse_mode=enums.ParseMode.HTML,
            link_preview_options=LinkPreviewOptions(is_disabled=True)
        )

    except Exception as e:
        await status_msg.edit_text(
            f"<blockquote>❌ <b>Failed to get link :</b>\n<code>{e}</code>\n\n"
            f"💡 <i>Make sure bot is added in that group and has 'Invite Users via Link' admin rights!</i></blockquote>",
            parse_mode=enums.ParseMode.HTML
        )

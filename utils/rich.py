import math
import os
import re
import urllib.request
import traceback
from pyrogram import enums, types
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

_TAG_RE = re.compile(
    r"<(/?)(b|i|u|a|code|emoji)(?:\s+(?:href|id)=([^>]+))?>",
    re.IGNORECASE,
)

def _make_custom_emoji(text, eid):
    try:
        val = int(str(eid).strip("\"' "))
        return types.RichTextCustomEmoji(text=text, document_id=val)
    except Exception:
        pass
    try:
        val = int(str(eid).strip("\"' "))
        return types.RichTextCustomEmoji(text=text, custom_emoji_id=val)
    except Exception:
        pass
    return text

def _parse_inline(segment):
    if not segment:
        return ""
    parts = []
    stack = []
    pos = 0

    for m in _TAG_RE.finditer(segment):
        if m.start() > pos:
            parts.append(segment[pos : m.start()])
        pos = m.end()

        closing = m.group(1)
        tag = m.group(2).lower()
        attr = m.group(3)

        if not closing:
            stack.append((tag, attr, len(parts)))
        elif stack and stack[-1][0] == tag:
            open_tag, val, start = stack.pop()
            inner = parts[start:]
            del parts[start:]
            inner = inner[0] if len(inner) == 1 else inner if inner else ""

            if open_tag == "b":
                parts.append(types.RichTextBold(text=inner))
            elif open_tag == "i":
                parts.append(types.RichTextItalic(text=inner))
            elif open_tag == "u":
                parts.append(types.RichTextUnderline(text=inner))
            elif open_tag == "code":
                parts.append(types.RichTextCode(text=inner))
            elif open_tag == "a":
                parts.append(types.RichTextUrl(text=inner, url=val.strip("\"' ")))
            elif open_tag == "emoji":
                parts.append(_make_custom_emoji(inner or "✨", val))

    if pos < len(segment):
        parts.append(segment[pos:])

    if not parts:
        return ""
    return parts[0] if len(parts) == 1 else parts

def html_to_rich_blocks(caption_html: str):
    blocks = []
    bq_pattern = re.compile(
        r"<(blockquote(?:\s+[^>]*)?)>(.*?)</blockquote\s*>",
        re.DOTALL | re.IGNORECASE,
    )

    last_idx = 0
    for match in bq_pattern.finditer(caption_html):
        start, end = match.span()
        if start > last_idx:
            pre_text = caption_html[last_idx:start].strip()
            if pre_text:
                for line in pre_text.split("\n"):
                    line_clean = line.strip()
                    if line_clean:
                        parsed = _parse_inline(line_clean)
                        if parsed:
                            blocks.append(types.InputRichBlockParagraph(text=parsed))

        open_tag = match.group(1).lower()
        inner_content = match.group(2).strip()
        is_expandable = "expandable" in open_tag

        sub_paragraphs = []
        for line in inner_content.split("\n"):
            line_clean = line.strip()
            if line_clean:
                parsed = _parse_inline(line_clean)
                if parsed:
                    sub_paragraphs.append(types.InputRichBlockParagraph(text=parsed))

        if is_expandable and hasattr(types, "InputRichBlockExpandableBlockQuotation"):
            try:
                blocks.append(types.InputRichBlockExpandableBlockQuotation(blocks=sub_paragraphs))
            except Exception:
                blocks.extend(sub_paragraphs)
        else:
            try:
                blocks.append(types.InputRichBlockBlockQuotation(blocks=sub_paragraphs))
            except Exception:
                blocks.extend(sub_paragraphs)

        last_idx = end

    if last_idx < len(caption_html):
        post_text = caption_html[last_idx:].strip()
        if post_text:
            for line in post_text.split("\n"):
                line_clean = line.strip()
                if line_clean:
                    parsed = _parse_inline(line_clean)
                    if parsed:
                        blocks.append(types.InputRichBlockParagraph(text=parsed))

    if not blocks:
        for line in caption_html.split("\n"):
            if line.strip():
                blocks.append(types.InputRichBlockParagraph(text=_parse_inline(line.strip())))

    return blocks

def make_exp_slider_row(curr_exp: int, max_exp: int = 500):
    percentage = (curr_exp / max_exp) * 100 if max_exp else 0
    umm = math.floor(percentage)
    if umm <= 10:
        bar = "─●────────"
    elif 10 < umm <= 25:
        bar = "──●───────"
    elif 25 < umm <= 40:
        bar = "────●─────"
    elif 40 < umm <= 60:
        bar = "─────●────"
    elif 60 < umm <= 75:
        bar = "──────●───"
    elif 75 < umm <= 90:
        bar = "────────●─"
    else:
        bar = "─────────●"

    slider_text = f"{curr_exp} EXP  {bar}  {max_exp} EXP"
    btn_style = getattr(enums.ButtonStyle, "DANGER", getattr(enums.ButtonStyle, "DEFAULT", None))

    return types.InputRichBlockButtons(
        buttons=[
            types.RichMessageButton(
                text=slider_text,
                style=btn_style,
                callback_data="noop_exp_bar",
            )
        ]
    )

def _convert_to_standard_inline(rich_buttons_rows):
    if not rich_buttons_rows:
        return None
    standard_rows = []
    for r in rich_buttons_rows:
        btns = []
        btn_list = r.buttons if isinstance(r, types.InputRichBlockButtons) else r
        for b in btn_list:
            t = getattr(b, "text", "Button")
            cb = getattr(b, "callback_data", None)
            url = getattr(b, "url", None)
            if url:
                btns.append(InlineKeyboardButton(text=t, url=url))
            else:
                btns.append(InlineKeyboardButton(text=t, callback_data=cb or "noop"))
        if btns:
            standard_rows.append(btns)
    return InlineKeyboardMarkup(standard_rows) if standard_rows else None

def _resolve_photo_path(photo):
    if not photo:
        return None
    if isinstance(photo, str) and (photo.startswith("http://") or photo.startswith("https://")):
        os.makedirs("cache", exist_ok=True)
        local_path = "cache/banner_downloaded.jpg"
        if not os.path.exists(local_path) or os.path.getsize(local_path) == 0:
            try:
                req = urllib.request.Request(
                    photo,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    }
                )
                with urllib.request.urlopen(req, timeout=10) as resp, open(local_path, "wb") as f:
                    f.write(resp.read())
            except Exception as e:
                print(f"[Photo Download Error]: {e}")
                return None
        return local_path if (os.path.exists(local_path) and os.path.getsize(local_path) > 0) else None
    elif isinstance(photo, str) and os.path.isfile(photo):
        return photo if os.path.getsize(photo) > 0 else None
    return None

async def send_jumble_rich(client, chat_id: int, caption_html: str, rich_buttons_rows: list = None, slider_row=None, photo=None):
    blocks = []

    photo_file = _resolve_photo_path(photo)
    if photo_file and os.path.isfile(photo_file):
        try:
            blocks.append(types.InputRichBlockPhoto(photo=types.InputMediaPhoto(photo_file)))
        except Exception as pe:
            print(f"[InputRichBlockPhoto Error]: {pe}")

    blocks.extend(html_to_rich_blocks(caption_html))
    if slider_row:
        blocks.append(slider_row)
    if rich_buttons_rows:
        for row in rich_buttons_rows:
            if isinstance(row, types.InputRichBlockButtons):
                blocks.append(row)
            elif isinstance(row, list):
                blocks.append(types.InputRichBlockButtons(buttons=row))

    # Try 1: Kurigram Native Send Rich Message
    try:
        if hasattr(client, "send_rich_message"):
            return await client.send_rich_message(
                chat_id=chat_id,
                rich_message=types.InputRichMessage(blocks=blocks),
            )
    except Exception as e:
        print(f"[send_jumble_rich Native Error]: {e}")

    # Try 2: Standard Message with Rich Blocks
    try:
        return await client.send_message(
            chat_id=chat_id,
            text=" ",
            rich_message=types.InputRichMessage(blocks=blocks)
        )
    except Exception as fe:
        print(f"[send_jumble_rich Rich Fallback Error]: {fe}")

    # Try 3: Standard Pyrogram HTML fallback with converted buttons
    inline_markup = _convert_to_standard_inline(rich_buttons_rows)
    return await client.send_message(
        chat_id=chat_id,
        text=caption_html,
        reply_markup=inline_markup,
        parse_mode=enums.ParseMode.HTML
    )

async def edit_jumble_rich(client, chat_id: int, message_id: int, caption_html: str, rich_buttons_rows: list = None, slider_row=None):
    blocks = html_to_rich_blocks(caption_html)
    if slider_row:
        blocks.append(slider_row)
    if rich_buttons_rows:
        for row in rich_buttons_rows:
            if isinstance(row, types.InputRichBlockButtons):
                blocks.append(row)
            elif isinstance(row, list):
                blocks.append(types.InputRichBlockButtons(buttons=row))

    # Try 1: Native edit_rich_message
    try:
        if hasattr(client, "edit_rich_message"):
            return await client.edit_rich_message(
                chat_id=chat_id,
                message_id=message_id,
                rich_message=types.InputRichMessage(blocks=blocks)
            )
    except Exception:
        pass

    # Try 2: edit_message_text with Rich Message
    try:
        return await client.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=" ",
            rich_message=types.InputRichMessage(blocks=blocks)
        )
    except Exception:
        pass

    # Try 3: Delete and Send Fresh
    try:
        await client.delete_messages(chat_id, message_id)
    except Exception:
        pass
    return await send_jumble_rich(client, chat_id, caption_html, rich_buttons_rows, slider_row)

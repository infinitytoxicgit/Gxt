import os
import re
import math
from pyrogram import enums, types
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

_TAG_RE = re.compile(r"<(/?)(b|i|u|a|code)(?:\s+(?:href)=([^>]+))?>", re.IGNORECASE)

def _parse_inline(segment):
    if not segment:
        return ""
    parts, stack, pos = [], [], 0
    for m in _TAG_RE.finditer(segment):
        if m.start() > pos:
            parts.append(segment[pos : m.start()])
        pos = m.end()
        closing, tag, attr = m.group(1), m.group(2).lower(), m.group(3)
        if not closing:
            stack.append((tag, attr, len(parts)))
        elif stack and stack[-1][0] == tag:
            open_tag, val, start = stack.pop()
            inner = parts[start:]
            del parts[start:]
            inner = inner[0] if len(inner) == 1 else inner if inner else ""
            if open_tag == "b": parts.append(types.RichTextBold(text=inner))
            elif open_tag == "i": parts.append(types.RichTextItalic(text=inner))
            elif open_tag == "u": parts.append(types.RichTextUnderline(text=inner))
            elif open_tag == "code": parts.append(types.RichTextCode(text=inner))
            elif open_tag == "a": parts.append(types.RichTextUrl(text=inner, url=val.strip("\"' ")))
    if pos < len(segment):
        parts.append(segment[pos:])
    return parts[0] if len(parts) == 1 else parts

def html_to_rich_blocks(caption_html: str):
    blocks = []
    clean_text = re.sub(r"</?blockquote[^>]*>", "", caption_html, flags=re.IGNORECASE)
    paragraphs = []
    for line in clean_text.strip().split("\n"):
        line_clean = line.strip()
        if line_clean:
            parsed = _parse_inline(line_clean)
            if parsed:
                paragraphs.append(types.InputRichBlockParagraph(text=parsed))
    if paragraphs and hasattr(types, "InputRichBlockBlockQuotation"):
        blocks.append(types.InputRichBlockBlockQuotation(blocks=paragraphs))
    else:
        blocks.extend(paragraphs)
    return blocks

def make_exp_slider_row(curr_exp: int, max_exp: int = 500):
    pct = (curr_exp / max_exp) * 100 if max_exp else 0
    bar = "─●────────" if pct <= 15 else "───●──────" if pct <= 40 else "─────●────" if pct <= 70 else "───────●──"
    txt = f"{curr_exp} EXP {bar} {max_exp} EXP"
    btn_style = getattr(enums.ButtonStyle, "DANGER", getattr(enums.ButtonStyle, "DEFAULT", None))
    return types.InputRichBlockButtons(buttons=[types.RichMessageButton(text=txt, style=btn_style, callback_data="noop")])

def _to_rich_buttons(buttons_rows):
    out = []
    if not buttons_rows:
        return out
    for r in buttons_rows:
        if isinstance(r, types.InputRichBlockButtons):
            out.append(r)
        elif isinstance(r, list):
            b_list = []
            for b in r:
                if isinstance(b, types.RichMessageButton):
                    b_list.append(b)
                elif isinstance(b, InlineKeyboardButton):
                    b_list.append(types.RichMessageButton(text=b.text, style=enums.ButtonStyle.PRIMARY, callback_data=b.callback_data or "noop"))
            if b_list:
                out.append(types.InputRichBlockButtons(buttons=b_list))
    return out

def _to_inline(buttons_rows, slider=None):
    rows = []
    if slider and hasattr(slider, "buttons"):
        rows.append([InlineKeyboardButton(b.text, callback_data="noop") for b in slider.buttons])
    if buttons_rows:
        for r in buttons_rows:
            btn_list = r.buttons if isinstance(r, types.InputRichBlockButtons) else r
            if not isinstance(btn_list, list):
                btn_list = [btn_list]
            row_b = []
            for b in btn_list:
                if isinstance(b, InlineKeyboardButton):
                    row_b.append(b)
                else:
                    row_b.append(InlineKeyboardButton(text=b.text, callback_data=getattr(b, "callback_data", "noop")))
            if row_b:
                rows.append(row_b)
    return InlineKeyboardMarkup(rows) if rows else None

async def send_jumble_rich(client, chat_id: int, caption_html: str, rich_buttons_rows: list = None, slider_row=None, photo=None):
    blocks = []
    has_photo = bool(photo and isinstance(photo, str) and os.path.isfile(photo))

    # Kurigram Native Rich Photo handling (Pass exact file path string)
    if has_photo and hasattr(types, "InputRichBlockPhoto"):
        try:
            blocks.append(types.InputRichBlockPhoto(photo=types.InputMediaPhoto(media=photo)))
        except Exception as e1:
            try:
                blocks.append(types.InputRichBlockPhoto(photo=photo))
            except Exception as e2:
                print(f"[Photo Block Error]: {e1} | {e2}")

    blocks.extend(html_to_rich_blocks(caption_html))
    if slider_row and isinstance(slider_row, types.InputRichBlockButtons):
        blocks.append(slider_row)
    blocks.extend(_to_rich_buttons(rich_buttons_rows))

    try:
        return await client.send_rich_message(
            chat_id=chat_id,
            rich_message=types.InputRichMessage(blocks=blocks)
        )
    except Exception as e:
        print(f"[send_rich_message direct failed]: {e}")

    # Fallback to prevent silent drops
    markup = _to_inline(rich_buttons_rows, slider_row)
    if has_photo:
        return await client.send_photo(chat_id=chat_id, photo=photo, caption=caption_html, reply_markup=markup, parse_mode=enums.ParseMode.HTML)
    return await client.send_message(chat_id=chat_id, text=caption_html, reply_markup=markup, parse_mode=enums.ParseMode.HTML)

async def edit_jumble_rich(client, chat_id: int, message_id: int, caption_html: str, rich_buttons_rows: list = None, slider_row=None, photo=None):
    try:
        await client.delete_messages(chat_id, message_id)
    except Exception:
        pass
    return await send_jumble_rich(client, chat_id, caption_html, rich_buttons_rows, slider_row, photo)

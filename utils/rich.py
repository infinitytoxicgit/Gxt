import os
import re
import math
import traceback
from pyrogram import enums, types
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

MODE_FILE = "cache/ui_mode.txt"

def get_ui_mode() -> str:
    try:
        if os.path.exists(MODE_FILE):
            with open(MODE_FILE, "r") as f:
                val = f.read().strip().lower()
                if val in ("rich", "inline"):
                    return val
    except Exception:
        pass
    return "rich"

def set_ui_mode(mode: str):
    os.makedirs("cache", exist_ok=True)
    with open(MODE_FILE, "w") as f:
        f.write(mode.lower().strip())

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
    mode = get_ui_mode()
    pct = (curr_exp / max_exp) * 100 if max_exp else 0
    bar = "─●────────" if pct <= 15 else "───●──────" if pct <= 40 else "─────●────" if pct <= 70 else "───────●──"
    txt = f"{curr_exp} EXP {bar} {max_exp} EXP"
    if mode == "inline":
        return [InlineKeyboardButton(text=txt, callback_data="noop")]
    btn_style = getattr(enums.ButtonStyle, "DANGER", getattr(enums.ButtonStyle, "DEFAULT", None))
    return types.InputRichBlockButtons(buttons=[types.RichMessageButton(text=txt, style=btn_style, callback_data="noop")])

def _to_inline(buttons_rows, slider=None):
    rows = []
    if slider:
        if isinstance(slider, list): rows.append(slider)
        elif hasattr(slider, "buttons"):
            rows.append([InlineKeyboardButton(b.text, callback_data=b.callback_data or "noop") for b in slider.buttons])
    if buttons_rows:
        for r in buttons_rows:
            btn_list = r.buttons if isinstance(r, types.InputRichBlockButtons) else r
            if not isinstance(btn_list, list): btn_list = [btn_list]
            row_b = []
            for b in btn_list:
                if isinstance(b, InlineKeyboardButton): row_b.append(b)
                else: row_b.append(InlineKeyboardButton(text=b.text, callback_data=b.callback_data or "noop"))
            if row_b: rows.append(row_b)
    return InlineKeyboardMarkup(rows) if rows else None

def _to_rich_buttons(buttons_rows):
    out = []
    if not buttons_rows: return out
    for r in buttons_rows:
        if isinstance(r, types.InputRichBlockButtons):
            out.append(r)
        elif isinstance(r, list):
            b_list = []
            for b in r:
                if isinstance(b, types.RichMessageButton): b_list.append(b)
                elif isinstance(b, InlineKeyboardButton):
                    b_list.append(types.RichMessageButton(text=b.text, style=enums.ButtonStyle.PRIMARY, callback_data=b.callback_data or "noop"))
            if b_list:
                out.append(types.InputRichBlockButtons(buttons=b_list))
    return out

async def send_jumble_rich(client, chat_id: int, caption_html: str, rich_buttons_rows: list = None, slider_row=None, photo=None):
    mode = get_ui_mode()
    has_photo = photo and os.path.isfile(photo)

    # 1. INLINE MODE
    if mode == "inline":
        markup = _to_inline(rich_buttons_rows, slider_row)
        if has_photo:
            try:
                return await client.send_photo(chat_id=chat_id, photo=photo, caption=caption_html, reply_markup=markup, parse_mode=enums.ParseMode.HTML)
            except Exception:
                pass
        return await client.send_message(chat_id=chat_id, text=caption_html, reply_markup=markup, parse_mode=enums.ParseMode.HTML)

    # 2. RICH MODE
    blocks = []
    # Agar photo block available hai
    if has_photo and hasattr(types, "InputRichBlockPhoto"):
        try:
            blocks.append(types.InputRichBlockPhoto(photo=photo))
        except Exception:
            pass

    blocks.extend(html_to_rich_blocks(caption_html))
    if slider_row and isinstance(slider_row, types.InputRichBlockButtons):
        blocks.append(slider_row)
    blocks.extend(_to_rich_buttons(rich_buttons_rows))

    try:
        if hasattr(client, "send_rich_message"):
            return await client.send_rich_message(chat_id=chat_id, rich_message=types.InputRichMessage(blocks=blocks))
    except Exception as e:
        print(f"[send_rich error]: {e}")

    try:
        return await client.send_message(chat_id=chat_id, text=" ", rich_message=types.InputRichMessage(blocks=blocks))
    except Exception:
        pass

    # Rich fail hone par inline fallback
    markup = _to_inline(rich_buttons_rows, slider_row)
    if has_photo:
        return await client.send_photo(chat_id=chat_id, photo=photo, caption=caption_html, reply_markup=markup, parse_mode=enums.ParseMode.HTML)
    return await client.send_message(chat_id=chat_id, text=caption_html, reply_markup=markup, parse_mode=enums.ParseMode.HTML)

async def edit_jumble_rich(client, chat_id: int, message_id: int, caption_html: str, rich_buttons_rows: list = None, slider_row=None, photo=None):
    mode = get_ui_mode()
    if mode == "inline":
        markup = _to_inline(rich_buttons_rows, slider_row)
        try:
            return await client.edit_message_caption(chat_id=chat_id, message_id=message_id, caption=caption_html, reply_markup=markup, parse_mode=enums.ParseMode.HTML)
        except Exception:
            try:
                return await client.edit_message_text(chat_id=chat_id, message_id=message_id, text=caption_html, reply_markup=markup, parse_mode=enums.ParseMode.HTML)
            except Exception:
                pass
    try:
        await client.delete_messages(chat_id, message_id)
    except Exception:
        pass
    return await send_jumble_rich(client, chat_id, caption_html, rich_buttons_rows, slider_row, photo)

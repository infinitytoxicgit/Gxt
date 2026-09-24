import math
import re
from pyrogram import enums, types

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

        inner_items = []
        for line in inner_content.split("\n"):
            line_clean = line.strip()
            if line_clean:
                parsed = _parse_inline(line_clean)
                if parsed:
                    if isinstance(parsed, list):
                        inner_items.extend(parsed)
                    else:
                        inner_items.append(parsed)
                    inner_items.append("\n")

        if inner_items and inner_items[-1] == "\n":
            inner_items.pop()

        # Regular Blue Blockquote (Non-expandable) & Expandable both supported
        if is_expandable and hasattr(types, "InputRichBlockExpandableBlockQuotation"):
            blocks.append(types.InputRichBlockExpandableBlockQuotation(text=inner_items))
        else:
            blocks.append(types.InputRichBlockBlockQuotation(text=inner_items))

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

async def send_jumble_rich(client, chat_id: int, caption_html: str, rich_buttons_rows: list = None, slider_row=None):
    blocks = html_to_rich_blocks(caption_html)
    if slider_row:
        blocks.append(slider_row)
    if rich_buttons_rows:
        for row in rich_buttons_rows:
            blocks.append(types.InputRichBlockButtons(buttons=row))

    return await client.send_rich_message(
        chat_id=chat_id,
        rich_message=types.InputRichMessage(blocks=blocks),
    )

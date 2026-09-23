import re
from pyrogram import enums, types

_TAG_RE = re.compile(
    r"<(/?)(b|u|a|emoji)(?:\s+(?:href|id)=([^>]+))?>",
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
            elif open_tag == "u":
                parts.append(types.RichTextUnderline(text=inner))
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
        r"<(blockquote(?:\s+expandable)?)>(.*?)</\1>",
        re.DOTALL | re.IGNORECASE,
    )

    last_idx = 0
    for match in bq_pattern.finditer(caption_html):
        start, end = match.span()
        if start > last_idx:
            pre_text = caption_html[last_idx:start].strip()
            if pre_text:
                for line in pre_text.split("\n"):
                    line_parsed = _parse_inline(line)
                    if line_parsed:
                        blocks.append(types.InputRichBlockParagraph(text=line_parsed))

        tag_name = match.group(1).lower()
        inner_content = match.group(2).strip()
        is_expandable = "expandable" in tag_name

        inner_items = []
        for line in inner_content.split("\n"):
            parsed = _parse_inline(line)
            if parsed:
                if isinstance(parsed, list):
                    inner_items.extend(parsed)
                else:
                    inner_items.append(parsed)
                inner_items.append("\n")

        if inner_items and inner_items[-1] == "\n":
            inner_items.pop()

        if is_expandable and hasattr(types, "InputRichBlockExpandableBlockQuotation"):
            try:
                blocks.append(types.InputRichBlockExpandableBlockQuotation(text=inner_items))
            except Exception:
                blocks.append(types.InputRichBlockParagraph(text=inner_items))
        elif hasattr(types, "InputRichBlockBlockQuotation"):
            try:
                blocks.append(types.InputRichBlockBlockQuotation(text=inner_items))
            except Exception:
                blocks.append(types.InputRichBlockParagraph(text=inner_items))
        else:
            blocks.append(types.InputRichBlockParagraph(text=inner_items))

        last_idx = end

    if last_idx < len(caption_html):
        post_text = caption_html[last_idx:].strip()
        if post_text:
            for line in post_text.split("\n"):
                line_parsed = _parse_inline(line)
                if line_parsed:
                    blocks.append(types.InputRichBlockParagraph(text=line_parsed))

    if not blocks:
        for line in caption_html.split("\n"):
            if line.strip():
                blocks.append(types.InputRichBlockParagraph(text=_parse_inline(line)))

    return blocks


async def send_jumble_rich(client, chat_id: int, caption_html: str, rich_buttons_rows: list = None):
    blocks = html_to_rich_blocks(caption_html)
    if rich_buttons_rows:
        for row in rich_buttons_rows:
            blocks.append(types.InputRichBlockButtons(buttons=row))
    return await client.send_rich_message(
        chat_id=chat_id,
        rich_message=types.InputRichMessage(blocks=blocks),
    )

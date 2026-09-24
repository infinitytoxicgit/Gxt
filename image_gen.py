import io
import os
import re
import unicodedata
from PIL import Image, ImageDraw, ImageFont

def get_font(size: int, bold: bool = True):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"
    ]
    for path in paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()

def clean_text_safe(text: str) -> str:
    if not text:
        return "Player"
    norm = unicodedata.normalize('NFKD', str(text))
    cleaned = "".join([c for c in norm if c.isprintable() and ord(c) < 128]).strip()
    cleaned = re.sub(r'[^\w\s\-\.\@\$\#]', '', cleaned).strip()
    return cleaned if cleaned else "Player"

def make_puzzle_image(jumbled, mode_tag, puzzle_id):
    width, height = 1200, 650
    # RGB format use kiya hai taaki Telegram media stream me 100% render ho
    img = Image.new("RGB", (width, height), (15, 18, 28))
    draw = ImageDraw.Draw(img)

    for x in range(0, width, 50):
        draw.line([(x, 0), (x, height)], fill=(25, 32, 48), width=1)
    for y in range(0, height, 50):
        draw.line([(0, y), (width, y)], fill=(25, 32, 48), width=1)

    draw.rounded_rectangle([(18, 18), (width - 18, height - 18)], radius=28, outline=(0, 229, 255), width=4)

    header_font = get_font(44, bold=True)
    draw.text((width // 2, 75), "JUMBLE WORD GAME", anchor="mm", font=header_font, fill=(255, 255, 255))

    draw.rounded_rectangle([(90, 150), (width - 90, 420)], radius=24, fill=(22, 28, 44), outline=(0, 255, 180), width=2)

    clean_jumbled = str(jumbled).replace(" ", "").upper()
    text_len = len(clean_jumbled)
    if text_len <= 6:
        display_text = "   ".join(clean_jumbled)
        word_font = get_font(88, bold=True)
    elif text_len <= 10:
        display_text = "  ".join(clean_jumbled)
        word_font = get_font(68, bold=True)
    elif text_len <= 14:
        display_text = " ".join(clean_jumbled)
        word_font = get_font(52, bold=True)
    else:
        display_text = " ".join(clean_jumbled)
        word_font = get_font(38, bold=True)

    draw.text((width // 2, 285), display_text, anchor="mm", font=word_font, fill=(0, 229, 255))

    tag_upper = str(mode_tag).upper()
    if "EASY" in tag_upper:
        tag_color = (0, 255, 136)
    elif "HARD" in tag_upper:
        tag_color = (255, 60, 80)
    else:
        tag_color = (255, 200, 0)

    sub_font = get_font(30, bold=True)
    draw.text((width // 2, 490), f"{tag_upper}   -   PUZZLE #{puzzle_id}", anchor="mm", font=sub_font, fill=tag_color)

    inst_font = get_font(24, bold=False)
    draw.text((width // 2, 560), "Unscramble the letters & type in chat!", anchor="mm", font=inst_font, fill=(180, 195, 215))

    os.makedirs("cache", exist_ok=True)
    out_path = f"cache/puzzle_{puzzle_id}.png"
    img.save(out_path, "PNG", optimize=True)
    return out_path

def make_stats_graph_image(user_name: str, easy: int, med: int, hard: int, rank: int, exp: int, max_exp: int):
    w, h = 1100, 600
    img = Image.new("RGB", (w, h), (18, 22, 34))
    draw = ImageDraw.Draw(img)

    safe_name = clean_text_safe(user_name)

    draw.rounded_rectangle([(16, 16), (w - 16, h - 16)], radius=24, outline=(80, 140, 255), width=3)
    draw.text((w // 2, 60), f"PERFORMANCE MATRIX - {safe_name.upper()}", font=get_font(34, bold=True), fill=(255, 255, 255), anchor="mm")
    draw.text((w // 2, 105), f"RANK: LEVEL {rank}   |   EXP: {exp} / {max_exp}", font=get_font(24, bold=True), fill=(0, 220, 255), anchor="mm")

    draw.rounded_rectangle([(90, 140), (w - 90, 172)], radius=16, fill=(35, 42, 60))
    ratio = min(max(exp / max_exp, 0.0), 1.0) if max_exp else 0
    if ratio > 0:
        draw.rounded_rectangle([(90, 140), (90 + int((w - 180) * ratio), 172)], radius=16, fill=(0, 230, 160))

    total_solves = max(1, easy + med + hard)
    bars = [
        ("EASY SOLVES", easy, (0, 255, 130), 240),
        ("MEDIUM SOLVES", med, (255, 200, 30), 340),
        ("HARD SOLVES", hard, (255, 70, 90), 440),
    ]

    for label, count, color, y in bars:
        draw.text((90, y), label, font=get_font(24, bold=True), fill=(220, 230, 245))
        draw.text((w - 90, y), f"{count} Solves", font=get_font(24, bold=True), fill=color, anchor="ra")

        draw.rounded_rectangle([(90, y + 36), (w - 90, y + 62)], radius=12, fill=(32, 38, 55))
        bar_len = int((w - 180) * (count / total_solves))
        if bar_len > 0:
            draw.rounded_rectangle([(90, y + 36), (90 + bar_len, y + 62)], radius=12, fill=color)

    os.makedirs("cache", exist_ok=True)
    clean_filename = re.sub(r'[^a-zA-Z0-9_]', '_', safe_name)
    out_path = f"cache/stats_{clean_filename}.png"
    img.save(out_path, "PNG", optimize=True)
    return out_path

def make_leaderboard_graph_image(scope_title: str, timeframe: str, top_data: list):
    w, h = 1100, 680
    img = Image.new("RGB", (w, h), (16, 20, 30))
    draw = ImageDraw.Draw(img)

    clean_scope = clean_text_safe(scope_title)
    clean_tf = clean_text_safe(timeframe)

    draw.rounded_rectangle([(16, 16), (w - 16, h - 16)], radius=24, outline=(0, 255, 200), width=3)
    draw.text((w // 2, 60), f"LEADERBOARD - {clean_scope.upper()}", font=get_font(34, bold=True), fill=(255, 255, 255), anchor="mm")
    draw.text((w // 2, 105), f"TIMEFRAME: {clean_tf.upper()}", font=get_font(24, bold=True), fill=(0, 220, 255), anchor="mm")

    if not top_data:
        draw.text((w // 2, 350), "No solves recorded in this timeframe yet.", font=get_font(26, bold=False), fill=(180, 190, 210), anchor="mm")
    else:
        max_score = max(1, top_data[0]["score"])
        colors = [(255, 215, 0), (192, 192, 192), (205, 127, 50), (0, 220, 255), (0, 255, 150)]

        start_y = 160
        for idx, row in enumerate(top_data[:5]):
            y = start_y + (idx * 90)
            color = colors[idx] if idx < len(colors) else (180, 200, 220)

            name = clean_text_safe(str(row["name"]))[:14]
            score = row["score"]

            draw.text((90, y), f"#{idx + 1}  {name}", font=get_font(26, bold=True), fill=(255, 255, 255))
            draw.text((w - 90, y), f"{score} Stars", font=get_font(26, bold=True), fill=color, anchor="ra")

            draw.rounded_rectangle([(90, y + 36), (w - 90, y + 64)], radius=12, fill=(30, 36, 52))
            bar_w = int((w - 180) * (score / max_score))
            if bar_w > 0:
                draw.rounded_rectangle([(90, y + 36), (90 + bar_w, y + 64)], radius=12, fill=color)

    os.makedirs("cache", exist_ok=True)
    clean_tf_filename = re.sub(r'[^a-zA-Z0-9_]', '_', clean_tf)
    out_path = f"cache/leaderboard_{clean_tf_filename}.png"
    img.save(out_path, "PNG", optimize=True)
    return out_path

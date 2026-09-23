from pyrogram import enums, filters, types
from main import app
from database import DB
from utils.rich import send_jumble_rich


def make_graph_bar(score, max_score, width=8):
    if max_score <= 0:
        return "░" * width
    ratio = min(score / max_score, 1.0)
    filled = int(round(ratio * width))
    return "█" * filled + "░" * (width - filled)


@app.on_message(filters.command(["leaderboard", "top"]))
async def leaderboard_cmd(client, message):
    top_users = DB.execute("SELECT user_id, name, stars FROM users ORDER BY stars DESC LIMIT 5").fetchall()
    if not top_users:
        return await message.reply_text("📊 No players recorded in leaderboard yet.")

    max_score = top_users[0]["stars"] if top_users[0]["stars"] > 0 else 1
    graph_lines = []

    for idx, u in enumerate(top_users, start=1):
        name = (u["name"] or f"Player {idx}")[:10]
        stars = u["stars"]
        bar = make_graph_bar(stars, max_score, width=8)
        graph_lines.append(f"#{idx} {name:<10} {bar} ⭐{stars}")

    chart_body = "\n".join(graph_lines)

    caption = (
        "<blockquote><emoji id=5895705279416241926>📊</emoji> <u><b>JUMBLE LEADERBOARD GRAPH</b></u></blockquote>\n\n"
        "<blockquote expandable>"
        "<b>Performance Chart :</b>\n"
        f"<code>{chart_body}</code>\n\n"
        "<emoji id=6066395745139824604>🎖️</emoji> <b>Formula :</b> 1 Level = 500 EXP\n"
        "<emoji id=5409132617750555920>⚡</emoji> Fast solves give extra bonus points!</blockquote>"
    )

    buttons = [
        [
            types.RichMessageButton(
                text="👤 My Stats",
                style=enums.ButtonStyle.SUCCESS,
                callback_data=f"show_stats|{message.from_user.id}",
            ),
            types.RichMessageButton(
                text="🔄 Refresh",
                style=enums.ButtonStyle.PRIMARY,
                callback_data="refresh_leaderboard",
            ),
        ]
    ]

    await send_jumble_rich(client, message.chat.id, caption, buttons)

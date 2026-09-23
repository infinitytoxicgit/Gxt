from pyrogram import filters, enums, types
from Gxt import app
from Gxt.utils.database import get_top_players
from Gxt.utils.rich import send_jumble_rich


def make_graph_bar(score, max_score, width=8):
    if max_score <= 0:
        return "░" * width
    ratio = min(score / max_score, 1.0)
    filled = int(round(ratio * width))
    return "█" * filled + "░" * (width - filled)


@app.on_message(filters.command(["leaderboard", "top"]))
async def jumble_leaderboard_cmd(client, message):
    top_users = await get_top_players(limit=5)
    if not top_users:
        return await message.reply_text("📊 No players recorded in leaderboard yet.")

    max_score = top_users[0].get("stars", 1) or 1
    graph_lines = []

    for idx, u in enumerate(top_users, start=1):
        name = (u.get("name") or f"Player {idx}")[:10]
        stars = u.get("stars", 0)
        bar = make_graph_bar(stars, max_score, width=8)
        graph_lines.append(f"#{idx} {name:<10} {bar} ⭐{stars}")

    chart_body = "\n".join(graph_lines)

    caption = (
        "<blockquote><emoji id=5895705279416241926>📊</emoji> <u><b>JUMBLE LEADERBOARD GRAPH</b></u></blockquote>\n\n"
        "<blockquote expandable>"
        "<b>Rankings & Performance :</b>\n"
        f"<code>{chart_body}</code>\n\n"
        "<emoji id=6066395745139824604>🎖️</emoji> <b>Rule :</b> 1 Level = 500 EXP\n"
        "<emoji id=5409132617750555920>⚡</emoji> <b>Points Multiplier :</b> Multiplies solve stars</blockquote>"
    )

    buttons = [
        [
            types.RichMessageButton(
                text="🔄 Refresh",
                style=enums.ButtonStyle.PRIMARY,
                callback_data="refresh_leaderboard",
            ),
            types.RichMessageButton(
                text="👤 My Stats",
                style=enums.ButtonStyle.SUCCESS,
                callback_data=f"show_my_stats|{message.from_user.id}",
            ),
        ]
    ]

    await send_jumble_rich(client, message.chat.id, caption, buttons)

"""Telegram delivery for Just Bake lead alerts.

Push-only by design: alerts go to one fixed chat id, never to whoever last
messaged the bot. The bot's username is public, so anyone can press Start;
the fixed destination is what makes that harmless.

No Sheets or Apify imports -- this module only knows about Telegram.
"""

import html
import logging

import requests

log = logging.getLogger(__name__)

API = "https://api.telegram.org/bot{token}/{method}"
EXCERPT_CHARS = 180
ANSWER_CHARS = 700

LEAD_THRESHOLD = 7
EXPERTISE_THRESHOLD = 9

PATH_LABELS = {
    "order":        ("🔥", "הזמנה"),
    "mentoring":    ("🌱", "ליווי"),
    "event":        ("📅", "אירוע"),
    "professional": ("💬", "מקצועי"),
    "none":         ("💬", "כללי"),
}


def should_notify(lead_score: int, expertise_score: int, notified_at: str) -> bool:
    """One alert per post, ever. An empty notified_at means still eligible."""
    if (notified_at or "").strip():
        return False
    return lead_score >= LEAD_THRESHOLD or expertise_score >= EXPERTISE_THRESHOLD


def format_alert(post: dict, result: dict, group_name: str) -> str:
    """HTML-formatted alert. Everything interpolated is escaped -- an unescaped
    '<' or '&' from a post body makes Telegram reject the entire message."""
    emoji, label = PATH_LABELS.get(result.get("lead_path"), PATH_LABELS["none"])
    excerpt = html.escape((post.get("text") or "")[:EXCERPT_CHARS])
    answer = html.escape((result.get("answer") or "")[:ANSWER_CHARS])

    lines = [
        f"{emoji} <b>ליד {result.get('lead_score', 0)}</b> · מסלול: {label} · {html.escape(group_name)}",
        f"<i>expertise {result.get('score', 0)}</i>",
        "",
        f'<i>"{excerpt}"</i>',
    ]
    if answer:
        lines += ["", "👇 <b>התשובה המוצעת</b> (לחיצה מעתיקה):", f"<code>{answer}</code>"]
    return "\n".join(lines)

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

LEAD_THRESHOLD = 6   # lowered from 7 on 27/09: a Sukkot event organiser needing 10 pizzas scored 6 and did not alert
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


def send_alert(token: str, chat_id: str, text: str,
               post_url: str, dashboard_url: str) -> int | None:
    """Send one alert. Returns the Telegram message_id, or None on any failure.

    Never raises: the sheet row is written regardless, and notified_at stays
    empty so the next run retries.
    """
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "reply_markup": {"inline_keyboard": [[
            {"text": "📄 לפוסט", "url": post_url},
            {"text": "📊 לדשבורד", "url": dashboard_url},
        ]]},
    }
    try:
        resp = requests.post(API.format(token=token, method="sendMessage"),
                             json=payload, timeout=20)
        if resp.status_code != 200:
            log.warning(f"Telegram sendMessage {resp.status_code}: {resp.text[:200]}")
            return None
        return resp.json().get("result", {}).get("message_id")
    except Exception as e:
        log.warning(f"Telegram send failed: {e}")
        return None


def ping_healthcheck(url: str, suffix: str = "") -> None:
    """Dead-man's switch ping. Silent no-op when unconfigured; never raises,
    because a monitoring failure must not fail the job it monitors."""
    if not url:
        return
    try:
        requests.get(url + suffix, timeout=10)
    except Exception as e:
        log.warning(f"Healthcheck ping failed: {e}")


def send_plain(token: str, chat_id: str, text: str) -> int | None:
    """Plain message with no buttons — used for the daily summary."""
    try:
        resp = requests.post(API.format(token=token, method="sendMessage"),
                             json={"chat_id": chat_id, "text": text}, timeout=20)
        if resp.status_code != 200:
            log.warning(f"Telegram sendMessage {resp.status_code}: {resp.text[:200]}")
            return None
        return resp.json().get("result", {}).get("message_id")
    except Exception as e:
        log.warning(f"Telegram send failed: {e}")
        return None


def fetch_replies(token: str, chat_id: str, offset: int) -> tuple[list, int]:
    """Drain queued updates. Returns (owner_messages, next_offset).

    Telegram queues updates for 24 hours, so a scheduled run is enough — no
    webhook and no always-on listener.

    from.id is set by Telegram's servers and cannot be spoofed by a sender, so
    the equality check below is the whole authorisation model. The offset
    advances past ignored updates too, otherwise a stranger's message would be
    re-fetched forever.
    """
    try:
        resp = requests.get(API.format(token=token, method="getUpdates"),
                            params={"offset": offset, "timeout": 0}, timeout=30)
        if resp.status_code != 200:
            log.warning(f"Telegram getUpdates {resp.status_code}: {resp.text[:200]}")
            return [], offset
        updates = resp.json().get("result", []) or []
    except Exception as e:
        log.warning(f"Telegram getUpdates failed: {e}")
        return [], offset

    if not updates:
        return [], offset

    owner = str(chat_id)
    replies = []
    for update in updates:
        msg = update.get("message") or {}
        if str((msg.get("from") or {}).get("id")) != owner:
            continue
        replies.append({
            "text": (msg.get("text") or "").strip(),
            "reply_to": (msg.get("reply_to_message") or {}).get("message_id"),
            "message_id": msg.get("message_id"),
        })

    next_offset = max(u["update_id"] for u in updates) + 1
    log.info(f"Drained {len(updates)} updates, {len(replies)} from owner")
    return replies, next_offset

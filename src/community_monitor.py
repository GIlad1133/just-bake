"""
Community Monitor — daily Facebook group listener.
Fetches posts, scores engagement opportunities, saves to Google Sheets.
Run via GitHub Actions daily, or manually: python src/community_monitor.py
"""

import os
import json
import logging
import base64
from datetime import datetime, timedelta, timezone

import requests

import gspread
from google.oauth2.service_account import Credentials
import anthropic
from apify_client import ApifyClient

from src.sheet_rows import COMMUNITY_HEADERS, build_row, row_to_dict
from src import telegram_notify
from src import answer_templates
from src import sheet_meta

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

COMMUNITY_SHEET_NAME = "Community"

GROUP_NAMES = {
    "1061644604326919": "הטאבון הביתי",
    "4432265433559920": "פיצה נפוליטנית",
    "2030269437295695": "אפייה ביתית",
    "587379969063560": "מחמצת ולחם",
    "695285311378525": "טאבון ופיצה",
    "197357223182966": "Home Tabun",
    "2926500980956274": "נפלאות הטאבון",
}


def group_name(group_url: str) -> str:
    for key, name in GROUP_NAMES.items():
        if key in (group_url or ""):
            return name
    return "קבוצה"


def maybe_alert(post: dict, result: dict, cfg: dict) -> tuple[str, str]:
    """Send an alert if the post qualifies. Returns (notified_at, tg_message_id),
    both empty strings when nothing was sent."""
    if not cfg.get("telegram_token") or not cfg.get("telegram_chat_id"):
        return "", ""
    if not telegram_notify.should_notify(result["lead_score"], result["score"], ""):
        return "", ""

    text = telegram_notify.format_alert(post, result, group_name(post.get("facebookUrl", "")))
    mid = telegram_notify.send_alert(
        cfg["telegram_token"], cfg["telegram_chat_id"], text,
        post.get("url", ""), cfg["dashboard_url"])
    if mid is None:
        return "", ""
    log.info(f"Alerted lead={result['lead_score']} path={result['lead_path']} msg={mid}")
    return datetime.now().strftime("%d/%m/%Y %H:%M"), str(mid)


TEMPLATE_COMMANDS = {"/order": "order", "/mentoring": "mentoring",
                     "/event": "event", "/pro": "professional"}


def classify_reply(reply: dict) -> dict:
    """Turn a raw Telegram reply into an action. Never raises."""
    text = (reply.get("text") or "").strip()
    target = reply.get("reply_to")

    if not text:
        return {"kind": "ignored"}

    if text in ("/bad", "/skip"):
        return {"kind": "bad", "target": target} if target else {"kind": "ignored"}

    head, _, rest = text.partition(" ")
    payload = rest.strip()

    if head == "/fact":
        return {"kind": "fact", "payload": payload} if payload else {"kind": "ignored"}

    if head in TEMPLATE_COMMANDS:
        return ({"kind": "template", "path": TEMPLATE_COMMANDS[head], "payload": payload}
                if payload else {"kind": "ignored"})

    if text.startswith("/"):
        return {"kind": "ignored"}

    return {"kind": "answer", "target": target, "payload": text} if target else {"kind": "ignored"}


def apply_replies(spreadsheet, ws, cfg) -> int:
    """Drain and apply Telegram replies. Every processed reply is acknowledged —
    without an ack, a reply silently lost to Telegram's 24h expiry looks exactly
    like one that was saved."""
    if not cfg.get("telegram_token"):
        return 0

    try:
        offset = int(sheet_meta.get_meta(spreadsheet, "telegram_offset", "0") or 0)
    except ValueError:
        log.warning("Bad telegram_offset in Meta tab; restarting from 0")
        offset = 0
    replies, next_offset = telegram_notify.fetch_replies(
        cfg["telegram_token"], cfg["telegram_chat_id"], offset)
    rows = ws.get_all_values()
    by_msg_id = {}
    for i, row in enumerate(rows[1:], start=2):
        data = row_to_dict(row)
        if data.get("tg_message_id"):
            by_msg_id[str(data["tg_message_id"])] = i

    applied = 0
    for reply in replies:
        action = classify_reply(reply)
        kind = action["kind"]
        ack = None

        if kind == "answer":
            row_num = by_msg_id.get(str(action["target"]))
            if row_num:
                ws.update_cell(row_num, COMMUNITY_HEADERS.index("my_answer") + 1, action["payload"])
                ws.update_cell(row_num, COMMUNITY_HEADERS.index("status") + 1, "posted")
                ack = "✅ נשמר כתשובה שלך, והפוסט סומן כפורסם"
            else:
                ack = "⚠️ לא מצאתי את הפוסט שהגבת עליו"

        elif kind == "bad":
            row_num = by_msg_id.get(str(action["target"]))
            if row_num:
                ws.update_cell(row_num, COMMUNITY_HEADERS.index("status") + 1, "bad_score")
                ack = "✅ סומן כניקוד שגוי"

        elif kind == "fact":
            spreadsheet.worksheet(answer_templates.FACTS_SHEET).append_row([action["payload"]])
            ack = f"✅ נוסף לעובדות: {action['payload'][:60]}"

        elif kind == "template":
            answer_templates.update_template(spreadsheet, action["path"], action["payload"])
            ack = f"✅ תבנית {action['path']} עודכנה: {action['payload'][:60]}"

        if ack:
            telegram_notify.send_plain(cfg["telegram_token"], cfg["telegram_chat_id"], ack)
            applied += 1

    # Persist the offset only after every reply has been applied and acked.
    # Advancing first means a mid-loop crash silently eats the replies.
    if next_offset != offset:
        sheet_meta.set_meta(spreadsheet, "telegram_offset", next_offset)

    if applied:
        log.info(f"Applied {applied} Telegram replies")
    return applied


# ─── Sheets ───────────────────────────────────────────────────────────────────

def get_or_create_community_sheet(spreadsheet):
    try:
        ws = spreadsheet.worksheet(COMMUNITY_SHEET_NAME)
        # Update headers if they're out of date
        if ws.col_count < len(COMMUNITY_HEADERS):
            ws.add_cols(len(COMMUNITY_HEADERS) - ws.col_count)
            log.info(f"Widened Community sheet to {len(COMMUNITY_HEADERS)} columns")
        current = ws.row_values(1)
        if current != COMMUNITY_HEADERS:
            ws.update("A1", [COMMUNITY_HEADERS])
            log.info("Updated Community sheet headers")
        return ws
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(COMMUNITY_SHEET_NAME, rows=2000, cols=len(COMMUNITY_HEADERS))
        ws.update("A1", [COMMUNITY_HEADERS])
        log.info("Created Community sheet")
        return ws


def get_known_posts(ws) -> dict:
    """Returns {url: {"row": row_number, "comment_count": N}} for dedup + update detection."""
    records = ws.get_all_values()
    if len(records) <= 1:
        return {}
    headers = records[0]
    url_col = headers.index("post_url")       # C = 2
    comments_col = headers.index("comments")  # G = 6
    result = {}
    for i, row in enumerate(records[1:], start=2):  # row 2 = first data row in Sheets
        url = row[url_col] if len(row) > url_col else ""
        comments = row[comments_col] if len(row) > comments_col else ""
        if url:
            result[url] = {"row": i, "comment_count": len(comments)}
    return result


# ─── Apify ────────────────────────────────────────────────────────────────────

# The gap between runs is not uniform: daytime runs are 2h apart but the
# overnight gap (20:00->04:00 UTC) is 8h. A fixed lookback is therefore wrong
# either way, so the window is derived from the last successful run.
LOOKBACK_MIN_HOURS = 3        # floor: consecutive runs still overlap
LOOKBACK_MAX_HOURS = 24       # ceiling: a long outage cannot blow the budget
LOOKBACK_MARGIN_MINUTES = 30  # slack for GitHub's scheduling delay


def compute_cutoff(last_run_iso: str, now=None) -> str:
    """ISO timestamp for onlyPostsNewerThan, derived from the last successful run.

    A skipped or delayed run would otherwise lose posts silently. Floored so two
    runs in quick succession still overlap, capped so recovering from a week-long
    outage does not request a huge billable window.
    """
    now = now or datetime.now(timezone.utc)
    floor = now - timedelta(hours=LOOKBACK_MIN_HOURS)
    ceiling = now - timedelta(hours=LOOKBACK_MAX_HOURS)
    try:
        last = datetime.fromisoformat((last_run_iso or "").replace("Z", "+00:00"))
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        cutoff = last - timedelta(minutes=LOOKBACK_MARGIN_MINUTES)
    except (ValueError, AttributeError, TypeError):
        cutoff = floor
    cutoff = min(cutoff, floor)     # window is never shorter than the floor
    cutoff = max(cutoff, ceiling)   # window is never longer than the ceiling
    return cutoff.replace(microsecond=0).isoformat().replace("+00:00", "Z")
POSTS_PER_GROUP = 3     # deliberate coverage cap; cost tracks posts examined, not frequency


def build_run_input(group_urls: list, cutoff: str) -> dict:
    """Apify input. onlyPostsNewerThan filters BEFORE billing (verified 16/09/2026),
    so it is the only lever that stops us re-buying posts already in the sheet."""
    return {
        "startUrls": [{"url": url} for url in group_urls],
        "resultsLimit": POSTS_PER_GROUP,
        "maxComments": 3,
        "sortOrder": "RECENT_POSTS",
        "onlyPostsNewerThan": cutoff,
        "proxyConfiguration": {"useApifyProxy": True},
    }


def fetch_posts(group_urls: list, apify_token: str, cutoff: str) -> list:
    client = ApifyClient(apify_token)
    run_input = build_run_input(group_urls, cutoff)
    log.info(f"Fetching from {len(group_urls)} groups since {run_input['onlyPostsNewerThan']}")
    run = client.actor("apify/facebook-groups-scraper").call(run_input=run_input)
    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    valid = [item for item in items if item.get("text") and item.get("url")]
    for item in valid:
        attachments = item.get("attachments") or []
        item["image_url"] = next(
            (a.get("thumbnail") or a.get("photo_image", {}).get("uri")
             for a in attachments if a.get("thumbnail") or a.get("photo_image")),
            None,
        )
    log.info(f"Got {len(valid)} posts ({sum(1 for p in valid if p.get('image_url'))} with images)")
    return valid


# ─── Pre-filter (no Claude call needed) ───────────────────────────────────────

# Patterns that are always noise — grows over time as we learn the groups
NOISE_PATTERNS = [
    # Welcome posts
    "ברוכים הבאים לקבוצה",
    "welcome our new members",
    "today marks",
    "let's welcome",
    # Sales
    "למכירה",
    "למסירה",
    "נמסר",
    # Ads / promo for other groups
    "הצטרפו לקבוצתנו",
    "הצטרפו לקבוצה",
]

def is_noise(post: dict) -> tuple[bool, str]:
    """Returns (True, reason) if post is obvious noise that doesn't need Claude scoring."""
    text = (post.get("text") or "").lower()
    for pattern in NOISE_PATTERNS:
        if pattern.lower() in text:
            return True, pattern
    return False, ""


def build_noise_row(post: dict, reason: str) -> list:
    """Row for a post rejected by the noise pre-filter — no Claude call made."""
    return build_row({
        "date_fetched": datetime.now().strftime("%d/%m/%Y"),
        "group_url": post.get("facebookUrl", ""),
        "post_url": post.get("url", ""),
        "post_author": post.get("user", {}).get("name", ""),
        "post_date": str(post.get("time", ""))[:10],
        "post_text": (post.get("text") or "")[:1000],
        "score": -1,
        "score_reason": reason,
        "status": "noise",
        "lead_score": 0,
        "lead_path": "none",
    })


# ─── Claude ───────────────────────────────────────────────────────────────────

VALID_LEAD_PATHS = {"order", "mentoring", "professional", "event", "none"}


def _clamp(value, low: int, high: int, default: int = 0) -> int:
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


def parse_score_response(text: str) -> dict:
    """Parse Claude's JSON reply into a validated result dict.

    Never raises: a malformed reply yields a zero-scored result so one bad post
    cannot abort the run.
    """
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        parts = cleaned.split("```")
        cleaned = parts[1] if len(parts) > 1 else ""
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
        if not isinstance(data, dict):
            raise ValueError("not an object")
    except Exception as e:
        log.warning(f"Unparseable Claude response ({e}): {(text or '')[:120]}")
        data = {}

    path = data.get("lead_path")
    return {
        "lead_score": _clamp(data.get("lead_score"), 0, 10),
        "lead_path": path if path in VALID_LEAD_PATHS else "none",
        "lead_reason": data.get("lead_reason") or "",
        "score": _clamp(data.get("score"), 0, 10),
        "score_reason": data.get("score_reason") or "",
        "answer": data.get("answer") or None,
        "tags": data.get("tags") or [],
        "question_type": data.get("question_type") or "",
        "post_type": data.get("post_type") or "",
        "image_description": data.get("image_description") or "",
    }


def score_and_answer(post: dict, claude: anthropic.Anthropic, guidance: str = "") -> dict:
    comments_text = "\n".join([
        f"- {c.get('profileName', 'אנונימי')}: {c.get('text', '')}"
        for c in (post.get("topComments") or [])
    ]) or "אין תגובות עדיין"

    has_image = bool(post.get("image_url"))
    prompt = f"""אתה עוזר לגלעד מ"פשוט לאפות" - עסק שמוכר בצק פיצה נפוליטני, ערכות אפייה, רוטב ומוצרי גבינה בפתח תקווה.

## מילון מונחי אפייה — השתמש רק במונחים אלה, לא תמציא תרגומים
- **שמרים** (לא "שמיר" — שמיר זה עשב)
- **ביגה** (biga) — פרה-פרמנט איטלקי, הידרציה ~50-60%, נוקשה
- **פוליש** (poolish) — פרה-פרמנט צרפתי, הידרציה 100%, נוזלי
- **אוטוליז** (autolyse) — מנוחת קמח+מים לפני הוספת שמרים
- **פרמנטציה** / **תסיסה** — תהליך השמרים
- **הידרציה** — אחוז מים מתוך קמח
- **גלוטן** — רשת החלבון בבצק
- **למינציה** (lamination) — קיפול בצק
- **פרה-פרמנט** — בסיס בצק שמותסס מראש (ביגה, פוליש, מחמצת)
- **מחמצת** — sourdough starter
- **קמח 00** / **קמח לחם** / **קמח כוסמין** — לא "קמח מיוחד"
- **טאבון** — התנור הביתי (לא "אובן אבן" או "מכשיר")
- **W-ערך** — חוזק הגלוטן בקמח
- **כדור בצק** (לא "גוש")
- **פתיחת בצק** (לא "מתיחה" לפיצה נפוליטנית)

## כלל מפתח: אם מונח מקצועי קיים בשפת המקור (איטלקית/צרפתית/אנגלית) — השתמש בו ישירות. אל תמציא תרגום עברי.

## סגנון התגובה
- עברית מדוברת, ישירה. לא פואטית, לא נאומים.
- פרטים קונקרטיים בלבד — לא תיאורים כלליים.
- קצר ולעניין — 2-4 משפטים מספיקים לרוב.
- לא לסיים בשאלה חוזרת אם לא נדרש.

פוסט מקבוצת פייסבוק:
מחבר: {post.get('user', {}).get('name', '')}
תאריך: {str(post.get('time', ''))[:10]}
תוכן הפוסט:
{post.get('text', '')}

תגובות קיימות:
{comments_text}

{"יש תמונה/וידאו מצורפת לפוסט - נתח אותה: מה מוצג בה? האם היא חלק מהשאלה, הדגמה, פרסומת, או שיתוף תוצאה?" if has_image else "אין תמונה בפוסט."}

{guidance}

ענה בJSON בלבד (ללא markdown):
{{
  "image_description": "<תיאור קצר של התמונה, או null>",
  "post_type": "<question|showcase|ad|sale|welcome|other>",
  "lead_score": <0-10>,
  "lead_path": "<order|mentoring|professional|event|none>",
  "lead_reason": "<משפט אחד למה הציון הזה>",
  "score": <0-10>,
  "score_reason": "<משפט קצר>",
  "answer": "<תגובה בעברית, או null אם אין מה לענות>",
  "tags": ["<נושא>"],
  "question_type": "<where_to_buy|recipe_help|technique|equipment|ingredient|general_pizza|not_relevant>"
}}

## שני ציונים נפרדים - אל תבלבל ביניהם

### score (מומחיות): כמה טוב גלעד יכול לענות מקצועית
9-10: שאלה ישירה על בצק, תסיסה, קמח או אפיית פיצה שגלעד יכול לענות עליה מניסיון
5-8: קשור לתחום, גלעד יכול להוסיף ערך
1-4: לא בתחום, או שכבר יש תשובות מלאות

### lead_score (כסף): כמה קרוב האדם לקנות מגלעד
הפוסט חייב לעבור את **שלושת השערים** כדי לקבל ציון מעל 0:
1. **כיוון**: הוא מחפש לקנות, לא מציע למכירה. מי שמוכר בצק הוא מתחרה, לא ליד.
2. **מוצר**: מה שהוא מחפש הוא משהו שגלעד מוכר - בצק, ערכות, רוטב, קמח, גבינה, סדנאות.
   לא מיקסרים, לא מלושים, לא טאבונים, לא אבני שמוט, לא שקיות תבלין.
3. **היקף**: שימוש ביתי/אישי. לא סיטונאות, לא פיצריה, לא ספקות B2B.
   מיקום גאוגרפי לא פוסל: אופה ביתי בצפון שמחפש קמח הוא ליד.

10: עובר את שלושת השערים - רוצה לקנות בצק/ערכה/רוטב/קמח/גבינה בכל כמות,
    **או** בעל טאבון חדש בלי ידע **שמכוון לפיצה ובצק**
7-9: מחפש ספק לאירוע פרטי, מתעניין בסדנה, שאלה על מוצר ספציפי
4-6: אופה ביתי מנוסה שמכין לבד
1-3: לומד תאוריה, או ציוד שגלעד לא בקיא בו
0: מוכר משהו, תמונה בלי שאלה, פרסומת, או כל פנייה עסקית/פיצרייה/סיטונאות

**חשוב - שער 2 חל גם על בעל טאבון חדש.** מי שקנה טאבון ושואל מה **לבשל** בו
(ירקות, בשר, טיפים כלליים) אין לו בעיית בצק והוא לא ליד. ציון נמוך, ו-answer=null.

## lead_path - קובע את מבנה התשובה
order: רוצה לקנות בצק עכשיו
mentoring: בעל טאבון חדש שמכוון לפיצה
event: מחפש ספק לאירוע פרטי
professional: שאלה מקצועית טהורה (score גבוה, lead נמוך)
none: אין מה לענות

## כללי ניסוח לתשובה - חובה
1. פתיחה אנושית קצרה.
2. **טיפ אחד בלבד**, לא שניים. אל תסביר לו דבר שהוא כבר יודע או כבר קנה.
3. **תמיד מספר** - 30 דקות, 350 מעלות, 48 שעות, 300 גרם. טיפ בלי מספר הוא מילוי.
4. תגיד מה קורה אם לא - "אחרת תקבל תוצאה מבאסת".
5. **בלי שורת סיום.** בלי "תשאל אותי", בלי קישור, בלי הזמנה. תסיים על עובדה.
6. **בלי מחיר בהודעה הראשונה, גם ב-order.** קודם תבדוק שאתה יכול לעזור
   ("אם איזור פתח תקווה בכיוון שלך אשמח לעזור"), ואז תגיד מה המוצר.
7. בלי אימוג'י. ":)" מותר.
8. שתיים עד ארבע שורות.

אל תתקן את הלקוח על מה שהוא ביקש. אם ביקש 300 גרם, אל תסביר לו שצריך 220.
אסור לסיים בשאלה. אסור להציע עזרה פעמיים באותה תשובה.

## דוגמאות אמיתיות - תחקה את הסגנון הזה

### דוגמה 1 - פוסט: "מחפש מישהו שמוכר 50-60 כדורי פיצה לטאבון 300g לאירוע"
lead_score=10, lead_path=order, score=3
answer: "היי מאיר, אם איזור פתח תקווה בכיוון שלך אשמח לעזור :)
בצקים שעברו התפחה של 48 שעות, יש אפשרות לטרי או קפוא. כל בצק שוקל כ-300 גרם"
למה זה טוב: בדק גאוגרפיה, נתן עובדות יבשות, לא נתן מחיר, לא סיים בשאלה, לא תיקן אותו.

### דוגמה 2 - פוסט: "קניתי אוני 16 ואין לי ידע, מאיפה מתחילים עם פיצה?"
lead_score=10, lead_path=mentoring, score=8
answer: "איזה כיף זה טאבון חדש!
טיפ הכי טוב שאוכל לתת לך זה לתת לטאבון להתחמם 30 דקות לפני שאתה מתחיל לעבוד איתו (בכל הפעלה)
חום אבן הטאבון כשאתה מכין פיצות צריך להיות סביבות 350 מעלות אחרת תקבל תוצאה מבאסת."
למה זה טוב: טיפ אחד, עם מספרים, אמר מה קורה אם לא, ולא הציע שום דבר למכירה.

### דוגמה 3 - פוסט: "רכשנו טאבון גז cozzi. ממה מתחילים? ירקות?"
lead_score=1, lead_path=none, score=3, answer=null
למה: הוא שאל מה לבשל, לא על בצק ולא על פיצה. שער 2 נכשל.
זה נשאר null גם אם הטאבון חדש לגמרי. לדחוף לו בצק זה לא אופי הקבוצה.

### דוגמה 4 - פוסט: "מה זה בכלל מחמצת ואיך היא עובדת?"
lead_score=2, lead_path=professional, score=9
למה: שאלה תאורטית. הוא לומד, הוא לא קונה. mentoring שמור **רק** למי שקנה טאבון
ושואל על פיצה או בצק. שאלת ידע לעולם לא mentoring.

אם אין מה לענות - answer=null. עדיף לא לענות מאשר לדחוף הצעה."""

    try:
        content = [{"type": "text", "text": prompt}]
        image_url = post.get("image_url")
        if image_url:
            try:
                resp = requests.get(image_url, timeout=10)
                content_type = resp.headers.get("content-type", "")
                if resp.status_code == 200 and content_type.startswith("image/"):
                    media_type = content_type.split(";")[0].strip()
                    img_b64 = base64.standard_b64encode(resp.content).decode("utf-8")
                    content.insert(0, {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": img_b64}})
                else:
                    log.warning(f"Image not usable: status={resp.status_code} content-type={content_type}")
            except Exception as img_err:
                log.warning(f"Could not load image: {img_err}")
        log.info(f"Calling Claude for post {post.get('url','?')[:60]} (content_blocks={len(content)})")
        resp = claude.messages.create(
            model="claude-sonnet-5",
            max_tokens=4000,
            messages=[{"role": "user", "content": content}]
        )
        log.info(f"Claude blocks: {[b.type for b in resp.content]} stop={resp.stop_reason}")
        text = next((b.text for b in resp.content if b.type == "text"), "")
        if not text:
            log.warning(f"No text block in response: {[b.type for b in resp.content]}")
        return parse_score_response(text)
    except Exception as e:
        log.exception(f"Claude error for post {post.get('url','?')[:60]}: {e}")
        result = parse_score_response("")
        result["score_reason"] = str(e)
        return result


# ─── Main ─────────────────────────────────────────────────────────────────────

def run_monitor():
    # Load env
    apify_token = os.getenv("APIFY_API_TOKEN")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    credentials_json = os.getenv("GOOGLE_SHEETS_CREDENTIALS")
    spreadsheet_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
    monitoring_groups = [
        u.strip()
        for u in os.getenv("MONITORING_GROUPS", "").split(",")
        if u.strip()
    ]
    cfg = {
        "telegram_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
        "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID", ""),
        "dashboard_url": os.getenv("DASHBOARD_URL", "https://just-bake.streamlit.app/Community"),
        "healthcheck_url": os.getenv("HEALTHCHECK_URL", ""),
    }

    if not all([apify_token, anthropic_key, credentials_json, spreadsheet_id, monitoring_groups]):
        raise ValueError("Missing required env vars: APIFY_API_TOKEN, ANTHROPIC_API_KEY, GOOGLE_SHEETS_CREDENTIALS, GOOGLE_SHEETS_SPREADSHEET_ID, MONITORING_GROUPS")

    # Connect to Sheets
    creds = Credentials.from_service_account_info(
        json.loads(credentials_json),
        scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"],
    )
    spreadsheet = gspread.authorize(creds).open_by_key(spreadsheet_id)
    ws = get_or_create_community_sheet(spreadsheet)
    known_posts = get_known_posts(ws)
    log.info(f"Known posts: {len(known_posts)}")

    apply_replies(spreadsheet, ws, cfg)

    guidance = answer_templates.render_guidance(
        answer_templates.load_templates(spreadsheet),
        answer_templates.load_facts(spreadsheet))

    # Fetch posts
    cutoff = compute_cutoff(sheet_meta.get_meta(spreadsheet, "last_run_at", ""))
    posts = fetch_posts(monitoring_groups, apify_token, cutoff)
    claude = anthropic.Anthropic(api_key=anthropic_key)
    saved = updated = alerted = 0

    for post in posts:
        url = post.get("url")
        if not url:
            continue

        comments_flat = " | ".join([
            f"{c.get('profileName','')}: {c.get('text','')}"
            for c in (post.get("topComments") or [])
        ])

        if url not in known_posts:
            noise, reason = is_noise(post)
            if noise:
                log.info(f"Skipping noise ({reason}): {url[:60]}")
                ws.append_row(build_noise_row(post, reason))
                known_posts[url] = {"row": None, "comment_count": 0}
                saved += 1
                continue

            # New post — score and append
            log.info(f"New post: {url[:70]}...")
            result = score_and_answer(post, claude, guidance)
            notified_at, tg_message_id = maybe_alert(post, result, cfg)

            ws.append_row(build_row({
                "date_fetched": datetime.now().strftime("%d/%m/%Y"),
                "group_url": post.get("facebookUrl", ""),
                "post_url": url,
                "post_author": post.get("user", {}).get("name", ""),
                "post_date": str(post.get("time", ""))[:10],
                "post_text": (post.get("text") or "")[:1000],
                "comments": comments_flat[:800],
                "answer": result.get("answer") or "",
                "score": result["score"],
                "score_reason": result["score_reason"],
                "tags": ", ".join(result["tags"]),
                "question_type": result["question_type"],
                "status": "pending",
                "image_url": post.get("image_url") or "",
                "image_description": result["image_description"],
                "post_type": result["post_type"],
                "lead_score": result["lead_score"],
                "lead_path": result["lead_path"],
                "notified_at": notified_at,
                "tg_message_id": tg_message_id,
            }))
            if tg_message_id:
                alerted += 1
            known_posts[url] = {"row": None, "comment_count": len(comments_flat)}
            saved += 1

        else:
            # Known post — check if comments grew (new engagement)
            stored = known_posts[url]
            if len(comments_flat) > stored["comment_count"] and stored["row"]:
                log.info(f"Updated comments on: {url[:70]}...")
                result = score_and_answer(post, claude, guidance)
                row = stored["row"]
                # Update comments (col 7), answer (8), score (9), score_reason (10)
                ws.update(f"G{row}:J{row}", [[
                    comments_flat[:800],
                    result.get("answer") or "",
                    result.get("score", 0),
                    result.get("score_reason", ""),
                ]])
                updated += 1

    log.info(f"Done. Saved {saved} new posts, updated {updated} existing posts.")
    sheet_meta.set_meta(spreadsheet, "last_run_at",
                        datetime.now(timezone.utc).replace(microsecond=0).isoformat())
    telegram_notify.ping_healthcheck(cfg["healthcheck_url"])

    # Last scheduled run of the day (20:00 UTC) sends the summary. Its absence
    # is the signal — see the dead-man's switch for the case where no run happens.
    if datetime.now(timezone.utc).hour >= 20 and cfg.get("telegram_token"):
        telegram_notify.send_plain(
            cfg["telegram_token"], cfg["telegram_chat_id"],
            f"📊 סיכום יום\nפוסטים חדשים: {saved}\nעודכנו: {updated}\nהתראות: {alerted}")
    return saved


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    run_monitor()

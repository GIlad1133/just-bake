"""
Community Monitor — daily Facebook group listener.
Fetches posts, scores engagement opportunities, saves to Google Sheets.
Run via GitHub Actions daily, or manually: python src/community_monitor.py
"""

import os
import json
import logging
import base64
from datetime import datetime, timedelta

import requests

import gspread
from google.oauth2.service_account import Credentials
import anthropic
from apify_client import ApifyClient

from src.sheet_rows import COMMUNITY_HEADERS, build_row

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

COMMUNITY_SHEET_NAME = "Community"

RECENT_DAYS = 3  # only score posts from roughly the last couple of days


# ─── Sheets ───────────────────────────────────────────────────────────────────

def get_or_create_community_sheet(spreadsheet):
    try:
        ws = spreadsheet.worksheet(COMMUNITY_SHEET_NAME)
        # Update headers if they're out of date
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

def fetch_posts(group_urls: list, apify_token: str, posts_per_group: int = 10) -> list:
    client = ApifyClient(apify_token)
    run_input = {
        "startUrls": [{"url": url} for url in group_urls],
        "resultsLimit": posts_per_group,
        "maxComments": 3,
        "sortOrder": "RECENT_POSTS",
        # Datacenter proxy (default) is far cheaper than residential — keeps runs
        # inside the Apify free tier. Switch back to RESIDENTIAL if FB blocks it.
        "proxyConfiguration": {"useApifyProxy": True},
    }
    log.info(f"Fetching posts from {len(group_urls)} groups...")
    run = client.actor("apify/facebook-groups-scraper").call(run_input=run_input)
    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    valid = [item for item in items if item.get("text") and item.get("url")]
    # Extract first image URL from attachments
    for item in valid:
        attachments = item.get("attachments") or []
        item["image_url"] = next(
            (a.get("thumbnail") or a.get("photo_image", {}).get("uri") for a in attachments if a.get("thumbnail") or a.get("photo_image")),
            None
        )
    log.info(f"Got {len(valid)} posts with text ({sum(1 for p in valid if p.get('image_url'))} with images)")
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


def score_and_answer(post: dict, claude: anthropic.Anthropic) -> dict:
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
            model="claude-haiku-4-5-20251001",
            max_tokens=1200,
            messages=[{"role": "user", "content": content}]
        )
        log.info(f"Claude raw response (first 200 chars): {resp.content[0].text.strip()[:200]}")
        return parse_score_response(resp.content[0].text)
    except Exception as e:
        log.exception(f"Claude error for post {post.get('url','?')[:60]}: {e}")
        result = parse_score_response("")
        result["score_reason"] = str(e)
        return result


# ─── Main ─────────────────────────────────────────────────────────────────────

def _is_recent(post: dict) -> bool:
    """Keep only posts from the last RECENT_DAYS days (unparseable dates kept)."""
    raw = str(post.get("time", ""))[:10]
    try:
        return datetime.strptime(raw, "%Y-%m-%d") >= datetime.now() - timedelta(days=RECENT_DAYS)
    except ValueError:
        return True


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

    # Fetch posts
    posts = fetch_posts(monitoring_groups, apify_token)
    posts = [p for p in posts if _is_recent(p)]
    log.info(f"{len(posts)} posts within last {RECENT_DAYS} days")
    claude = anthropic.Anthropic(api_key=anthropic_key)
    saved = updated = 0

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
            result = score_and_answer(post, claude)

            ws.append_row([
                datetime.now().strftime("%d/%m/%Y"),          # date_fetched
                post.get("facebookUrl", ""),                   # group_url
                url,                                           # post_url
                post.get("user", {}).get("name", ""),          # post_author
                str(post.get("time", ""))[:10],                # post_date
                (post.get("text") or "")[:1000],               # post_text
                comments_flat[:800],                           # comments
                result.get("answer") or "",                    # answer
                result.get("score", 0),                        # score
                result.get("score_reason", ""),                # score_reason
                ", ".join(result.get("tags", [])),             # tags
                result.get("question_type", ""),               # question_type
                "pending",                                     # status
                "",                                            # posted_date
                post.get("image_url") or "",                   # image_url
                result.get("image_description") or "",         # image_description
                result.get("post_type") or "",                 # post_type
            ])
            known_posts[url] = {"row": None, "comment_count": len(comments_flat)}
            saved += 1

        else:
            # Known post — check if comments grew (new engagement)
            stored = known_posts[url]
            if len(comments_flat) > stored["comment_count"] and stored["row"]:
                log.info(f"Updated comments on: {url[:70]}...")
                result = score_and_answer(post, claude)
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
    return saved


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    run_monitor()

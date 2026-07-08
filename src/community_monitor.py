"""
Community Monitor — daily Facebook group listener.
Fetches posts, scores engagement opportunities, saves to Google Sheets.
Run via GitHub Actions daily, or manually: python src/community_monitor.py
"""

import os
import json
import logging
import base64
from datetime import datetime

import requests

import gspread
from google.oauth2.service_account import Credentials
import anthropic
from apify_client import ApifyClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

COMMUNITY_SHEET_NAME = "Community"
COMMUNITY_HEADERS = [
    "date_fetched", "group_url", "post_url", "post_author",
    "post_date", "post_text", "comments", "answer",
    "score", "score_reason", "tags", "question_type", "status", "posted_date", "image_url",
    "image_description", "post_type", "my_answer",
]


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

def fetch_posts(group_urls: list, apify_token: str, posts_per_group: int = 25) -> list:
    client = ApifyClient(apify_token)
    run_input = {
        "startUrls": [{"url": url} for url in group_urls],
        "resultsLimit": posts_per_group,
        "maxComments": 10,
        "sortOrder": "RECENT_POSTS",
        "proxyConfiguration": {
            "useApifyProxy": True,
            "apifyProxyGroups": ["RESIDENTIAL"],
        },
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


# ─── Claude ───────────────────────────────────────────────────────────────────

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
  "image_description": "<תיאור קצר של מה שרואים בתמונה, או null אם אין תמונה>",
  "post_type": "<question|showcase|ad|sale|welcome|other>",
  "score": <1-10>,
  "score_reason": "<משפט קצר למה הציון הזה, כולל מה הבנת מהתמונה אם יש>",
  "answer": "<תגובה בעברית מדוברת שגלעד יכול לפרסם - מקצועית, מועילה, לא שיווקית מדי. null אם לא רלוונטי>",
  "tags": ["<נושא>", "<נושא>"],
  "question_type": "<where_to_buy|recipe_help|technique|equipment|ingredient|general_pizza|not_relevant>"
}}

כללי ציון:
9-10: שאלה ישירה על בצק/אפייה/פיצה נפוליטנית שגלעד יכול לענות מניסיון, עדיין אין תשובה טובה
7-8: רלוונטי לתחום, גלעד יכול להוסיף ערך מקצועי
5-6: קשור לפיצה/טאבון אבל פחות ממוקד
1-4: לא קשור, פרסומת, מכירה, ברכות, או כבר יש תשובות מלאות

הדגש: גלעד מוכר בצק, ערכות, רוטב, קמח. ענה רק כשיש קשר לתחומים אלה."""

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
        text = resp.content[0].text.strip()
        log.info(f"Claude raw response (first 200 chars): {text[:200]}")
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("```", 2)[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        return json.loads(text)
    except Exception as e:
        log.exception(f"Claude error for post {post.get('url','?')[:60]}: {e}")
        return {"score": 0, "answer": None, "tags": [], "question_type": "other", "score_reason": str(e)}


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
                ws.append_row([
                    datetime.now().strftime("%d/%m/%Y"),
                    post.get("facebookUrl", ""),
                    url,
                    post.get("user", {}).get("name", ""),
                    str(post.get("time", ""))[:10],
                    (post.get("text") or "")[:1000],
                    "", "", -1, reason, "", "noise", "", "", "",  # score=-1, status=noise
                    "", "",
                ])
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

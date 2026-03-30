"""
Community Monitor — daily Facebook group listener.
Fetches posts, scores engagement opportunities, saves to Google Sheets.
Run via GitHub Actions daily, or manually: python src/community_monitor.py
"""

import os
import json
import logging
from datetime import datetime

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
    "score", "tags", "question_type", "status", "posted_date",
]


# ─── Sheets ───────────────────────────────────────────────────────────────────

def get_or_create_community_sheet(spreadsheet):
    try:
        return spreadsheet.worksheet(COMMUNITY_SHEET_NAME)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(COMMUNITY_SHEET_NAME, rows=2000, cols=len(COMMUNITY_HEADERS))
        ws.append_row(COMMUNITY_HEADERS)
        log.info("Created Community sheet")
        return ws


def get_known_urls(ws) -> set:
    urls = ws.col_values(3)  # post_url = column C
    return set(urls[1:])     # skip header


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
    log.info(f"Got {len(valid)} posts with text")
    return valid


# ─── Claude ───────────────────────────────────────────────────────────────────

def score_and_answer(post: dict, claude: anthropic.Anthropic) -> dict:
    comments_text = "\n".join([
        f"- {c.get('profileName', 'אנונימי')}: {c.get('text', '')}"
        for c in (post.get("topComments") or [])
    ]) or "אין תגובות עדיין"

    prompt = f"""אתה עוזר לגלעד מ"פשוט לאפות" - עסק שמוכר בצק פיצה נפוליטני, ערכות אפייה, רוטב ומוצרי גבינה בפתח תקווה.

פוסט מקבוצת פייסבוק:
מחבר: {post.get('user', {}).get('name', '')}
תאריך: {str(post.get('time', ''))[:10]}
תוכן הפוסט:
{post.get('text', '')}

תגובות קיימות:
{comments_text}

ענה בJSON בלבד (ללא markdown):
{{
  "score": <1-10>,
  "score_reason": "<משפט קצר למה הציון הזה>",
  "answer": "<תגובה בעברית מדוברת שגלעד יכול לפרסם - מקצועית, מועילה, לא שיווקית מדי. null אם לא רלוונטי>",
  "tags": ["<נושא>", "<נושא>"],
  "question_type": "<where_to_buy|recipe_help|technique|equipment|ingredient|general_pizza|not_relevant>"
}}

כללי ציון:
9-10: שאלה ישירה על בצק/אפייה/פיצה נפוליטנית שגלעד יכול לענות מניסיון, עדיין אין תשובה טובה
7-8: רלוונטי לתחום, גלעד יכול להוסיף ערך מקצועי
5-6: קשור לפיצה/טאבון אבל פחות ממוקד
1-4: לא קשור, פרסומת, או כבר יש תשובות מלאות

הדגש: גלעד מוכר בצק, ערכות, רוטב, קמח. ענה רק כשיש קשר לתחומים אלה."""

    try:
        resp = claude.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}]
        )
        return json.loads(resp.content[0].text)
    except Exception as e:
        log.warning(f"Claude error: {e}")
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
    known_urls = get_known_urls(ws)
    log.info(f"Known URLs: {len(known_urls)}")

    # Fetch posts
    posts = fetch_posts(monitoring_groups, apify_token)
    new_posts = [p for p in posts if p.get("url") not in known_urls]
    log.info(f"New posts to process: {len(new_posts)}")

    # Score and save
    claude = anthropic.Anthropic(api_key=anthropic_key)
    saved = 0

    for post in new_posts:
        url = post.get("url")
        log.info(f"Scoring: {url[:70]}...")
        result = score_and_answer(post, claude)

        comments_flat = " | ".join([
            f"{c.get('profileName','')}: {c.get('text','')}"
            for c in (post.get("topComments") or [])
        ])

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
            ", ".join(result.get("tags", [])),             # tags
            result.get("question_type", ""),               # question_type
            "pending",                                     # status
            "",                                            # posted_date
        ])
        known_urls.add(url)
        saved += 1

    log.info(f"Done. Saved {saved} new posts.")
    return saved


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    run_monitor()

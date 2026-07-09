"""
Just Bake - Community Monitor
Daily Facebook group opportunities, knowledge base, and content ideas.
"""

import streamlit as st
import os
import sys
import anthropic
from datetime import datetime, date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from sheets_client import get_spreadsheet

COMMUNITY_SHEET = "Community"

# ─── Auth ─────────────────────────────────────────────────────────────────────

def require_auth():
    if not st.user.is_logged_in:
        st.title("🌐 Community Monitor")
        st.login("google")
        st.stop()
    allowed = [e.strip() for e in st.secrets.get("allowed_emails", "").split(",") if e.strip()]
    if allowed and st.user.email not in allowed:
        st.error(f"❌ Access denied: {st.user.email}")
        if st.button("Log out"):
            st.logout()
        st.stop()

require_auth()

# ─── Data ─────────────────────────────────────────────────────────────────────

def load_community_data() -> list:
    spreadsheet = get_spreadsheet()
    try:
        ws = spreadsheet.worksheet(COMMUNITY_SHEET)
    except Exception:
        return []
    rows = ws.get_all_values()
    if len(rows) <= 1:
        return []
    headers = rows[0]
    return [dict(zip(headers, row)) for row in rows[1:] if any(row)]

def update_status(post_url: str, new_status: str):
    spreadsheet = get_spreadsheet()
    ws = spreadsheet.worksheet(COMMUNITY_SHEET)
    urls = ws.col_values(3)
    for i, url in enumerate(urls):
        if url == post_url:
            row_num = i + 1
            ws.update_cell(row_num, 13, new_status)           # status = col M
            if new_status == "posted":
                ws.update_cell(row_num, 14, date.today().strftime("%d/%m/%Y"))  # posted_date
            st.cache_data.clear()
            return


MY_ANSWER_HEADER = "my_answer"


def _my_answer_col(ws) -> int:
    """1-based index of the my_answer column; create it if the sheet lacks it."""
    headers = ws.row_values(1)
    if MY_ANSWER_HEADER in headers:
        return headers.index(MY_ANSWER_HEADER) + 1
    col = len(headers) + 1
    ws.update_cell(1, col, MY_ANSWER_HEADER)
    return col


def save_my_answer(post_url: str, text: str):
    """Store Gilad's own answer (the voice training set), mark the post posted."""
    spreadsheet = get_spreadsheet()
    ws = spreadsheet.worksheet(COMMUNITY_SHEET)
    my_col = _my_answer_col(ws)
    urls = ws.col_values(3)
    for i, url in enumerate(urls):
        if url == post_url:
            row_num = i + 1
            ws.update_cell(row_num, my_col, text)
            ws.update_cell(row_num, 13, "posted")
            ws.update_cell(row_num, 14, date.today().strftime("%d/%m/%Y"))
            st.cache_data.clear()
            return


def draft_in_my_voice(post: dict, examples: list, client) -> str:
    """Draft an answer copying Gilad's real saved answers (few-shot, same-topic first)."""
    qt = post.get("question_type", "")
    same = [e for e in examples if e.get("question_type") == qt]
    picked = (same + [e for e in examples if e not in same])[:8]
    ex_text = "\n\n".join(
        f"פוסט: {e.get('post_text','')[:200]}\nהתשובה שלי: {e.get('my_answer','')}"
        for e in picked
    )
    prompt = (
        "אתה כותב תשובה לפוסט בקבוצת פייסבוק, בדיוק בסגנון של גלעד.\n"
        "למד את הסגנון, הסלנג, הטון והאורך מהדוגמאות האמיתיות שלו:\n\n"
        f"{ex_text}\n\n"
        "עכשיו כתוב תשובה לפוסט הבא באותו סגנון בדיוק. תשובה בלבד:\n"
        f"פוסט: {post.get('post_text','')}"
    )
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()

# ─── UI ───────────────────────────────────────────────────────────────────────

st.title("🌐 Community Monitor")
st.divider()

TYPE_LABELS = {
    "recipe_help": "🍕 עזרה במתכון",
    "technique": "🎓 טכניקת אפייה",
    "where_to_buy": "🛒 איפה לקנות",
    "equipment": "🔥 ציוד וטאבון",
    "ingredient": "🧀 מרכיבים",
    "general_pizza": "🍕 פיצה כללי",
    "other": "💬 אחר",
}

with st.spinner("Loading..."):
    all_posts = load_community_data()

if not all_posts:
    st.info("No community data yet. The daily monitor runs every morning at 8:00.")
    st.caption("To run manually: GitHub → Actions → Community Monitor → Run workflow")
    st.stop()

tab1, tab2, tab3 = st.tabs([
    "📬 Opportunities",
    "📚 Knowledge Base",
    "💡 Content Ideas",
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — OPPORTUNITIES
# ══════════════════════════════════════════════════════════════════════════════

with tab1:
    CORE_TYPES = {"technique", "recipe_help", "ingredient", "where_to_buy"}
    VOICE_THRESHOLD = 10  # once you've saved this many, the AI can draft in your style
    RECENT_DAYS = 2       # only show the last day or two — no old backlog

    def _recent(p):
        raw = (p.get("post_date") or "")[:10]
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date() >= date.today() - timedelta(days=RECENT_DAYS)
        except ValueError:
            return False

    fc1, fc2 = st.columns([1, 1])
    with fc1:
        min_score = st.slider("ציון מינימלי", 1, 10, 7)
    with fc2:
        core_only = st.checkbox("רק נושאי ליבה (בצק/מתכון/קמח)", value=True)

    saved_answers = [p for p in all_posts if (p.get("my_answer") or "").strip()]
    st.caption(f"🧠 לומד את הסגנון שלך — {len(saved_answers)} תשובות שמורות")

    pending = [
        p for p in all_posts
        if p.get("status") == "pending"
        and int(p.get("score") or 0) >= min_score
        and (not core_only or p.get("question_type") in CORE_TYPES)
        and _recent(p)
    ]
    pending.sort(key=lambda x: int(x.get("score") or 0), reverse=True)

    if not pending:
        st.success("✅ אין פוסטים ממתינים")
    else:
        st.caption(f"{len(pending)} פוסטים ממתינים")

    for post in pending:
        score = int(post.get("score") or 0)
        dot = "🔴" if score >= 9 else "🟠" if score >= 7 else "🟡"
        url_key = post.get("post_url", "")
        draft_key = f"draft_{url_key}"

        with st.container(border=True):
            col1, col2 = st.columns([5, 1])
            with col1:
                st.markdown(f"{dot} **{score}/10** · {post.get('post_author', '')} · {post.get('post_date', '')[:10]}")
                st.caption(post.get("score_reason", ""))
            with col2:
                st.markdown(f"[פייסבוק ↗]({url_key})")

            st.info(post.get("post_text", ""), icon=None)

            if post.get("comments"):
                with st.expander("💬 תגובות קיימות"):
                    for line in post.get("comments", "").split(" | "):
                        if line.strip():
                            st.caption(f"• {line.strip()}")

            # Optional AI draft in your voice — only after you've taught it enough
            if len(saved_answers) >= VOICE_THRESHOLD:
                if st.button("✍️ טיוטה בסגנון שלי", key=f"voice_{url_key}"):
                    anthropic_key = st.secrets.get("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
                    if not anthropic_key:
                        st.error("חסר ANTHROPIC_API_KEY ב-secrets")
                    else:
                        with st.spinner("כותב בסגנון שלך..."):
                            st.session_state[draft_key] = draft_in_my_voice(
                                post, saved_answers, anthropic.Anthropic(api_key=anthropic_key)
                            )
                        st.rerun()

            my_text = st.text_area(
                "התשובה שלך:",
                value=st.session_state.get(draft_key, ""),
                height=150,
                key=f"my_{url_key}",
                placeholder="כתוב כאן בסגנון שלך...",
            )

            b1, b2 = st.columns(2)
            with b1:
                if st.button("✅ שמור ופרסמתי", key=f"save_{url_key}", use_container_width=True, type="primary"):
                    if my_text.strip():
                        save_my_answer(url_key, my_text.strip())
                        st.success("נשמר! ✅")
                        st.rerun()
                    else:
                        st.warning("כתוב תשובה קודם")
            with b2:
                if st.button("⏭️ דלג", key=f"skip_{url_key}", use_container_width=True):
                    update_status(url_key, "skipped")
                    st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — KNOWLEDGE BASE
# ══════════════════════════════════════════════════════════════════════════════

with tab2:
    st.subheader("📚 Knowledge Base")
    st.caption("כל השאלות והתשובות שנאספו — זהב לבלוג, וידאו ותוכן")

    answered = [p for p in all_posts if p.get("answer") and int(p.get("score") or 0) >= 5]

    col_search, col_filter = st.columns([3, 1])
    with col_search:
        search = st.text_input("חיפוש", placeholder="בצק, תנור, מוצרלה...", label_visibility="collapsed")
    with col_filter:
        q_types = ["הכל"] + sorted(set(p.get("question_type", "") for p in answered if p.get("question_type")))
        selected_type = st.selectbox("סוג", q_types, label_visibility="collapsed")

    filtered = answered
    if search:
        filtered = [p for p in filtered if search.lower() in (p.get("post_text","") + p.get("answer","")).lower()]
    if selected_type != "הכל":
        filtered = [p for p in filtered if p.get("question_type") == selected_type]

    filtered.sort(key=lambda x: int(x.get("score") or 0), reverse=True)

    st.caption(f"{len(filtered)} תשובות")

    for post in filtered[:50]:
        label = TYPE_LABELS.get(post.get("question_type", ""), post.get("question_type", ""))
        with st.expander(f"{label} · {post.get('post_text','')[:90]}..."):
            st.markdown("**שאלה:**")
            st.info(post.get("post_text", ""), icon=None)
            st.markdown("**תשובה:**")
            st.write(post.get("answer", ""))
            col_tags, col_link = st.columns([3, 1])
            col_tags.caption(f"🏷️ {post.get('tags','')} · 📅 {post.get('post_date','')[:10]}")
            col_link.markdown(f"[פייסבוק ↗]({post.get('post_url','')})")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — CONTENT IDEAS
# ══════════════════════════════════════════════════════════════════════════════

with tab3:
    st.subheader("💡 Content Ideas")
    st.caption("שאלות שחוזרות על עצמן = תוכן שאנשים רוצים")

    answered = [
        p for p in all_posts
        if p.get("question_type")
        and p.get("question_type") not in ("not_relevant", "noise", "other", "ad", "sale", "welcome")
        and p.get("post_type") not in ("sale", "ad", "welcome")
        and int(p.get("score") or 0) >= 4
    ]

    # Group by question_type
    from collections import Counter, defaultdict
    type_counts = Counter(p.get("question_type") for p in answered)
    type_posts = defaultdict(list)
    for p in answered:
        type_posts[p.get("question_type")].append(p)
    type_labels = TYPE_LABELS

    if "dismissed_topics" not in st.session_state:
        st.session_state.dismissed_topics = set()

    for q_type, count in type_counts.most_common():
        if q_type in ("noise", "not_relevant", "other", "ad", "sale", "welcome"):
            continue
        if q_type in st.session_state.dismissed_topics:
            continue
        label = type_labels.get(q_type, q_type)
        with st.container(border=True):
            col_title, col_dismiss = st.columns([6, 1])
            with col_title:
                st.markdown(f"### {label} — {count} שאלות")
            with col_dismiss:
                if st.button("✕", key=f"dismiss_{q_type}", help="הסתר נושא זה"):
                    st.session_state.dismissed_topics.add(q_type)
                    st.rerun()

            def get_anthropic_key():
                try:
                    return st.secrets["ANTHROPIC_API_KEY"]
                except Exception:
                    return os.getenv("ANTHROPIC_API_KEY")

            def generate_post(prompt_text, result_key):
                key = get_anthropic_key()
                if not key:
                    st.error("חסר anthropic_api_key ב-secrets")
                    return
                with st.spinner("כותב פוסט..."):
                    client = anthropic.Anthropic(api_key=key)
                    resp = client.messages.create(
                        model="claude-haiku-4-5-20251001",
                        max_tokens=1000,
                        messages=[{"role": "user", "content": prompt_text}]
                    )
                    st.session_state[result_key] = resp.content[0].text.strip()

            BASE_CONTEXT = """גלעד מוכר בצק פיצה נפוליטני, ערכות אפייה (5 כדורי בצק + גבינת מוצרלה + רוטב + קמח לפתיחה), בצק כוסמין ובצק ללא גלוטן. איסוף מרחוב נס ציונה 10, פתח תקווה. טלפון: 0525800797.
מחירים: מארז 130 ₪ | 2 מארזים 240 ₪ | 10 כדורי בצק 100 ₪
כלול תמיד: יש גם בצק ללא גלוטן ומקמח כוסמין | הבצק מתאים לאפייה בתנור ביתי ובטאבון | איסוף מרחוב נס ציונה 10, פתח תקווה (אם המושבות הותיקה) | 📲 0525800797 גלעד"""

            # Show each post individually with its own generate button
            samples = type_posts[q_type][:8]
            for i, p in enumerate(samples):
                post_key = f"gen_{q_type}_{i}"
                result_key = f"result_{q_type}_{i}"
                with st.container(border=False):
                    col_text, col_btn = st.columns([5, 1])
                    with col_text:
                        st.caption(f"• {p.get('post_text','')[:150]}...")
                    with col_btn:
                        if st.button("✍️", key=post_key, help="צור פוסט על הפוסט הזה"):
                            single_prompt = f"""אתה עוזר לגלעד מ"פשוט לאפות" לכתוב פוסט לפייסבוק.
{BASE_CONTEXT}

השראה — פוסט מהקהילה:
{p.get('post_text','')[:400]}

כתוב פוסט פייסבוק בעברית מדוברת שמספק ערך אמיתי בנושא הזה. לא שיווקי מדי. כותרת מושכת, תוכן מועיל (2-3 פסקאות), ובסוף ציין שגלעד יכול לעזור.
פוסט בלבד, ללא הסברים."""
                            generate_post(single_prompt, result_key)
                    if result_key in st.session_state:
                        st.text_area("ערוך:", value=st.session_state[result_key], height=300, key=f"txt_{result_key}")

            st.divider()
            # Category-level button — generates one post inspired by all posts in category
            cat_result_key = f"result_{q_type}_all"
            if st.button("✍️ צור פוסט על כל הנושא", key=f"gen_{q_type}_all", use_container_width=True):
                questions_text = "\n".join(f"- {p.get('post_text','')[:200]}" for p in type_posts[q_type][:8])
                cat_prompt = f"""אתה עוזר לגלעד מ"פשוט לאפות" לכתוב פוסט לפייסבוק.
{BASE_CONTEXT}

בקבוצות פייסבוק, {count} אנשים עסקו בנושא "{label}":
{questions_text}

כתוב פוסט פייסבוק שמספק ערך אמיתי — תשובה מקצועית, כתובה בעברית מדוברת ואנושית. כותרת/hook מושכת, תוכן מועיל (2-3 פסקאות), ובסוף ציין שגלעד יכול לעזור.
פוסט בלבד, ללא הסברים."""
                generate_post(cat_prompt, cat_result_key)
            if cat_result_key in st.session_state:
                st.text_area("ערוך:", value=st.session_state[cat_result_key], height=300, key=f"txt_{cat_result_key}")

st.caption("Just Bake • Pashut La'afot 🍕")

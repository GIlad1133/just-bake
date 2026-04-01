"""
Just Bake - Community Monitor
Daily Facebook group opportunities, knowledge base, and content ideas.
"""

import streamlit as st
import os
import sys
from datetime import datetime, date

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

# ─── UI ───────────────────────────────────────────────────────────────────────

st.title("🌐 Community Monitor")
st.divider()

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
    min_score = st.slider("Minimum score", 1, 10, 7)

    pending = [
        p for p in all_posts
        if p.get("status") == "pending"
        and p.get("status") != "noise"
        and int(p.get("score") or 0) >= min_score
        and p.get("answer")
    ]
    pending.sort(key=lambda x: int(x.get("score") or 0), reverse=True)

    if not pending:
        st.success(f"✅ No pending opportunities with score ≥ {min_score}")
    else:
        st.caption(f"{len(pending)} opportunities waiting")

    for post in pending:
        score = int(post.get("score") or 0)
        score_color = "🔴" if score >= 9 else "🟠" if score >= 7 else "🟡"

        with st.container(border=True):
            col1, col2 = st.columns([5, 1])
            with col1:
                st.markdown(f"{score_color} **Score {score}/10** · {post.get('post_author', '')} · {post.get('post_date', '')[:10]}")
                st.caption(post.get("score_reason", ""))
            with col2:
                st.markdown(f"[פתח בפייסבוק ↗]({post.get('post_url', '')})")

            # Post text
            with st.expander("📝 הפוסט המקורי"):
                st.write(post.get("post_text", ""))
                if post.get("comments"):
                    st.divider()
                    st.caption("תגובות קיימות:")
                    for line in post.get("comments", "").split(" | "):
                        if line.strip():
                            st.caption(f"• {line.strip()}")

            # Answer
            st.markdown("**התגובה המוצעת:**")
            edited_answer = st.text_area(
                "ערוך לפי הצורך:",
                value=post.get("answer", ""),
                height=150,
                key=f"ans_{post.get('post_url','')}",
                label_visibility="collapsed"
            )

            col_posted, col_skip = st.columns(2)
            with col_posted:
                if st.button("✅ פרסמתי", key=f"post_{post.get('post_url','')}", use_container_width=True):
                    update_status(post.get("post_url", ""), "posted")
                    st.success("מסומן כפורסם!")
                    st.rerun()
            with col_skip:
                if st.button("⏭️ דלג", key=f"skip_{post.get('post_url','')}", use_container_width=True):
                    update_status(post.get("post_url", ""), "skipped")
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
        with st.expander(f"[{post.get('question_type','')}] {post.get('post_text','')[:80]}..."):
            st.markdown("**שאלה:**")
            st.write(post.get("post_text", ""))
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

    answered = [p for p in all_posts if p.get("question_type") and p.get("question_type") != "not_relevant"]

    # Group by question_type
    from collections import Counter, defaultdict
    type_counts = Counter(p.get("question_type") for p in answered)
    type_posts = defaultdict(list)
    for p in answered:
        type_posts[p.get("question_type")].append(p)

    type_labels = {
        "recipe_help": "🍕 עזרה במתכון",
        "technique": "🎓 טכניקת אפייה",
        "where_to_buy": "🛒 איפה לקנות",
        "equipment": "🔥 ציוד וטאבון",
        "ingredient": "🧀 מרכיבים",
        "general_pizza": "🍕 פיצה כללי",
        "other": "💬 אחר",
    }

    for q_type, count in type_counts.most_common():
        label = type_labels.get(q_type, q_type)
        with st.container(border=True):
            st.markdown(f"### {label} — {count} שאלות")

            # Content suggestions based on type
            suggestions = {
                "recipe_help": "📹 וידאו: מתכון שלב אחרי שלב | ✍️ בלוג: מדריך מקיף",
                "technique": "📹 וידאו: טיפים מקצועיים | 📸 פוסט: before/after",
                "where_to_buy": "📣 פוסט פייסבוק: היכן לקנות את המוצרים שלנו",
                "equipment": "📹 וידאו: איך לבחור טאבון | ✍️ בלוג: המדריך לציוד",
                "ingredient": "📣 פוסט: על המרכיבים שלנו | 📹 וידאו: השוואת מוצרים",
                "general_pizza": "📹 וידאו כללי | 📣 פוסט אינפורמטיבי",
            }
            st.caption(f"💡 רעיונות: {suggestions.get(q_type, 'תוכן על הנושא')}")

            # Show sample questions
            samples = type_posts[q_type][:3]
            for p in samples:
                st.caption(f"• {p.get('post_text','')[:100]}...")

st.caption("Just Bake • Pashut La'afot 🍕")

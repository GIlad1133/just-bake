"""
Just Bake - Marketing Hub
Generate Hebrew social media posts and track content calendar.
"""

import streamlit as st
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from sheets_client import get_spreadsheet
from products import PRODUCTS

# ─── Auth ─────────────────────────────────────────────────────────────────────

def require_auth():
    if not st.user.is_logged_in:
        st.title("📣 Just Bake - Marketing")
        st.info("Log in with your Google account.")
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

@st.cache_data(ttl=300)
def get_price_list() -> dict:
    """Get most recent price per product across all orders."""
    spreadsheet = get_spreadsheet()
    worksheet = spreadsheet.get_worksheet(0)
    rows = worksheet.get_all_values()[1:]
    prices = {}
    for row in rows:
        for pi, product in enumerate(PRODUCTS):
            prefix = product["column_prefix"]
            try:
                price_idx = 24 if pi == 9 else 6 + 2 * pi + 1
                price = float(row[price_idx]) if len(row) > price_idx and row[price_idx] else 0.0
                if price > 0:
                    prices[prefix] = price
            except (ValueError, IndexError):
                pass
    return prices

# ─── UI ───────────────────────────────────────────────────────────────────────

st.title("📣 Marketing Hub")
st.divider()

tab1, tab2, tab3 = st.tabs(["✍️ Post Generator", "📅 Content Calendar", "✅ Group Tracker"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — POST GENERATOR
# ══════════════════════════════════════════════════════════════════════════════

with tab1:
    st.subheader("Generate Hebrew Post")

    col1, col2 = st.columns(2)
    with col1:
        platform = st.selectbox("Platform", [
            "קבוצות פייסבוק",
            "אינסטגרם",
            "טיקטוק",
        ])
    with col2:
        post_type = st.selectbox("Post Type", [
            "מחירון שבועי",
            "מבצע / הנחה",
            "טיפ על בצק / פיצה",
            "מוצר חדש בסטוק",
            "פוסט אישי / סיפור",
        ])

    extra_context = ""
    if post_type == "מבצע / הנחה":
        extra_context = st.text_input("פרטי המבצע", placeholder="לדוגמה: 10% הנחה על ערכה נפוליטנית עד יום שישי")
    elif post_type == "טיפ על בצק / פיצה":
        extra_context = st.text_input("נושא הטיפ", placeholder="לדוגמה: איך מקבלים קורניצ'ונה מושלמת בתנור ביתי")
    elif post_type == "מוצר חדש בסטוק":
        product_names = [p["hebrew"] for p in PRODUCTS]
        extra_context = st.selectbox("איזה מוצר?", product_names)
    elif post_type == "פוסט אישי / סיפור":
        extra_context = st.text_input("על מה הסיפור?", placeholder="לדוגמה: לקוח ששלח תמונה של פיצה מטורפת שעשה עם הבצק שלי")

    tone = st.select_slider("טון הפוסט", ["רשמי", "ידידותי", "שובב וכיפי"], value="ידידותי")

    # Build price context from sheet
    try:
        prices = get_price_list()
        price_lines = [
            f"{p['hebrew']}: ₪{prices[p['column_prefix']]:.0f}"
            for p in PRODUCTS if prices.get(p["column_prefix"])
        ]
        price_context = "\n".join(price_lines) if price_lines else "מחירים לא זמינים"
    except Exception:
        price_context = "מחירים לא זמינים"

    if st.button("🪄 צור פוסט", type="primary", use_container_width=True):
        api_key = st.secrets.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            st.error("❌ ANTHROPIC_API_KEY חסר ב-Streamlit secrets.")
        else:
            platform_instructions = {
                "קבוצות פייסבוק": (
                    "פוסט לקבוצת פייסבוק. כתוב 3-5 פסקאות קצרות. "
                    "כלול מחירים בצורה ברורה. סיים עם קריאה לפעולה - 'שלחו הודעה' או 'וואטסאפ בפרופיל'. "
                    "אין צורך בהאשטגים."
                ),
                "אינסטגרם": (
                    "כיתוב לאינסטגרם. שורה ראשונה = הוק חזק. שאר הטקסט קצר ועם ירידות שורה. "
                    "בסוף הוסף 6-8 האשטגים בעברית כמו #פיצהביתית #בצקנאפוליטני #פשוטלאפות #פיצה #אפייהביתית. "
                    "ללא קו תחתון בהאשטגים!"
                ),
                "טיקטוק": (
                    "כיתוב לטיקטוק. מאוד קצר ומחוספס. משפט הוק אחד חזק. "
                    "3-5 האשטגים מעורב עברית ואנגלית: #פיצה #pizza #פשוטלאפות #NapolitanPizza. "
                    "ללא קו תחתון!"
                ),
            }[platform]

            prompt = f"""אתה כותב תוכן לרשתות חברתיות עבור "פשוט לאפות" - עסק של גלעד מפתח תקווה שמוכר בצק פיצה נפוליטני, ערכות אפייה ומוצרים נלווים.

כתוב פוסט מסוג "{post_type}" בעברית מדוברת וטבעית - לא עברית ספרותית או רשמית.
טון: {tone}.
{f'פרטים נוספים: {extra_context}' if extra_context else ''}

{platform_instructions}

מחירון נוכחי:
{price_context}

כללים חשובים:
- עברית מדוברת, לא רשמית - כמו שגלעד היה כותב לחבר
- דוגרי ואמיתי - ישראלים שונאים שיווק מתנפח
- שורה ראשונה = הוק שגורם לאנשים לעצור לגלול
- ירידות שורה בין פסקאות (קוראים ישראלים במובייל)
- אל תזכיר סדנאות - מושהות כרגע
- כתוב רק את הפוסט עצמו, ללא הסברים"""

            with st.spinner("יוצר פוסט..."):
                import anthropic
                client = anthropic.Anthropic(api_key=api_key)
                message = client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=700,
                    messages=[{"role": "user", "content": prompt}]
                )
                st.session_state["generated_post"] = message.content[0].text

    if "generated_post" in st.session_state:
        st.divider()
        edited = st.text_area(
            "הפוסט המוכן — ערוך לפי הצורך:",
            value=st.session_state["generated_post"],
            height=320
        )
        st.caption(f"{len(edited)} תווים")
        col_copy, col_regen = st.columns(2)
        with col_regen:
            if st.button("🔄 צור מחדש", use_container_width=True):
                del st.session_state["generated_post"]
                st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — CONTENT CALENDAR
# ══════════════════════════════════════════════════════════════════════════════

with tab2:
    st.subheader("לוח תוכן שבועי")

    today = date.today()
    days_since_sunday = (today.weekday() + 1) % 7
    week_start = today - timedelta(days=days_since_sunday)
    st.caption(f"שבוע {week_start.strftime('%d/%m')} — {(week_start + timedelta(6)).strftime('%d/%m/%Y')}")

    # Recommended schedule based on Israeli social media patterns
    schedule = [
        ("ראשון",  week_start,              "קבוצות פייסבוק",      "09:00",       "מחירון שבועי + הזמנות",       "🟢"),
        ("שני",    week_start + timedelta(1),"—",                    "—",           "יום מנוחה מפרסום",            "⚪"),
        ("שלישי",  week_start + timedelta(2),"אינסטגרם / טיקטוק",   "19:00",       "תוכן / טיפ / וידאו",          "🟢"),
        ("רביעי",  week_start + timedelta(3),"—",                    "—",           "יום מנוחה מפרסום",            "⚪"),
        ("חמישי",  week_start + timedelta(4),"קבוצות פייסבוק",      "09:00",       "מבצע / הזמנות אחרונות",       "🟢"),
        ("שישי",   week_start + timedelta(5),"⚠️ עד 12:00 בלבד",    "לפני 12:00",  "שבת — פחות פעילות",           "🟡"),
        ("שבת",    week_start + timedelta(6),"❌ לא לפרסם",          "—",           "שבת — אפס פעילות",            "🔴"),
    ]

    header = st.columns([1.2, 1.2, 2, 1, 2.5])
    header[0].markdown("**יום**")
    header[1].markdown("**תאריך**")
    header[2].markdown("**פלטפורמה**")
    header[3].markdown("**שעה**")
    header[4].markdown("**תוכן מומלץ**")

    for day_name, day_date, platform_rec, time_rec, content_rec, indicator in schedule:
        is_today = day_date == today
        cols = st.columns([1.2, 1.2, 2, 1, 2.5])
        label = f"**{day_name}**" if is_today else day_name
        cols[0].markdown(f"{indicator} {label}" + (" ← היום" if is_today else ""))
        cols[1].write(day_date.strftime("%d/%m"))
        cols[2].write(platform_rec)
        cols[3].write(time_rec)
        cols[4].write(content_rec)

    st.divider()
    st.info("⏰ שעות שיא לפרסום בישראל: 8-9 בבוקר, 12-13 בצהריים, 19-21 בערב (א׳-ה׳)")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — GROUP TRACKER
# ══════════════════════════════════════════════════════════════════════════════

with tab3:
    st.subheader("מעקב קבוצות פייסבוק")
    st.caption("סמן אילו קבוצות פרסמת השבוע")

    raw_groups = st.secrets.get("facebook_groups", "")
    groups = [g.strip() for g in raw_groups.split(",") if g.strip()] if raw_groups else []

    if not groups:
        st.warning("לא הוגדרו קבוצות. הוסף `facebook_groups` ל-Streamlit secrets:")
        st.code('facebook_groups = "שם קבוצה 1, שם קבוצה 2, שם קבוצה 3"')
    else:
        if "group_checks" not in st.session_state:
            st.session_state.group_checks = {}

        for group in groups:
            checked = st.checkbox(
                group,
                key=f"grp_{group}",
                value=st.session_state.group_checks.get(group, False)
            )
            st.session_state.group_checks[group] = checked

        posted = sum(1 for v in st.session_state.group_checks.values() if v)
        total = len(groups)

        st.divider()
        st.progress(posted / total if total > 0 else 0)

        if posted == total:
            st.success(f"✅ פרסמת בכל {total} הקבוצות השבוע!")
        else:
            st.info(f"פרסמת ב-{posted} מתוך {total} קבוצות — נשארו {total - posted}")

        if st.button("🔄 איפוס לשבוע חדש", use_container_width=True):
            st.session_state.group_checks = {}
            st.rerun()

st.caption("Just Bake • Pashut La'afot 🍕")

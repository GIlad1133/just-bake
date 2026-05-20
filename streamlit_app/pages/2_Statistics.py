"""
Just Bake - Statistics
Aggregate sales/product stats over a configurable date range.
"""

import streamlit as st
from datetime import datetime, date, timedelta
import os
import sys
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))           # streamlit_app/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))  # project root

from sheets_client import get_sheets_client  # noqa: F401 (ensure cached resource is set up)
from date_widget import date_input_dmy as _date_input_dmy
from products import PRODUCTS  # noqa: F401
from orders_data import fetch_all_orders

load_dotenv()


# ─── Auth ─────────────────────────────────────────────────────────────────────

def require_auth():
    if not st.user.is_logged_in:
        st.title("🔐 Just Bake - סטטיסטיקות")
        st.info("Log in with your Google account to view stats.")
        st.login("google")
        st.stop()

    allowed = [
        e.strip()
        for e in st.secrets.get("allowed_emails", "").split(",")
        if e.strip()
    ]
    if allowed and st.user.email not in allowed:
        st.error(f"❌ Access denied: {st.user.email} is not authorized.")
        if st.button("Log out"):
            st.logout()
        st.stop()


require_auth()


# ─── Header ───────────────────────────────────────────────────────────────────

col_title, col_logout = st.columns([5, 1])
with col_title:
    st.title("📊 Just Bake - סטטיסטיקות")
with col_logout:
    if st.button("Logout", use_container_width=True):
        st.logout()

st.caption(f"👤 Logged in as {st.user.email}")
st.divider()


# ─── Date range selector ─────────────────────────────────────────────────────

today = date.today()
this_month_start = today.replace(day=1)
prev_month_end = this_month_start - timedelta(days=1)
prev_month_start = prev_month_end.replace(day=1)

PRESETS = {
    "החודש": (this_month_start, today),
    "החודש שעבר": (prev_month_start, prev_month_end),
    "7 ימים אחרונים": (today - timedelta(days=6), today),
    "30 ימים אחרונים": (today - timedelta(days=29), today),
    "השנה": (date(today.year, 1, 1), today),
    "מותאם אישית": None,
}

st.markdown("### טווח תאריכים")
preset = st.radio(
    "בחר טווח",
    options=list(PRESETS.keys()),
    horizontal=True,
    index=0,
    label_visibility="collapsed",
)

if PRESETS[preset] is not None:
    range_from, range_to = PRESETS[preset]
    st.caption(
        f"📅 {range_from.strftime('%d/%m/%Y')} עד {range_to.strftime('%d/%m/%Y')}  ·  "
        f"{(range_to - range_from).days + 1} ימים"
    )
else:
    c1, c2 = st.columns(2)
    with c1:
        range_from = _date_input_dmy(
            "מ-",
            value=this_month_start,
            key="stats_from",
        )
    with c2:
        range_to = _date_input_dmy(
            "עד",
            value=today,
            key="stats_to",
        )

if range_from > range_to:
    st.error("תאריך התחלה חייב להיות לפני תאריך סיום")
    st.stop()

st.divider()


# ─── Fetch + filter ─────────────────────────────────────────────────────────

with st.spinner("טוען הזמנות..."):
    all_orders = fetch_all_orders()

filtered = [
    o for o in all_orders
    if o["date"] and range_from <= o["date"] <= range_to
]

if not filtered:
    st.info("אין הזמנות בטווח התאריכים שנבחר")
    st.stop()


# ─── Aggregations ────────────────────────────────────────────────────────────

total_revenue = sum(o["amount"] for o in filtered)

def _sum_qty(prefix):
    return sum((o["products"].get(f"{prefix}_qty") or 0) for o in filtered)

# Kit and standalone counts
n_kit  = _sum_qty("neapolitan_kit")
s_kit  = _sum_qty("spelt_kit")
gf_kit = _sum_qty("gluten_free_kit")
n_dough  = _sum_qty("neapolitan_dough")
s_dough  = _sum_qty("spelt_dough")
gf_dough = _sum_qty("gluten_free_dough")

# Total balls (kit × 5 + standalone)
n_balls  = n_dough + n_kit * 5
s_balls  = s_dough + s_kit * 5
gf_balls = gf_dough + gf_kit * 5
total_balls = n_balls + s_balls + gf_balls

# Other products
cheese        = _sum_qty("cheese")
white_sauce   = _sum_qty("white_sauce")
red_sauce     = _sum_qty("red_sauce")
opening_flour = _sum_qty("opening_flour")
workshops     = _sum_qty("pizza_sandwich")

# Fresh/frozen breakdown for Neapolitan
def _nean_count(o):
    p = o["products"]
    return (p.get("neapolitan_dough_qty") or 0) + (p.get("neapolitan_kit_qty") or 0) * 5

fresh_balls  = sum(_nean_count(o) for o in filtered if o["dough_type"] == "fresh")
frozen_balls = sum(_nean_count(o) for o in filtered if o["dough_type"] == "frozen")
unspec_balls = n_balls - fresh_balls - frozen_balls


# ─── Display ──────────────────────────────────────────────────────────────────

st.subheader(f"📦 {len(filtered)} הזמנות בטווח")
days_in_range = (range_to - range_from).days + 1
avg_balls_per_day = total_balls / max(days_in_range, 1)

m1, m2, m3, m4 = st.columns(4)
with m1: st.metric("💰 הכנסות", f"₪{total_revenue:,.0f}")
with m2: st.metric("הזמנות", len(filtered))
with m3: st.metric("סך כדורי בצק", total_balls)
with m4: st.metric("ממוצע כדורים/יום", f"{avg_balls_per_day:.1f}")

st.divider()

# ─── Dough balls by type ──────────────────────────────────────────────────────
st.markdown("### 🍞 כדורי בצק לפי סוג")
db1, db2, db3 = st.columns(3)
with db1: st.metric("נאפוליטני", n_balls)
with db2: st.metric("כוסמין", s_balls)
with db3: st.metric("ללא גלוטן", gf_balls)

if n_balls > 0:
    st.caption(
        f"מתוך הנאפוליטני:  🌿 טרי **{fresh_balls}**  ·  "
        f"❄️ קפוא **{frozen_balls}**  ·  "
        f"❓ לא תויג **{unspec_balls}**"
    )

st.divider()

# ─── Kits ─────────────────────────────────────────────────────────────────────
st.markdown("### 🧰 מארזים")
k1, k2, k3 = st.columns(3)
with k1: st.metric("מארז נאפוליטני", n_kit)
with k2: st.metric("מארז כוסמין", s_kit)
with k3: st.metric("מארז ללא גלוטן", gf_kit)
st.caption(f"כל מארז = 5 כדורים. סה״כ {n_kit + s_kit + gf_kit} מארזים בטווח.")

st.divider()

# ─── Standalone doughs ───────────────────────────────────────────────────────
if n_dough or s_dough or gf_dough:
    st.markdown("### בצקים בודדים")
    sd1, sd2, sd3 = st.columns(3)
    with sd1: st.metric("נאפוליטני בודד", n_dough)
    with sd2: st.metric("כוסמין בודד", s_dough)
    with sd3: st.metric("ללא גלוטן בודד", gf_dough)
    st.divider()

# ─── Other products ──────────────────────────────────────────────────────────
st.markdown("### שאר המוצרים")
op1, op2, op3, op4 = st.columns(4)
with op1: st.metric("גבינה", cheese)
with op2: st.metric("רוטב לבן", white_sauce)
with op3: st.metric("רוטב אדום", red_sauce)
with op4: st.metric("קמח פתיחה", opening_flour)

if workshops:
    st.metric("סדנת פיצה", workshops)

st.divider()

# ─── Top customers ──────────────────────────────────────────────────────────
from collections import Counter
customer_revenue = Counter()
customer_orders = Counter()
for o in filtered:
    customer_revenue[o["customer"]] += o["amount"]
    customer_orders[o["customer"]] += 1

st.markdown("### 🏆 לקוחות מובילים")
top = customer_revenue.most_common(10)
if top:
    for i, (cust, rev) in enumerate(top, 1):
        count = customer_orders[cust]
        st.markdown(
            f"{i}. **{cust}**  ·  ₪{rev:,.0f}  ·  "
            f"{count} הזמנ{'ות' if count != 1 else 'ה'}"
        )

st.divider()

# ─── Refresh button ──────────────────────────────────────────────────────────
if st.button("🔄 רענן נתונים"):
    from orders_data import invalidate_orders_cache
    invalidate_orders_cache()
    st.rerun()

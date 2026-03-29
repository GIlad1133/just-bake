"""
Just Bake - Analytics Dashboard
Sales insights: revenue over time, top customers, product breakdown.
"""

import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))           # streamlit_app/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))  # project root
from sheets_client import get_spreadsheet
from products import PRODUCTS

# ─── Auth ─────────────────────────────────────────────────────────────────────

def require_auth():
    if not st.user.is_logged_in:
        st.title("📊 Just Bake - Analytics")
        st.info("Log in with your Google account to access analytics.")
        st.login("google")
        st.stop()
    allowed = [e.strip() for e in st.secrets.get("allowed_emails", "").split(",") if e.strip()]
    if allowed and st.user.email not in allowed:
        st.error(f"❌ Access denied: {st.user.email}")
        if st.button("Log out"):
            st.logout()
        st.stop()

require_auth()

# ─── Data Loading ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def load_data() -> pd.DataFrame:
    spreadsheet = get_spreadsheet()
    worksheet = spreadsheet.get_worksheet(0)
    rows = worksheet.get_all_values()
    if len(rows) <= 1:
        return pd.DataFrame()

    records = []
    for row in rows[1:]:
        if len(row) < 3 or not row[1].strip():
            continue
        try:
            date = datetime.strptime(row[0].strip(), "%d/%m/%Y")
        except ValueError:
            continue

        try:
            amount = float(row[2]) if row[2] else 0.0
        except ValueError:
            amount = 0.0

        payment = row[3].strip() if len(row) > 3 else ""

        # Product revenue per product
        product_data = {"date": date, "customer": row[1].strip(), "amount": amount, "payment": payment}
        for pi, product in enumerate(PRODUCTS):
            prefix = product["column_prefix"]
            try:
                if pi == 9:  # Cheese: price at 24, qty at 25
                    price = float(row[24]) if len(row) > 24 and row[24] else 0.0
                    qty = float(row[25]) if len(row) > 25 and row[25] else 0.0
                else:
                    qty_idx = 6 + 2 * pi
                    price_idx = qty_idx + 1
                    qty = float(row[qty_idx]) if len(row) > qty_idx and row[qty_idx] else 0.0
                    price = float(row[price_idx]) if len(row) > price_idx and row[price_idx] else 0.0
                product_data[prefix] = qty * price
                product_data[f"{prefix}_qty"] = qty
            except (ValueError, IndexError):
                product_data[prefix] = 0.0
                product_data[f"{prefix}_qty"] = 0.0

        records.append(product_data)

    return pd.DataFrame(records)

# ─── UI ───────────────────────────────────────────────────────────────────────

st.title("📊 Analytics")
st.divider()

with st.spinner("Loading data..."):
    df = load_data()

if df.empty:
    st.info("No orders found.")
    st.stop()

# ─── Filters ──────────────────────────────────────────────────────────────────

col_f1, col_f2 = st.columns(2)
with col_f1:
    period = st.selectbox("Group by", ["Month", "Week", "Day"], index=0)
with col_f2:
    months_back = st.selectbox("Show last", [3, 6, 12, 24, 9999], format_func=lambda x: "All time" if x == 9999 else f"{x} months", index=1)

df["date"] = pd.to_datetime(df["date"])

if months_back != 9999:
    cutoff = pd.Timestamp.now() - pd.DateOffset(months=months_back)
    df = df[df["date"] >= cutoff]

if df.empty:
    st.info("No orders in the selected period.")
    st.stop()

# ─── KPI Row ──────────────────────────────────────────────────────────────────

paid = df[df["payment"] != "לא שולם"]
total_revenue = paid["amount"].sum()
total_orders = len(df)
avg_order = paid["amount"].mean() if not paid.empty else 0
unique_customers = df["customer"].nunique()

k1, k2, k3, k4 = st.columns(4)
k1.metric("Total Revenue", f"₪{total_revenue:,.0f}")
k2.metric("Orders", total_orders)
k3.metric("Avg Order Value", f"₪{avg_order:,.0f}")
k4.metric("Customers", unique_customers)

st.divider()

# ─── Revenue Over Time ────────────────────────────────────────────────────────

st.subheader("Revenue Over Time")

freq = {"Month": "ME", "Week": "W", "Day": "D"}[period]
label_format = {"Month": "%b %Y", "Week": "%d %b", "Day": "%d %b"}[period]

revenue_ts = (
    paid.set_index("date")["amount"]
    .resample(freq)
    .sum()
    .reset_index()
    .rename(columns={"date": "Period", "amount": "Revenue"})
)
revenue_ts["Label"] = revenue_ts["Period"].dt.strftime(label_format)

chart = alt.Chart(revenue_ts).mark_bar(color="#FF6B35").encode(
    x=alt.X("Label:O", sort=None, title=None),
    y=alt.Y("Revenue:Q", title="₪"),
    tooltip=["Label:O", alt.Tooltip("Revenue:Q", format=",.0f", title="₪")],
).properties(height=300)
st.altair_chart(chart, use_container_width=True)

st.divider()

# ─── Product Breakdown ────────────────────────────────────────────────────────

st.subheader("Revenue by Product")

product_revenue = {}
for product in PRODUCTS:
    prefix = product["column_prefix"]
    total = df[prefix].sum()
    if total > 0:
        product_revenue[product["hebrew"]] = total

if product_revenue:
    prod_df = pd.DataFrame(
        list(product_revenue.items()), columns=["Product", "Revenue"]
    ).sort_values("Revenue", ascending=False)

    chart2 = alt.Chart(prod_df).mark_bar(color="#4ECDC4").encode(
        x=alt.X("Revenue:Q", title="₪"),
        y=alt.Y("Product:O", sort="-x", title=None),
        tooltip=["Product:O", alt.Tooltip("Revenue:Q", format=",.0f", title="₪")],
    ).properties(height=max(200, len(prod_df) * 40))
    st.altair_chart(chart2, use_container_width=True)

st.divider()

# ─── Top Customers ────────────────────────────────────────────────────────────

st.subheader("Top Customers")

top_customers = (
    paid.groupby("customer")
    .agg(revenue=("amount", "sum"), orders=("amount", "count"))
    .sort_values("revenue", ascending=False)
    .head(15)
    .reset_index()
)
top_customers["revenue_fmt"] = top_customers["revenue"].apply(lambda x: f"₪{x:,.0f}")

chart3 = alt.Chart(top_customers).mark_bar(color="#A8E6CF").encode(
    x=alt.X("revenue:Q", title="₪"),
    y=alt.Y("customer:O", sort="-x", title=None),
    tooltip=[
        "customer:O",
        alt.Tooltip("revenue:Q", format=",.0f", title="₪"),
        alt.Tooltip("orders:Q", title="Orders"),
    ],
).properties(height=max(200, len(top_customers) * 35))
st.altair_chart(chart3, use_container_width=True)

st.divider()

# ─── Payment Method Split ─────────────────────────────────────────────────────

st.subheader("Payment Methods")

payment_counts = df["payment"].value_counts().reset_index()
payment_counts.columns = ["Method", "Count"]

chart4 = alt.Chart(payment_counts).mark_arc(innerRadius=50).encode(
    theta=alt.Theta("Count:Q"),
    color=alt.Color("Method:N", legend=alt.Legend(title=None)),
    tooltip=["Method:O", "Count:Q"],
).properties(height=250)
st.altair_chart(chart4, use_container_width=True)

st.caption("Just Bake • Pashut La'afot 🍕")

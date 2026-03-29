"""
Just Bake - Order Entry UI
Streamlit web app for entering new pizza orders.
"""

import streamlit as st
from datetime import datetime
import uuid
import os
from dotenv import load_dotenv
from products import PRODUCTS, PAYMENT_METHODS
from sheets_client import get_sheets_client, get_spreadsheet

load_dotenv()

st.set_page_config(
    page_title="Just Bake - New Order",
    page_icon="🍕",
    layout="wide"
)

# ─── Google OAuth Authentication ──────────────────────────────────────────────

def require_auth():
    """Gate the app behind Google OAuth. Stops execution if not authorized."""
    if not st.user.is_logged_in:
        st.title("🍕 Just Bake - Login")
        st.info("Log in with your Google account to access the order system.")
        st.login("google")
        st.stop()

    allowed = [e.strip() for e in st.secrets.get("allowed_emails", "").split(",") if e.strip()]
    if allowed and st.user.email not in allowed:
        st.error(f"❌ Access denied: {st.user.email} is not authorized.")
        if st.button("Log out"):
            st.logout()
        st.stop()

require_auth()

# ─── Form Version Counter (reliable form clear) ───────────────────────────────
# Incrementing this changes all widget keys, forcing Streamlit to recreate them fresh.

if "form_version" not in st.session_state:
    st.session_state.form_version = 0

v = st.session_state.form_version  # short alias used in all widget keys

# ─── Customer Data ────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def get_existing_customers():
    """
    Returns {customer_name: {"phone": ..., "prices": {prefix: price}}}
    Reads last order per customer to pre-fill prices.
    """
    spreadsheet = get_spreadsheet()
    if spreadsheet is None:
        return {}
    try:
        worksheet = spreadsheet.get_worksheet(0)
        all_data = worksheet.get_all_values()[1:]

        customers = {}
        for row in all_data:
            name = row[1].strip() if len(row) > 1 else ""
            if not name:
                continue
            phone = row[28].strip() if len(row) > 28 else ""

            # Extract last price per product (overwrite to keep most recent)
            prices = {}
            for i, product in enumerate(PRODUCTS):
                prefix = product["column_prefix"]
                if i == 9:  # Cheese: price first (col Y=24), qty second (col Z=25)
                    price_idx = 24
                else:
                    price_idx = 6 + 2 * i + 1  # H,J,L,N,P,R,T,V,X

                try:
                    val = float(row[price_idx]) if len(row) > price_idx and row[price_idx] else 0.0
                    if val > 0:
                        prices[f"{prefix}_price"] = val
                except (ValueError, IndexError):
                    pass

            customers[name] = {"phone": phone, "prices": prices}
        return customers
    except Exception as e:
        st.warning(f"Could not load existing customers: {e}")
        return {}

# ─── Order Logic ──────────────────────────────────────────────────────────────

def calculate_total(product_data):
    total = 0.0
    for product in PRODUCTS:
        prefix = product["column_prefix"]
        qty = product_data.get(f"{prefix}_qty") or 0
        price = product_data.get(f"{prefix}_price") or 0.0
        total += qty * price
    return total

def submit_order(customer_name, order_date, payment_method, product_data, phone="", business_id=""):
    spreadsheet = get_spreadsheet()
    if spreadsheet is None:
        return False, "Failed to connect to Google Sheets"
    try:
        worksheet = spreadsheet.get_worksheet(0)
        row_id = str(uuid.uuid4())
        total = calculate_total(product_data)
        formatted_date = order_date.strftime("%d/%m/%Y")

        row_data = [
            formatted_date,
            customer_name,
            total,
            PAYMENT_METHODS[payment_method],
            "",   # create invoice
            "",   # invoice_url
        ]

        for i, product in enumerate(PRODUCTS):
            prefix = product["column_prefix"]
            if i == 9:  # Cheese: Price then Qty
                row_data.append(product_data.get(f"{prefix}_price") or 0.0)
                row_data.append(product_data.get(f"{prefix}_qty") or 0)
            else:
                row_data.append(product_data.get(f"{prefix}_qty") or 0)
                row_data.append(product_data.get(f"{prefix}_price") or 0.0)

        row_data += [row_id, "", phone or "", business_id or ""]
        worksheet.append_row(row_data)
        return True, row_id
    except Exception as e:
        return False, str(e)

# ─── Main UI ──────────────────────────────────────────────────────────────────

st.title("🍕 Just Bake - New Order")
st.divider()

# ─── Customer ─────────────────────────────────────────────────────────────────

existing_customers = get_existing_customers()
customer_options = ["🆕 New Customer"] + sorted(existing_customers.keys())

col1, col2 = st.columns(2)
with col1:
    selected_customer = st.selectbox(
        "Customer *",
        options=customer_options,
        key=f"v{v}_customer"
    )
    if selected_customer == "🆕 New Customer":
        customer_name = st.text_input(
            "Name *",
            placeholder="Enter customer name",
            key=f"v{v}_customer_name"
        )
    else:
        customer_name = selected_customer

with col2:
    default_phone = ""
    if selected_customer != "🆕 New Customer" and selected_customer in existing_customers:
        default_phone = existing_customers[selected_customer]["phone"]
    phone = st.text_input(
        "Phone",
        value=default_phone,
        placeholder="050-1234567",
        key=f"v{v}_phone"
    )

col3, col4 = st.columns(2)
with col3:
    order_date = st.date_input("Date *", value=datetime.now(), key=f"v{v}_date")
with col4:
    payment_method = st.selectbox(
        "Payment *",
        options=list(PAYMENT_METHODS.keys()),
        format_func=lambda x: PAYMENT_METHODS[x],
        key=f"v{v}_payment"
    )

with st.expander("🏢 Business Customer (optional)"):
    business_id = st.text_input(
        "Business ID (ח.פ.)",
        placeholder="123456789",
        key=f"v{v}_business_id"
    )

st.divider()

# ─── Products ─────────────────────────────────────────────────────────────────

st.subheader("Products")

# Pre-fill prices from customer's last order
last_prices = {}
if selected_customer != "🆕 New Customer" and selected_customer in existing_customers:
    last_prices = existing_customers[selected_customer].get("prices", {})

product_data = {}

for i, product in enumerate(PRODUCTS):
    prefix = product["column_prefix"]

    col_name, col_qty, col_price = st.columns([3, 1, 1.5])

    with col_name:
        st.markdown(f"**{product['hebrew']}**  \n_{product['name']}_")

    with col_qty:
        qty = st.number_input(
            "Qty",
            min_value=0,
            value=None,
            step=1,
            key=f"v{v}_{prefix}_qty",
            label_visibility="collapsed",
            placeholder="0"
        )

    with col_price:
        default_price = last_prices.get(f"{prefix}_price", None)
        price = st.number_input(
            "Price",
            min_value=0.0,
            value=default_price,
            step=0.5,
            format="%.2f",
            key=f"v{v}_{prefix}_price",
            label_visibility="collapsed",
            placeholder="0.00"
        )

    product_data[f"{prefix}_qty"] = qty or 0
    product_data[f"{prefix}_price"] = price or 0.0

st.divider()

total = calculate_total(product_data)
st.markdown(f"### Total: ₪{total:.2f}")

st.divider()

# ─── Submit / Clear ───────────────────────────────────────────────────────────

col_submit, col_clear = st.columns(2)

with col_submit:
    if st.button("📝 Submit Order", type="primary", use_container_width=True):
        errors = []
        if not customer_name or not customer_name.strip():
            errors.append("Customer name is required")
        if not any(
            (product_data.get(f"{p['column_prefix']}_qty") or 0) > 0 and
            (product_data.get(f"{p['column_prefix']}_price") or 0) > 0
            for p in PRODUCTS
        ):
            errors.append("At least one product must have quantity and price")

        if errors:
            for e in errors:
                st.error(e)
        else:
            with st.spinner("Submitting..."):
                success, result = submit_order(
                    customer_name, order_date, payment_method,
                    product_data, phone, business_id
                )
            if success:
                st.success("✅ Order submitted!")
                st.balloons()
                import time; time.sleep(1.5)
                st.session_state.form_version += 1
                st.rerun()
            else:
                st.error(f"❌ Failed: {result}")

with col_clear:
    if st.button("🗑️ Clear Form", use_container_width=True):
        st.session_state.form_version += 1
        st.rerun()

st.divider()
st.caption("Just Bake • Pashut La'afot 🍕")

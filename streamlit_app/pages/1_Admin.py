"""
Just Bake - Admin Dashboard
Secure admin interface for managing orders, payments, and invoices.
"""

import streamlit as st
from datetime import datetime, timedelta, date
import os
import sys
from dotenv import load_dotenv

# Allow importing from streamlit_app/ and project root (for src/)
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))           # streamlit_app/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))  # project root
from sheets_client import get_sheets_client, get_spreadsheet
from products import PRODUCTS, PAYMENT_METHODS
from src.google_sheets import GoogleSheetsClient
from src.keep_client import KeepClient
from src.invoice_processor import InvoiceProcessor

load_dotenv()

# ─── Security Configuration ───────────────────────────────────────────────────

MAX_FAILED_ATTEMPTS = 5       # Lock out after this many wrong passwords
LOCKOUT_DURATION_MINUTES = 15 # How long the lockout lasts
SESSION_TIMEOUT_MINUTES = 30  # Auto-logout after inactivity

# ─── Security Layer ───────────────────────────────────────────────────────────

def init_security_state():
    """Initialize security-related session state."""
    if "admin_authenticated" not in st.session_state:
        st.session_state.admin_authenticated = False
    if "failed_attempts" not in st.session_state:
        st.session_state.failed_attempts = 0
    if "lockout_until" not in st.session_state:
        st.session_state.lockout_until = None
    if "last_activity" not in st.session_state:
        st.session_state.last_activity = datetime.now()

def is_locked_out() -> bool:
    """Check if the user is currently locked out."""
    if st.session_state.lockout_until is None:
        return False
    if datetime.now() < st.session_state.lockout_until:
        return True
    # Lockout expired — reset
    st.session_state.lockout_until = None
    st.session_state.failed_attempts = 0
    return False

def is_session_expired() -> bool:
    """Check if the admin session has timed out due to inactivity."""
    if not st.session_state.admin_authenticated:
        return False
    elapsed = datetime.now() - st.session_state.last_activity
    return elapsed > timedelta(minutes=SESSION_TIMEOUT_MINUTES)

def record_activity():
    """Update last activity timestamp to keep session alive."""
    st.session_state.last_activity = datetime.now()

def check_admin_password() -> bool:
    """
    Secure admin login with rate limiting and lockout.
    Returns True if authenticated.
    """
    init_security_state()

    # Session timeout check
    if is_session_expired():
        st.session_state.admin_authenticated = False
        st.warning("⏱️ Session expired. Please log in again.")

    if st.session_state.admin_authenticated:
        record_activity()
        return True

    st.title("🔐 Just Bake - Admin")

    # Lockout check
    if is_locked_out():
        remaining = (st.session_state.lockout_until - datetime.now()).seconds // 60 + 1
        st.error(f"🔒 Too many failed attempts. Try again in {remaining} minute(s).")
        return False

    # Show remaining attempts warning
    if st.session_state.failed_attempts > 0:
        remaining_attempts = MAX_FAILED_ATTEMPTS - st.session_state.failed_attempts
        st.warning(f"⚠️ {remaining_attempts} attempt(s) remaining before lockout.")

    with st.form("admin_login"):
        password = st.text_input("Admin Password", type="password")
        submitted = st.form_submit_button("Login", use_container_width=True)

    if submitted:
        admin_password = st.secrets.get("admin_password", "")
        if password == admin_password and admin_password != "":
            st.session_state.admin_authenticated = True
            st.session_state.failed_attempts = 0
            st.session_state.last_activity = datetime.now()
            st.rerun()
        else:
            st.session_state.failed_attempts += 1
            if st.session_state.failed_attempts >= MAX_FAILED_ATTEMPTS:
                st.session_state.lockout_until = datetime.now() + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
                st.error(f"🔒 Too many failed attempts. Locked out for {LOCKOUT_DURATION_MINUTES} minutes.")
            else:
                st.error("❌ Incorrect password.")

    return False

# ─── Google Sheets Client ─────────────────────────────────────────────────────
# Imported from sheets_client.py (shared with app.py so the connection is cached once)

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _safe_float(row, idx):
    try:
        return float(row[idx]) if len(row) > idx and row[idx] else 0.0
    except (ValueError, TypeError):
        return 0.0

def _safe_int(row, idx):
    try:
        return int(float(row[idx])) if len(row) > idx and row[idx] else 0
    except (ValueError, TypeError):
        return 0

# ─── Data Loading ─────────────────────────────────────────────────────────────

def load_all_orders():
    """Load all orders from Google Sheets."""
    spreadsheet = get_spreadsheet()
    if not spreadsheet:
        return []

    try:
        worksheet = spreadsheet.get_worksheet(0)
        rows = worksheet.get_all_values()
        if len(rows) <= 1:
            return []

        orders = []
        for i, row in enumerate(rows[1:], start=2):  # start=2 = actual sheet row number
            if len(row) < 6:
                continue

            customer_name = row[1].strip() if len(row) > 1 else ""
            if not customer_name:
                continue

            # Parse product quantities and prices
            products = {}
            for pi, product in enumerate(PRODUCTS):
                prefix = product["column_prefix"]
                if pi == 9:  # Cheese: Price(Y=24) then Qty(Z=25) — swapped
                    products[f"{prefix}_price"] = _safe_float(row, 24)
                    products[f"{prefix}_qty"] = _safe_int(row, 25)
                else:
                    qty_idx = 6 + 2 * pi
                    price_idx = 6 + 2 * pi + 1
                    products[f"{prefix}_qty"] = _safe_int(row, qty_idx)
                    products[f"{prefix}_price"] = _safe_float(row, price_idx)

            orders.append({
                "row": i,
                "date": row[0] if len(row) > 0 else "",
                "customer": customer_name,
                "amount": row[2] if len(row) > 2 else "0",
                "payment_method": row[3] if len(row) > 3 else "",
                "create_invoice": row[4] if len(row) > 4 else "",
                "invoice_url": row[5] if len(row) > 5 else "",
                "row_id": row[26] if len(row) > 26 else "",  # AA
                "status": row[27] if len(row) > 27 else "",  # AB
                "phone": row[28] if len(row) > 28 else "",   # AC
                "products": products,
            })
        return orders
    except Exception as e:
        st.error(f"Failed to load orders: {e}")
        return []

# ─── Update Helpers ───────────────────────────────────────────────────────────

def update_payment_method(row_number: int, new_method: str) -> bool:
    """Update payment method for an order (Column D = index 3)."""
    spreadsheet = get_spreadsheet()
    if not spreadsheet:
        return False
    try:
        worksheet = spreadsheet.get_worksheet(0)
        worksheet.update_cell(row_number, 4, new_method)  # Column D
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Failed to update payment: {e}")
        return False

def update_order(row_number: int, customer: str, phone: str, order_date, payment_method: str, products: dict) -> bool:
    """Overwrite an entire order row with new values."""
    spreadsheet = get_spreadsheet()
    if not spreadsheet:
        return False
    try:
        worksheet = spreadsheet.get_worksheet(0)

        total = sum(
            (products.get(f"{p['column_prefix']}_qty") or 0) *
            (products.get(f"{p['column_prefix']}_price") or 0.0)
            for p in PRODUCTS
        )

        # Rebuild the row (columns A–D, keep E and F as-is)
        row_data = [
            order_date.strftime("%d/%m/%Y"),
            customer,
            total,
            payment_method,
        ]

        # Products G–Z
        for pi, product in enumerate(PRODUCTS):
            prefix = product["column_prefix"]
            if pi == 9:  # Cheese: Price then Qty
                row_data.append(products.get(f"{prefix}_price") or 0.0)
                row_data.append(products.get(f"{prefix}_qty") or 0)
            else:
                row_data.append(products.get(f"{prefix}_qty") or 0)
                row_data.append(products.get(f"{prefix}_price") or 0.0)

        # Update A:D and G:Z (skip E=create_invoice, F=invoice_url)
        worksheet.update(f"A{row_number}:D{row_number}", [row_data[:4]])
        worksheet.update(f"G{row_number}:Z{row_number}", [row_data[4:]])
        # Update phone (AC = column 29)
        worksheet.update_cell(row_number, 29, phone)

        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Failed to update order: {e}")
        return False

def create_invoice_now(row_number: int) -> tuple:
    """Create invoice immediately via Keep.co.il API."""
    try:
        credentials_json = st.secrets.get("GOOGLE_CREDENTIALS_JSON")
        spreadsheet_id = st.secrets.get("spreadsheet_id")
        keep_client_id = st.secrets.get("keep_client_id")
        keep_client_secret = st.secrets.get("keep_client_secret")
        keep_api_base_url = st.secrets.get("keep_api_base_url", "https://app.keep.co.il")

        if not keep_client_id or not keep_client_secret:
            return False, "Keep.co.il credentials not set in Streamlit secrets (keep_client_id, keep_client_secret)"

        # Mark row as ready for processing
        sheets = GoogleSheetsClient(credentials_json, spreadsheet_id)
        sheets.worksheet.update_cell(row_number, 5, "yes")

        # Find and process just this order
        pending = sheets.get_pending_orders()
        order = next((o for o in pending if o.sheet_row_number == row_number), None)

        if not order:
            return False, "Could not read order data from sheet"

        keep = KeepClient(keep_client_id, keep_client_secret, keep_api_base_url)
        processor = InvoiceProcessor(sheets, keep)
        success = processor._process_single_order(order, stop_on_validation_error=False)

        st.cache_data.clear()
        if success:
            return True, "✅ Invoice created!"
        else:
            return False, "Invoice failed — check the Status column in Google Sheets"

    except Exception as e:
        return False, str(e)

# ─── Main Admin UI ────────────────────────────────────────────────────────────

if not check_admin_password():
    st.stop()

# Track which order is being edited
if "editing_row" not in st.session_state:
    st.session_state.editing_row = None

# Admin header with logout
col_title, col_logout = st.columns([5, 1])
with col_title:
    st.title("📋 Just Bake - Admin Dashboard")
with col_logout:
    if st.button("Logout", use_container_width=True):
        st.session_state.admin_authenticated = False
        st.rerun()

# Session info
time_left = SESSION_TIMEOUT_MINUTES - int((datetime.now() - st.session_state.last_activity).seconds / 60)
st.caption(f"Session active · Auto-logout in {time_left} min")

st.divider()

# Load orders
with st.spinner("Loading orders..."):
    all_orders = load_all_orders()

if not all_orders:
    st.info("No orders found in Google Sheets.")
    st.stop()

not_paid = [o for o in all_orders if o["payment_method"] == "לא שולם"]

include_cash = st.sidebar.checkbox("Include cash orders in No Invoice tab", value=False)

CASH_VALUES = ("מזומן", "cash", "Cash")
excluded = ("לא שולם",) if include_cash else ("לא שולם", *CASH_VALUES)
paid_no_invoice = [
    o for o in all_orders
    if o["payment_method"] not in excluded
    and not o["invoice_url"].strip()
    and o["create_invoice"].strip().lower() != "yes"
]

# ─── Tabs ─────────────────────────────────────────────────────────────────────

tab1, tab2 = st.tabs([
    f"⚠️ Not Paid ({len(not_paid)})",
    f"🧾 Paid - No Invoice ({len(paid_no_invoice)})",
])

def render_order_table(orders, allow_payment_update=False, allow_invoice_trigger=False):
    """Render a table of orders with optional action buttons."""
    if not orders:
        st.success("✅ Nothing here!")
        return

    for order in orders:
        with st.container(border=True):
            col1, col2, col3, col4 = st.columns([2, 1, 1, 2])

            with col1:
                st.markdown(f"**{order['customer']}**")
                st.caption(f"📅 {order['date']}  ·  📞 {order['phone'] or '—'}")

            with col2:
                st.metric("Amount", f"₪{order['amount']}")

            with col3:
                st.markdown(f"**Payment**")
                st.caption(order["payment_method"] or "—")

            with col4:
                if allow_payment_update:
                    new_method = st.selectbox(
                        "Mark as paid",
                        options=["—", "Bit", "Paybox", "מזומן"],
                        key=f"pay_{order['row']}",
                        label_visibility="collapsed"
                    )
                    if new_method != "—":
                        if st.button("✅ Update Payment", key=f"btn_pay_{order['row']}", use_container_width=True):
                            if update_payment_method(order["row"], new_method):
                                st.success(f"Updated to {new_method}")
                                st.rerun()

                    # Edit button
                    is_editing = st.session_state.editing_row == order["row"]
                    edit_label = "✏️ Cancel Edit" if is_editing else "✏️ Edit Order"
                    if st.button(edit_label, key=f"btn_edit_{order['row']}", use_container_width=True):
                        st.session_state.editing_row = None if is_editing else order["row"]
                        st.rerun()

                if allow_invoice_trigger:
                    if st.button("🧾 Create Invoice", key=f"btn_inv_{order['row']}", use_container_width=True):
                        with st.spinner("Creating invoice..."):
                            success, msg = create_invoice_now(order["row"])
                        if success:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)

                if order["invoice_url"]:
                    st.link_button("📄 View Invoice", order["invoice_url"], use_container_width=True)

            # ── Inline Edit Form ──────────────────────────────────────────
            if st.session_state.editing_row == order["row"]:
                st.divider()
                st.markdown("#### ✏️ Edit Order")

                ec1, ec2 = st.columns(2)
                with ec1:
                    edit_customer = st.text_input("Customer Name", value=order["customer"], key=f"edit_name_{order['row']}")
                    try:
                        d, m, y = order["date"].split("/")
                        parsed_date = date(int(y), int(m), int(d))
                    except Exception:
                        parsed_date = date.today()
                    edit_date = st.date_input("Date", value=parsed_date, key=f"edit_date_{order['row']}")

                with ec2:
                    edit_phone = st.text_input("Phone", value=order["phone"], key=f"edit_phone_{order['row']}")
                    method_keys = list(PAYMENT_METHODS.keys())
                    method_values = list(PAYMENT_METHODS.values())
                    current_idx = method_values.index(order["payment_method"]) if order["payment_method"] in method_values else 0
                    edit_payment = st.selectbox(
                        "Payment Method",
                        options=method_keys,
                        index=current_idx,
                        format_func=lambda x: PAYMENT_METHODS[x],
                        key=f"edit_payment_{order['row']}"
                    )

                st.markdown("**Products**")
                edit_products = {}
                for pi, product in enumerate(PRODUCTS):
                    prefix = product["column_prefix"]
                    current_qty = order["products"].get(f"{prefix}_qty", 0)
                    current_price = order["products"].get(f"{prefix}_price", 0.0)

                    pc1, pc2, pc3 = st.columns([3, 1, 1.5])
                    with pc1:
                        st.markdown(f"**{product['hebrew']}** _{product['name']}_")
                    with pc2:
                        edit_products[f"{prefix}_qty"] = st.number_input(
                            "Qty", min_value=0, value=current_qty, step=1,
                            key=f"edit_{prefix}_qty_{order['row']}", label_visibility="collapsed"
                        )
                    with pc3:
                        edit_products[f"{prefix}_price"] = st.number_input(
                            "Price", min_value=0.0, value=current_price, step=0.5, format="%.2f",
                            key=f"edit_{prefix}_price_{order['row']}", label_visibility="collapsed"
                        )

                new_total = sum(
                    (edit_products.get(f"{p['column_prefix']}_qty") or 0) *
                    (edit_products.get(f"{p['column_prefix']}_price") or 0.0)
                    for p in PRODUCTS
                )
                st.markdown(f"**New Total: ₪{new_total:.2f}**")

                if st.button("💾 Save Changes", key=f"save_{order['row']}", type="primary"):
                    if update_order(order["row"], edit_customer, edit_phone, edit_date, PAYMENT_METHODS[edit_payment], edit_products):
                        st.success("✅ Order updated!")
                        st.session_state.editing_row = None
                        st.rerun()
                st.divider()

with tab1:
    st.subheader("Orders Awaiting Payment")
    st.caption("These orders have been entered but payment has not been received yet.")
    render_order_table(not_paid, allow_payment_update=True)

with tab2:
    st.subheader("Paid Orders Without Invoice")
    st.caption("Payment received but no invoice has been created yet.")
    render_order_table(paid_no_invoice, allow_invoice_trigger=True)

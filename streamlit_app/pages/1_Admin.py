"""
Just Bake - Admin Dashboard
Secure admin interface for managing orders, payments, and invoices.
"""

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import json
import os
from dotenv import load_dotenv

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

@st.cache_resource
def get_sheets_client():
    """Initialize Google Sheets client (same logic as app.py)."""
    try:
        credentials_dict = None

        try:
            creds_json = st.secrets.get("GOOGLE_CREDENTIALS_JSON")
            if creds_json:
                credentials_dict = json.loads(creds_json)
        except Exception:
            pass

        if not credentials_dict:
            try:
                credentials_dict = dict(st.secrets["google_sheets_credentials"])
            except Exception:
                pass

        if not credentials_dict:
            credentials_json = os.getenv("GOOGLE_SHEETS_CREDENTIALS")
            if credentials_json:
                credentials_dict = json.loads(credentials_json)
            else:
                raise ValueError("No Google Sheets credentials found.")

        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        credentials = Credentials.from_service_account_info(credentials_dict, scopes=scopes)
        return gspread.authorize(credentials)
    except Exception as e:
        st.error(f"Failed to connect to Google Sheets: {e}")
        return None

def get_spreadsheet():
    client = get_sheets_client()
    if client is None:
        return None
    try:
        spreadsheet_id = st.secrets.get("spreadsheet_id") or os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
        return client.open_by_key(spreadsheet_id)
    except Exception as e:
        st.error(f"Failed to open spreadsheet: {e}")
        return None

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

            orders.append({
                "row": i,                                    # Sheet row number (for updates)
                "date": row[0] if len(row) > 0 else "",
                "customer": customer_name,
                "amount": row[2] if len(row) > 2 else "0",
                "payment_method": row[3] if len(row) > 3 else "",
                "create_invoice": row[4] if len(row) > 4 else "",
                "invoice_url": row[5] if len(row) > 5 else "",
                "row_id": row[26] if len(row) > 26 else "",  # AA
                "status": row[27] if len(row) > 27 else "",  # AB
                "phone": row[28] if len(row) > 28 else "",   # AC
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

def mark_for_invoice(row_number: int) -> bool:
    """Set 'create invoice' = 'yes' to trigger invoice automation (Column E = index 4)."""
    spreadsheet = get_spreadsheet()
    if not spreadsheet:
        return False
    try:
        worksheet = spreadsheet.get_worksheet(0)
        worksheet.update_cell(row_number, 5, "yes")  # Column E
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Failed to mark for invoice: {e}")
        return False

# ─── Main Admin UI ────────────────────────────────────────────────────────────

if not check_admin_password():
    st.stop()

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

# ─── Sidebar Filters ──────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Filters")

    all_methods = sorted(set(o["payment_method"] for o in all_orders if o["payment_method"]))

    st.caption("**Not Paid tab** — show orders placed via:")
    not_paid_filter = st.multiselect(
        "Not Paid: payment methods",
        options=all_methods,
        default=all_methods,
        label_visibility="collapsed",
        key="filter_not_paid"
    )

    st.divider()

    # Default: exclude cash from invoice list
    invoice_default = [m for m in all_methods if m != "מזומן"]
    st.caption("**No Invoice tab** — include payment methods:")
    invoice_filter = st.multiselect(
        "Invoice: payment methods",
        options=all_methods,
        default=invoice_default,
        label_visibility="collapsed",
        key="filter_invoice"
    )
    st.caption("💡 Cash excluded by default — change anytime")

# ─── Filter: Not Paid ─────────────────────────────────────────────────────────

not_paid = [
    o for o in all_orders
    if o["payment_method"] == "לא שולם"
]

# ─── Filter: Paid but No Invoice ──────────────────────────────────────────────

paid_no_invoice = [
    o for o in all_orders
    if o["payment_method"] != "לא שולם"
    and o["payment_method"] in invoice_filter
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

                if allow_invoice_trigger:
                    if st.button("🧾 Create Invoice", key=f"btn_inv_{order['row']}", use_container_width=True):
                        if mark_for_invoice(order["row"]):
                            st.success("Marked for invoice creation!")
                            st.rerun()

                if order["invoice_url"]:
                    st.link_button("📄 View Invoice", order["invoice_url"], use_container_width=True)

with tab1:
    st.subheader("Orders Awaiting Payment")
    st.caption("These orders have been entered but payment has not been received yet.")
    render_order_table(not_paid, allow_payment_update=True)

with tab2:
    st.subheader("Paid Orders Without Invoice")
    st.caption("Payment received but no invoice has been created yet.")
    render_order_table(paid_no_invoice, allow_invoice_trigger=True)

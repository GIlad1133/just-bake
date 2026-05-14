"""
Just Bake - Admin Dashboard
Secure admin interface for managing orders, payments, and invoices.
"""

import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime, date, timedelta


def _normalize_dmy(date_str: str) -> str:
    """Force any date string to DD/MM/YYYY.

    Google Sheets sometimes re-displays dates in ISO when the column has been
    auto-formatted as a date (happens to a brand-new column the first time we
    write a parseable date). Normalize on read so comparisons and grouping work.
    """
    if not date_str:
        return ""
    s = str(date_str).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%d/%m/%Y")
        except ValueError:
            continue
    return s
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

# ─── Google OAuth Authentication ──────────────────────────────────────────────

def require_auth():
    """Gate the admin page behind Google OAuth. Stops execution if not authorized."""
    if not st.user.is_logged_in:
        st.title("🔐 Just Bake - Admin")
        st.info("Log in with your Google account to access the admin dashboard.")
        st.login("google")
        st.stop()

    allowed = [e.strip() for e in st.secrets.get("allowed_emails", "").split(",") if e.strip()]
    if allowed and st.user.email not in allowed:
        st.error(f"❌ Access denied: {st.user.email} is not authorized.")
        if st.button("Log out"):
            st.logout()
        st.stop()

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
                if "qty_col" in product:
                    products[f"{prefix}_qty"] = _safe_int(row, product["qty_col"])
                    products[f"{prefix}_price"] = _safe_float(row, product["price_col"])
                elif pi == 9:  # Cheese: Price(Y=24) then Qty(Z=25) — swapped
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
                "picked_up": (row[32].strip().lower() == "yes") if len(row) > 32 and row[32] else False,  # AG
                "dough_type": (row[33].strip().lower() if len(row) > 33 and row[33] else ""),  # AH: "fresh" / "frozen" / ""
                "bake_date": _normalize_dmy(row[34]) if len(row) > 34 and row[34] else "",  # AI: DD/MM/YYYY or empty
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

        # Products G–Z (standard contiguous block — skip products with custom column positions)
        for pi, product in enumerate(PRODUCTS):
            if "qty_col" in product:
                continue
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
        # Update products stored in non-contiguous columns (e.g. Pizza Workshop at AE/AF)
        for product in PRODUCTS:
            if "qty_col" not in product:
                continue
            prefix = product["column_prefix"]
            worksheet.update_cell(row_number, product["qty_col"] + 1, products.get(f"{prefix}_qty") or 0)
            worksheet.update_cell(row_number, product["price_col"] + 1, products.get(f"{prefix}_price") or 0.0)

        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Failed to update order: {e}")
        return False

def update_collection_date(row_number: int, new_date) -> bool:
    """Update the collection date for an order (Column A)."""
    spreadsheet = get_spreadsheet()
    if not spreadsheet:
        return False
    try:
        worksheet = spreadsheet.get_worksheet(0)
        worksheet.update_cell(row_number, 1, new_date.strftime("%d/%m/%Y"))  # Column A
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Failed to update date: {e}")
        return False

def update_pickup_status(row_number: int, picked_up: bool) -> bool:
    """Mark/unmark an order as picked up (Column AG = column 33).

    Writes 'yes' / 'no' explicitly so backfill can distinguish manual
    unmarks from never-touched cells.
    """
    spreadsheet = get_spreadsheet()
    if not spreadsheet:
        return False
    try:
        worksheet = spreadsheet.get_worksheet(0)
        worksheet.update_cell(row_number, 33, "yes" if picked_up else "no")
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Failed to update pickup status: {e}")
        return False

def update_dough_type(row_number: int, dough_type: str) -> bool:
    """Tag a Neapolitan order as fresh/frozen (Column AH = column 34).

    Pass 'fresh', 'frozen', or '' to clear.
    """
    spreadsheet = get_spreadsheet()
    if not spreadsheet:
        return False
    try:
        worksheet = spreadsheet.get_worksheet(0)
        worksheet.update_cell(row_number, 34, dough_type)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Failed to update dough type: {e}")
        return False

def update_bake_date(row_number: int, bake_date_str: str) -> bool:
    """Set when the customer plans to bake (Column AI = column 35).

    For fresh Neapolitan, this drives fermentation timing. Empty string clears.
    Writes with value_input_option='RAW' so Sheets stores the literal text
    instead of parsing it as a date and re-displaying in a different locale.
    """
    spreadsheet = get_spreadsheet()
    if not spreadsheet:
        return False
    try:
        worksheet = spreadsheet.get_worksheet(0)
        worksheet.update(
            range_name=f"AI{row_number}",
            values=[[bake_date_str or ""]],
            value_input_option="RAW",
        )
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Failed to update bake date: {e}")
        return False

def backfill_picked_up() -> int:
    """Mark historical orders as picked up when AG is blank.

    Heuristic: has invoice URL OR (paid AND date already passed).
    Cash orders never get invoice URLs but are paid at pickup, so
    any cash-paid past order is treated as picked up. Idempotent —
    skips rows already marked yes/no. Returns count updated.
    """
    spreadsheet = get_spreadsheet()
    if not spreadsheet:
        return 0
    try:
        worksheet = spreadsheet.get_worksheet(0)
        rows = worksheet.get_all_values()
        if len(rows) <= 1:
            return 0

        today_start = datetime.combine(date.today(), datetime.min.time())
        updates = []
        for i, row in enumerate(rows[1:], start=2):
            ag_value = row[32].strip() if len(row) > 32 else ""
            if ag_value:
                continue  # already explicitly marked yes/no — leave alone

            has_invoice = bool(len(row) > 5 and row[5].strip())
            payment_method = row[3] if len(row) > 3 else ""
            order_date = _parse_date(row[0] if len(row) > 0 else "")
            paid_and_past = _is_paid(payment_method) and order_date < today_start

            if has_invoice or paid_and_past:
                updates.append({"range": f"AG{i}", "values": [["yes"]]})

        if updates:
            worksheet.batch_update(updates)
            st.cache_data.clear()
        return len(updates)
    except Exception as e:
        st.error(f"Backfill failed: {e}")
        return 0

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

def bulk_create_invoices(row_numbers: list) -> dict:
    """Create invoices for many orders in one pass.

    Shares one Sheets+Keep client instead of recreating per call.
    Batch-writes the 'yes' flags, reads pending orders once, then
    processes each. Returns {successes: int, failures: list[(row, msg)]}.
    """
    result = {"successes": 0, "failures": []}
    if not row_numbers:
        return result

    try:
        credentials_json = st.secrets.get("GOOGLE_CREDENTIALS_JSON")
        spreadsheet_id = st.secrets.get("spreadsheet_id")
        keep_client_id = st.secrets.get("keep_client_id")
        keep_client_secret = st.secrets.get("keep_client_secret")
        keep_api_base_url = st.secrets.get("keep_api_base_url", "https://app.keep.co.il")

        if not keep_client_id or not keep_client_secret:
            result["failures"].append((0, "Keep.co.il credentials not set in Streamlit secrets"))
            return result

        sheets = GoogleSheetsClient(credentials_json, spreadsheet_id)
        keep = KeepClient(keep_client_id, keep_client_secret, keep_api_base_url)
        processor = InvoiceProcessor(sheets, keep)

        # Mark all rows as ready in one batch write
        sheets.worksheet.batch_update([
            {"range": f"E{r}", "values": [["yes"]]}
            for r in row_numbers
        ])

        # Read pending orders once and index by row number
        pending = {o.sheet_row_number: o for o in sheets.get_pending_orders()}

        n = len(row_numbers)
        progress = st.progress(0.0)
        status = st.empty()

        for i, row_num in enumerate(row_numbers, 1):
            status.write(f"Creating invoice {i}/{n} (row {row_num})…")
            order = pending.get(row_num)
            if not order:
                result["failures"].append((row_num, "Could not read order data from sheet"))
            elif processor._process_single_order(order, stop_on_validation_error=False):
                result["successes"] += 1
            else:
                result["failures"].append((row_num, "Invoice failed — check Status column"))
            progress.progress(i / n)

        status.empty()
        progress.empty()
        st.cache_data.clear()
        return result

    except Exception as e:
        result["failures"].append((0, f"Bulk error: {e}"))
        return result

def delete_order(row_number: int) -> bool:
    """Delete an order row from Google Sheets."""
    spreadsheet = get_spreadsheet()
    if not spreadsheet:
        return False
    try:
        worksheet = spreadsheet.get_worksheet(0)
        worksheet.delete_rows(row_number)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Failed to delete order: {e}")
        return False

# ─── Main Admin UI ────────────────────────────────────────────────────────────

require_auth()

# Track which order is being edited / pending delete confirmation
if "editing_row" not in st.session_state:
    st.session_state.editing_row = None
if "confirm_delete_row" not in st.session_state:
    st.session_state.confirm_delete_row = None
if "selected_invoices" not in st.session_state:
    st.session_state.selected_invoices = set()

# Admin header with logout
col_title, col_logout = st.columns([5, 1])
with col_title:
    st.title("📋 Just Bake - Admin Dashboard")
with col_logout:
    if st.button("Logout", use_container_width=True):
        st.logout()

st.caption(f"👤 Logged in as {st.user.email}")

st.divider()

# Load orders
with st.spinner("Loading orders..."):
    all_orders = load_all_orders()

if not all_orders:
    st.info("No orders found in Google Sheets.")
    st.stop()

def _parse_date(date_str):
    if not date_str:
        return datetime.min
    s = str(date_str).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return datetime.min

UNPAID_PAYMENT_VALUES = {"לא שולם", "", "-"}
CASH_VALUES = ("מזומן", "cash", "Cash")

def _is_paid(payment_method: str) -> bool:
    """Cash, Bit, Paybox → paid. 'לא שולם', empty, '-' → unpaid."""
    return (payment_method or "").strip() not in UNPAID_PAYMENT_VALUES

def _is_cash(payment_method: str) -> bool:
    return (payment_method or "").strip() in CASH_VALUES

def _neapolitan_count(order) -> int:
    """Total Neapolitan dough balls in an order: kit*5 + standalone."""
    p = order["products"]
    return (p.get("neapolitan_kit_qty", 0) or 0) * 5 + (p.get("neapolitan_dough_qty", 0) or 0)

def _has_neapolitan(order) -> bool:
    return _neapolitan_count(order) > 0

def _effective_dough_date(order) -> str:
    """The date by which the dough must be READY.

    Fresh orders: bake date (drives fermentation start time).
    Frozen / unspecified: pickup date (when to thaw or hand over).
    """
    if order.get("dough_type") == "fresh" and order.get("bake_date"):
        return order["bake_date"]
    return order["date"]

not_paid = sorted(
    [o for o in all_orders if not _is_paid(o["payment_method"])],
    key=lambda o: _parse_date(o["date"])
)

include_cash = st.sidebar.checkbox("Include cash orders in No Invoice tab", value=False)

paid_no_invoice = [
    o for o in all_orders
    if _is_paid(o["payment_method"])
    and (include_cash or not _is_cash(o["payment_method"]))
    and not o["invoice_url"].strip()
    and o["create_invoice"].strip().lower() != "yes"
]

paid_no_invoice.sort(key=lambda o: _parse_date(o["date"]))

show_picked_up = st.sidebar.checkbox("Show recently picked-up orders", value=False)

with st.sidebar.expander("⚙️ Tools"):
    st.caption(
        "**Backfill picked-up**\n\n"
        "Marks an order as picked up if it has an invoice URL, or if it was "
        "already paid (cash/Bit/Paybox) and its collection date is in the past. "
        "Only touches rows you haven't explicitly marked yet. "
        "Safe to run multiple times."
    )
    if st.button("🪄 Run backfill", use_container_width=True):
        count = backfill_picked_up()
        if count > 0:
            st.success(f"✅ Marked {count} orders as picked up")
            st.rerun()
        else:
            st.info("Nothing to backfill — all eligible orders already handled.")

today_start = datetime.combine(date.today(), datetime.min.time())
tomorrow_start = datetime.combine(date.today() + timedelta(days=1), datetime.min.time())

pickup_queue = sorted(
    [o for o in all_orders if not o["picked_up"]],
    key=lambda o: _parse_date(o["date"])
)
overdue_orders = [o for o in pickup_queue if _parse_date(o["date"]) < today_start]
today_pickups = [o for o in pickup_queue if today_start <= _parse_date(o["date"]) < tomorrow_start]
upcoming_pickups = [o for o in pickup_queue if _parse_date(o["date"]) >= tomorrow_start]

recently_picked = sorted(
    [o for o in all_orders if o["picked_up"]],
    key=lambda o: _parse_date(o["date"]),
    reverse=True
)[:20] if show_picked_up else []

# ─── Tabs ─────────────────────────────────────────────────────────────────────

# After creating an invoice we rerun — re-click tab2 so the user stays there
if st.session_state.pop("return_to_invoice_tab", False):
    components.html("""
    <script>
    (function() {
        function clickTab() {
            const tabs = window.parent.document.querySelectorAll('[data-baseweb="tab"]');
            if (tabs.length > 1) { tabs[1].click(); return; }
            setTimeout(clickTab, 50);
        }
        setTimeout(clickTab, 50);
    })();
    </script>
    """, height=0)

# After pickup actions we rerun — re-click tab3 (index 2) so the user stays in the queue
if st.session_state.pop("return_to_pickup_tab", False):
    components.html("""
    <script>
    (function() {
        function clickTab() {
            const tabs = window.parent.document.querySelectorAll('[data-baseweb="tab"]');
            if (tabs.length > 2) { tabs[2].click(); return; }
            setTimeout(clickTab, 50);
        }
        setTimeout(clickTab, 50);
    })();
    </script>
    """, height=0)

def _pickup_rerun():
    """Set tab-restore flag, then rerun. Use inside any pickup-queue action."""
    st.session_state.return_to_pickup_tab = True
    st.rerun()

def _pickup_on_change():
    """Widget on_change callback — sets the tab-restore flag so the implicit
    rerun from a value change doesn't bounce the user back to Not Paid."""
    st.session_state.return_to_pickup_tab = True

pickup_tab_label = f"📦 Pickup Queue ({len(pickup_queue)})"
if overdue_orders:
    pickup_tab_label = f"📦 Pickup Queue ({len(pickup_queue)} · 🔴 {len(overdue_orders)} overdue)"

tab1, tab2, tab3 = st.tabs([
    f"⚠️ Not Paid ({len(not_paid)})",
    f"🧾 Paid - No Invoice ({len(paid_no_invoice)})",
    pickup_tab_label,
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
                    is_selected = order["row"] in st.session_state.selected_invoices
                    new_selected = st.checkbox(
                        "🧾 Select for invoice",
                        value=is_selected,
                        key=f"sel_inv_{order['row']}",
                    )
                    if new_selected and not is_selected:
                        st.session_state.selected_invoices.add(order["row"])
                    elif not new_selected and is_selected:
                        st.session_state.selected_invoices.discard(order["row"])

                if order["invoice_url"]:
                    st.link_button("📄 View Invoice", order["invoice_url"], use_container_width=True)

                # Delete button with confirmation
                if st.session_state.confirm_delete_row == order["row"]:
                    st.warning("Are you sure?")
                    dc1, dc2 = st.columns(2)
                    with dc1:
                        if st.button("🗑️ Yes, delete", key=f"confirm_del_{order['row']}", use_container_width=True, type="primary"):
                            if delete_order(order["row"]):
                                st.session_state.confirm_delete_row = None
                                st.rerun()
                    with dc2:
                        if st.button("Cancel", key=f"cancel_del_{order['row']}", use_container_width=True):
                            st.session_state.confirm_delete_row = None
                            st.rerun()
                else:
                    if st.button("🗑️ Delete", key=f"btn_del_{order['row']}", use_container_width=True):
                        st.session_state.confirm_delete_row = order["row"]
                        st.rerun()

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

                # Dough type (only relevant if order has Neapolitan in the new edit)
                has_nean_edit = (
                    (edit_products.get("neapolitan_kit_qty") or 0) > 0
                    or (edit_products.get("neapolitan_dough_qty") or 0) > 0
                )
                edit_dough_type = order["dough_type"]
                edit_bake_date_str = order.get("bake_date") or ""
                if has_nean_edit:
                    dough_options = ["", "fresh", "frozen"]
                    try:
                        dt_idx = dough_options.index(order["dough_type"])
                    except ValueError:
                        dt_idx = 0
                    edit_dough_type = st.radio(
                        "🍞 Neapolitan dough type",
                        options=dough_options,
                        index=dt_idx,
                        format_func=lambda x: {"": "❓ Not specified", "fresh": "🌿 Fresh", "frozen": "❄️ Frozen"}.get(x, x),
                        horizontal=True,
                        key=f"edit_dough_{order['row']}",
                    )

                    try:
                        d, m, y = (order.get("bake_date") or order["date"]).split("/")
                        current_bake_date = date(int(y), int(m), int(d))
                    except Exception:
                        current_bake_date = edit_date if isinstance(edit_date, date) else date.today()
                    edit_bake_date = st.date_input(
                        "🍞 Bake date (when customer plans to bake)",
                        value=current_bake_date,
                        key=f"edit_bake_{order['row']}",
                    )
                    edit_bake_date_str = edit_bake_date.strftime("%d/%m/%Y")

                st.markdown(f"**New Total: ₪{new_total:.2f}**")

                if st.button("💾 Save Changes", key=f"save_{order['row']}", type="primary"):
                    if update_order(order["row"], edit_customer, edit_phone, edit_date, PAYMENT_METHODS[edit_payment], edit_products):
                        if has_nean_edit and edit_dough_type != order["dough_type"]:
                            update_dough_type(order["row"], edit_dough_type)
                        if has_nean_edit and edit_bake_date_str != (order.get("bake_date") or ""):
                            update_bake_date(order["row"], edit_bake_date_str)
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
    st.caption("Payment received but no invoice has been created yet. Tick the orders you want to invoice, then click the button at the top.")

    # Show results from the last bulk run (if any)
    if "bulk_invoice_results" in st.session_state:
        results = st.session_state.pop("bulk_invoice_results")
        if results["successes"]:
            st.success(f"✅ Created {results['successes']} invoice{'s' if results['successes'] != 1 else ''}")
        if results["failures"]:
            st.error(f"❌ {len(results['failures'])} failed:")
            for row_num, msg in results["failures"]:
                label = f"Row {row_num}" if row_num else "—"
                st.write(f"- {label}: {msg}")

    # Drop selections that are no longer in this tab's filter (e.g. orders already invoiced)
    visible_rows = {o["row"] for o in paid_no_invoice}
    st.session_state.selected_invoices &= visible_rows
    n_selected = len(st.session_state.selected_invoices)

    if paid_no_invoice:
        bulk_c1, bulk_c2, bulk_c3 = st.columns([2, 1, 1])
        with bulk_c1:
            btn_label = (
                f"🧾 Create {n_selected} invoice{'s' if n_selected != 1 else ''}"
                if n_selected else "🧾 Create invoices (select orders first)"
            )
            if st.button(btn_label, type="primary", disabled=(n_selected == 0), use_container_width=True):
                with st.spinner(f"Creating {n_selected} invoice{'s' if n_selected != 1 else ''}…"):
                    selected_rows = sorted(st.session_state.selected_invoices)
                    results = bulk_create_invoices(selected_rows)
                st.session_state.bulk_invoice_results = results
                st.session_state.selected_invoices -= set(selected_rows)
                st.session_state.return_to_invoice_tab = True
                st.rerun()
        with bulk_c2:
            if st.button(f"☑️ Select all ({len(paid_no_invoice)})", use_container_width=True):
                st.session_state.selected_invoices |= visible_rows
                st.session_state.return_to_invoice_tab = True
                st.rerun()
        with bulk_c3:
            if st.button("Clear selection", use_container_width=True, disabled=(n_selected == 0)):
                st.session_state.selected_invoices -= visible_rows
                st.session_state.return_to_invoice_tab = True
                st.rerun()
        st.divider()

    render_order_table(paid_no_invoice, allow_invoice_trigger=True)

with tab3:
    st.subheader("📦 Pickup Queue")
    st.caption("All orders not yet picked up — paid or not. Mark each one as picked up when the customer collects it.")

    if not pickup_queue and not recently_picked:
        st.success("✅ All caught up — nothing pending pickup!")
    else:
        # ── Order card renderer (shared across all sections) ──────────────
        def _render_order_card(order, banner_color=None, banner_text=None):
            paid = _is_paid(order["payment_method"])
            payment_icon = "✅" if paid else "⚠️"

            with st.container(border=True):
                if banner_color == "red" and banner_text:
                    st.error(banner_text)
                elif banner_color == "green" and banner_text:
                    st.success(banner_text)

                col1, col2, col3, col4 = st.columns([2, 1, 1, 2])

                with col1:
                    st.markdown(f"**{order['customer']}**")
                    st.caption(f"📅 {order['date']}  ·  📞 {order['phone'] or '—'}")

                with col2:
                    st.metric("Amount", f"₪{order['amount']}")

                with col3:
                    st.markdown(f"{payment_icon} **Payment**")
                    st.caption(order["payment_method"] or "—")

                with col4:
                    # Primary action: pickup toggle
                    if order["picked_up"]:
                        if st.button("↩️ Unmark Picked Up", key=f"unpick_{order['row']}", use_container_width=True):
                            if update_pickup_status(order["row"], False):
                                _pickup_rerun()
                    else:
                        if st.button("✅ Mark as Picked Up", key=f"pick_{order['row']}", use_container_width=True, type="primary"):
                            if update_pickup_status(order["row"], True):
                                _pickup_rerun()

                    # Date editor
                    try:
                        d, m, y = order["date"].split("/")
                        current_coll_date = date(int(y), int(m), int(d))
                    except Exception:
                        current_coll_date = date.today()

                    new_coll_date = st.date_input(
                        "Collection date",
                        value=current_coll_date,
                        key=f"coll_date_pq_{order['row']}",
                        label_visibility="collapsed",
                        on_change=_pickup_on_change,
                    )
                    if new_coll_date != current_coll_date:
                        if st.button("📅 Update Date", key=f"btn_coll_pq_{order['row']}", use_container_width=True):
                            if update_collection_date(order["row"], new_coll_date):
                                _pickup_rerun()

                    # Edit toggle
                    is_editing = st.session_state.editing_row == order["row"]
                    edit_label = "✏️ Cancel Edit" if is_editing else "✏️ Edit Order"
                    if st.button(edit_label, key=f"btn_edit_pq_{order['row']}", use_container_width=True):
                        st.session_state.editing_row = None if is_editing else order["row"]
                        _pickup_rerun()

                    # Delete with confirmation
                    if st.session_state.confirm_delete_row == order["row"]:
                        st.warning("Are you sure?")
                        dc1, dc2 = st.columns(2)
                        with dc1:
                            if st.button("🗑️ Yes, delete", key=f"confirm_del_pq_{order['row']}", use_container_width=True, type="primary"):
                                if delete_order(order["row"]):
                                    st.session_state.confirm_delete_row = None
                                    _pickup_rerun()
                        with dc2:
                            if st.button("Cancel", key=f"cancel_del_pq_{order['row']}", use_container_width=True):
                                st.session_state.confirm_delete_row = None
                                _pickup_rerun()
                    else:
                        if st.button("🗑️ Delete", key=f"btn_del_pq_{order['row']}", use_container_width=True):
                            st.session_state.confirm_delete_row = order["row"]
                            _pickup_rerun()

                # Dough type footer (Neapolitan orders only)
                if _has_neapolitan(order):
                    n_count = _neapolitan_count(order)
                    ball_label = f"{n_count} ball{'s' if n_count != 1 else ''}"
                    bake_suffix = (
                        f" · bake {order['bake_date']}"
                        if order.get("bake_date") and order["bake_date"] != order["date"]
                        else ""
                    )
                    if order["dough_type"] == "fresh":
                        st.markdown(f"🌿 **Fresh** Neapolitan dough · {ball_label}{bake_suffix}")
                    elif order["dough_type"] == "frozen":
                        st.markdown(f"❄️ **Frozen** Neapolitan dough · {ball_label}{bake_suffix}")
                    else:
                        dt_c1, dt_c2, dt_c3 = st.columns([2, 1, 1])
                        with dt_c1:
                            st.caption(f"❓ Neapolitan dough type not set · {ball_label}")
                        with dt_c2:
                            if st.button("🌿 Fresh", key=f"tag_fresh_pq_{order['row']}", use_container_width=True):
                                if update_dough_type(order["row"], "fresh"):
                                    _pickup_rerun()
                        with dt_c3:
                            if st.button("❄️ Frozen", key=f"tag_frozen_pq_{order['row']}", use_container_width=True):
                                if update_dough_type(order["row"], "frozen"):
                                    _pickup_rerun()

                # Inline edit form
                if st.session_state.editing_row == order["row"]:
                    st.divider()
                    st.markdown("#### ✏️ Edit Order")
                    ec1, ec2 = st.columns(2)
                    with ec1:
                        edit_customer = st.text_input("Customer Name", value=order["customer"], key=f"edit_name_pq_{order['row']}", on_change=_pickup_on_change)
                        try:
                            d, m, y = order["date"].split("/")
                            parsed_date = date(int(y), int(m), int(d))
                        except Exception:
                            parsed_date = date.today()
                        edit_date = st.date_input("Date", value=parsed_date, key=f"edit_date_pq_{order['row']}", on_change=_pickup_on_change)
                    with ec2:
                        edit_phone = st.text_input("Phone", value=order["phone"], key=f"edit_phone_pq_{order['row']}", on_change=_pickup_on_change)
                        method_keys = list(PAYMENT_METHODS.keys())
                        method_values = list(PAYMENT_METHODS.values())
                        current_idx = method_values.index(order["payment_method"]) if order["payment_method"] in method_values else 0
                        edit_payment = st.selectbox(
                            "Payment Method",
                            options=method_keys,
                            index=current_idx,
                            format_func=lambda x: PAYMENT_METHODS[x],
                            key=f"edit_payment_pq_{order['row']}",
                            on_change=_pickup_on_change,
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
                                key=f"edit_pq_{prefix}_qty_{order['row']}", label_visibility="collapsed",
                                on_change=_pickup_on_change,
                            )
                        with pc3:
                            edit_products[f"{prefix}_price"] = st.number_input(
                                "Price", min_value=0.0, value=current_price, step=0.5, format="%.2f",
                                key=f"edit_pq_{prefix}_price_{order['row']}", label_visibility="collapsed",
                                on_change=_pickup_on_change,
                            )

                    new_total = sum(
                        (edit_products.get(f"{p['column_prefix']}_qty") or 0) *
                        (edit_products.get(f"{p['column_prefix']}_price") or 0.0)
                        for p in PRODUCTS
                    )
                    # Dough type (only relevant if order has Neapolitan in the new edit)
                    has_nean_edit = (
                        (edit_products.get("neapolitan_kit_qty") or 0) > 0
                        or (edit_products.get("neapolitan_dough_qty") or 0) > 0
                    )
                    edit_dough_type = order["dough_type"]
                    edit_bake_date_str = order.get("bake_date") or ""
                    if has_nean_edit:
                        dough_options = ["", "fresh", "frozen"]
                        try:
                            dt_idx = dough_options.index(order["dough_type"])
                        except ValueError:
                            dt_idx = 0
                        edit_dough_type = st.radio(
                            "🍞 Neapolitan dough type",
                            options=dough_options,
                            index=dt_idx,
                            format_func=lambda x: {"": "❓ Not specified", "fresh": "🌿 Fresh", "frozen": "❄️ Frozen"}.get(x, x),
                            horizontal=True,
                            key=f"edit_dough_pq_{order['row']}",
                            on_change=_pickup_on_change,
                        )

                        # Bake date — defaults to pickup date if not set
                        try:
                            d, m, y = (order.get("bake_date") or order["date"]).split("/")
                            current_bake_date = date(int(y), int(m), int(d))
                        except Exception:
                            current_bake_date = edit_date if isinstance(edit_date, date) else date.today()
                        edit_bake_date = st.date_input(
                            "🍞 Bake date (when customer plans to bake)",
                            value=current_bake_date,
                            key=f"edit_bake_pq_{order['row']}",
                            on_change=_pickup_on_change,
                        )
                        edit_bake_date_str = edit_bake_date.strftime("%d/%m/%Y")

                    st.markdown(f"**New Total: ₪{new_total:.2f}**")
                    if st.button("💾 Save Changes", key=f"save_pq_{order['row']}", type="primary"):
                        if update_order(order["row"], edit_customer, edit_phone, edit_date, PAYMENT_METHODS[edit_payment], edit_products):
                            if has_nean_edit and edit_dough_type != order["dough_type"]:
                                update_dough_type(order["row"], edit_dough_type)
                            if has_nean_edit and edit_bake_date_str != (order.get("bake_date") or ""):
                                update_bake_date(order["row"], edit_bake_date_str)
                            st.success("✅ Order updated!")
                            st.session_state.editing_row = None
                            _pickup_rerun()
                    st.divider()

        # ── Neapolitan dough prep (fresh by BAKE date, frozen by PICKUP date) ──
        neapolitan_orders = [o for o in pickup_queue if _has_neapolitan(o)]
        if neapolitan_orders:
            st.markdown("#### 🍞 Neapolitan Dough Prep")
            st.caption("Fresh grouped by bake date · Frozen / unspecified grouped by pickup date. Tells you what needs to be **ready** by each date.")
            # Index orders by their effective prep date
            by_date = {}
            for o in neapolitan_orders:
                key = _effective_dough_date(o)
                by_date.setdefault(key, []).append(o)
            def _name_list(orders, predicate):
                return ", ".join(
                    f"{o['customer']} ({_neapolitan_count(o)})"
                    for o in orders if predicate(o)
                )

            # Sort dates chronologically
            for day_str in sorted(by_date.keys(), key=_parse_date):
                day_orders = by_date[day_str]
                fresh = sum(_neapolitan_count(o) for o in day_orders if o["dough_type"] == "fresh")
                frozen = sum(_neapolitan_count(o) for o in day_orders if o["dough_type"] == "frozen")
                unspecified = sum(_neapolitan_count(o) for o in day_orders if not o["dough_type"])
                with st.container(border=True):
                    st.markdown(
                        f"**📅 {day_str}** — {len(day_orders)} order{'s' if len(day_orders) != 1 else ''}"
                    )
                    m1, m2, m3 = st.columns(3)
                    with m1:
                        st.metric("🌿 Fresh", fresh)
                    with m2:
                        st.metric("❄️ Frozen", frozen)
                    with m3:
                        if unspecified:
                            st.metric("❓ Unspecified", unspecified)
                        else:
                            st.caption("✅ All tagged")
                    if fresh:
                        st.caption(f"🌿 {_name_list(day_orders, lambda o: o['dough_type'] == 'fresh')}")
                    if frozen:
                        st.caption(f"❄️ {_name_list(day_orders, lambda o: o['dough_type'] == 'frozen')}")
                    if unspecified:
                        st.caption(f"❓ {_name_list(day_orders, lambda o: not o['dough_type'])}")
            st.divider()

        # ── Overdue section (most urgent — safety net for stale dates) ────
        if overdue_orders:
            st.markdown(f"### 🔴 Overdue ({len(overdue_orders)})")
            st.caption("Collection date already passed. Mark as picked up if collected, or update the date if postponed.")
            for order in overdue_orders:
                _render_order_card(order, banner_color="red", banner_text=f"🔴 OVERDUE — was scheduled for {order['date']}")
            st.divider()

        # ── Today section ─────────────────────────────────────────────────
        if today_pickups:
            st.markdown(f"### 📅 Today ({len(today_pickups)})")
            for order in today_pickups:
                _render_order_card(order)
            st.divider()

        # ── Upcoming section ──────────────────────────────────────────────
        if upcoming_pickups:
            st.markdown(f"### 🟢 Upcoming ({len(upcoming_pickups)})")
            for order in upcoming_pickups:
                _render_order_card(order)

        # ── Recently picked up (sidebar toggle — for undoing mistakes) ────
        if show_picked_up and recently_picked:
            st.divider()
            st.markdown(f"### ✅ Recently Picked Up ({len(recently_picked)})")
            st.caption("Click 'Unmark' if any were marked by mistake.")
            for order in recently_picked:
                _render_order_card(order, banner_color="green", banner_text=f"✅ Picked up — was on {order['date']}")

"""
Just Bake - Order Entry UI
Streamlit web app for entering new pizza orders.
"""

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import uuid
import json
import os
from dotenv import load_dotenv
from products import PRODUCTS, PAYMENT_METHODS

# Load environment variables for local development
load_dotenv()

# Page configuration
st.set_page_config(
    page_title="Just Bake - New Order",
    page_icon="🍕",
    layout="centered"
)

# Initialize Google Sheets client
@st.cache_resource
def get_sheets_client():
    """Initialize and cache Google Sheets client using Streamlit secrets or .env."""
    try:
        # Try Streamlit secrets first (for Streamlit Cloud deployment)
        try:
            credentials_dict = st.secrets["google_sheets_credentials"]
        except:
            # Fall back to .env file (for local development)
            credentials_json = os.getenv("GOOGLE_SHEETS_CREDENTIALS")
            if not credentials_json:
                raise ValueError("No Google Sheets credentials found in secrets or .env")
            credentials_dict = json.loads(credentials_json)

        # Create credentials from the dictionary
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        credentials = Credentials.from_service_account_info(
            credentials_dict,
            scopes=scopes
        )

        client = gspread.authorize(credentials)
        return client
    except Exception as e:
        st.error(f"Failed to initialize Google Sheets client: {e}")
        return None

def get_spreadsheet():
    """Get the PIZZA TIME spreadsheet."""
    client = get_sheets_client()
    if client is None:
        return None

    try:
        # Try Streamlit secrets first, fall back to .env
        try:
            spreadsheet_id = st.secrets["spreadsheet_id"]
        except:
            spreadsheet_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
            if not spreadsheet_id:
                raise ValueError("No spreadsheet ID found in secrets or .env")

        return client.open_by_key(spreadsheet_id)
    except Exception as e:
        st.error(f"Failed to open spreadsheet: {e}")
        return None

def calculate_total(product_data):
    """Calculate total order amount."""
    total = 0.0
    for product in PRODUCTS:
        prefix = product["column_prefix"]
        qty = product_data.get(f"{prefix}_qty", 0)
        price = product_data.get(f"{prefix}_price", 0.0)
        total += qty * price
    return total

def validate_order(customer_name, product_data):
    """Validate order data before submission."""
    errors = []

    # Check customer name
    if not customer_name or not customer_name.strip():
        errors.append("Customer name is required")

    # Check if at least one product has quantity and price
    has_items = False
    for product in PRODUCTS:
        prefix = product["column_prefix"]
        qty = product_data.get(f"{prefix}_qty", 0)
        price = product_data.get(f"{prefix}_price", 0.0)
        if qty > 0 and price > 0:
            has_items = True
            break

    if not has_items:
        errors.append("At least one product must have quantity and price greater than 0")

    return errors

def submit_order(customer_name, order_date, payment_method, product_data, phone="", business_id=""):
    """Submit order to Google Sheets."""
    spreadsheet = get_spreadsheet()
    if spreadsheet is None:
        return False, "Failed to connect to Google Sheets"

    try:
        # Get the first worksheet (or specify sheet name if needed)
        worksheet = spreadsheet.get_worksheet(0)

        # Generate unique row ID
        row_id = str(uuid.uuid4())

        # Calculate total
        total = calculate_total(product_data)

        # Format date as DD/MM/YYYY
        formatted_date = order_date.strftime("%d/%m/%Y")

        # Build row data - matched to your PIZZA TIME 2026 sheet structure
        # A: Date, B: Customer Name, C: Amount, D: Payment Method, E: Create Invoice, F: Invoice URL
        row_data = [
            formatted_date,                            # A: Date
            customer_name,                             # B: Customer Name
            total,                                     # C: Amount (₪)
            PAYMENT_METHODS[payment_method],           # D: payment method
            "",                                        # E: create invoice (empty by default)
            "",                                        # F: invoice_url (empty, filled by automation)
        ]

        # Add product quantities and prices (G through Z)
        # G-H: Neapolitan Kit, I-J: Spelt Kit, K-L: Gluten-free Kit,
        # M-N: Neapolitan Dough, O-P: Spelt Dough, Q-R: Gluten-free Dough,
        # S-T: White Sauce, U-V: Red Sauce, W-X: Opening Flour
        for i, product in enumerate(PRODUCTS):
            prefix = product["column_prefix"]

            # Special case: Cheese (last product) has SWAPPED columns (Price, Qty)
            if i == 9:  # Cheese
                row_data.append(product_data.get(f"{prefix}_price", 0.0))  # Y: Cheese Price
                row_data.append(product_data.get(f"{prefix}_qty", 0))      # Z: Cheese Qty
            else:  # All other products: Qty, Price
                row_data.append(product_data.get(f"{prefix}_qty", 0))
                row_data.append(product_data.get(f"{prefix}_price", 0.0))

        # AA: RowId, AB: Status, AC: Phone, AD: Business ID
        row_data.append(row_id)                        # AA: RowId
        row_data.append("")                            # AB: Status (empty, filled by automation on error)
        row_data.append(phone or "")                   # AC: Phone Number
        row_data.append(business_id or "")             # AD: Business ID

        # Append row to sheet
        worksheet.append_row(row_data)

        return True, row_id

    except Exception as e:
        return False, str(e)

# Main UI
st.title("🍕 Just Bake - New Order Entry")
st.markdown("**Pashut La'afot** - Neapolitan Pizza Ordering System")
st.divider()

# Customer Information Section
st.subheader("Customer Information")

col1, col2 = st.columns(2)
with col1:
    customer_name = st.text_input("Customer Name *", placeholder="Enter customer name")
with col2:
    phone = st.text_input("Phone Number", placeholder="050-1234567 (optional)")

col3, col4 = st.columns(2)
with col3:
    order_date = st.date_input("Order Date *", value=datetime.now())
with col4:
    payment_method = st.selectbox(
        "Payment Method *",
        options=list(PAYMENT_METHODS.keys()),
        format_func=lambda x: PAYMENT_METHODS[x]
    )

# Business customer section (optional)
with st.expander("🏢 Business Customer (B2B) - Optional"):
    business_id = st.text_input(
        "Business ID (ח.פ. / עוסק מורשה)",
        placeholder="e.g., 123456789",
        help="Leave empty for regular customers. Fill in for business customers who need tax invoice."
    )

st.divider()

# Products Section
st.subheader("Products")

# Initialize session state for product data if not exists
if 'product_data' not in st.session_state:
    st.session_state.product_data = {}

# Create product input grid
for i, product in enumerate(PRODUCTS):
    prefix = product["column_prefix"]

    # Create columns for product row
    col_name, col_qty, col_price = st.columns([3, 1, 1.5])

    with col_name:
        st.markdown(f"**{product['hebrew']}** _{product['name']}_")

    with col_qty:
        qty = st.number_input(
            "Qty",
            min_value=0,
            value=st.session_state.product_data.get(f"{prefix}_qty", 0),
            step=1,
            key=f"{prefix}_qty",
            label_visibility="collapsed"
        )
        st.session_state.product_data[f"{prefix}_qty"] = qty

    with col_price:
        price = st.number_input(
            "Price",
            min_value=0.0,
            value=st.session_state.product_data.get(f"{prefix}_price", 0.0),
            step=0.01,
            format="%.2f",
            key=f"{prefix}_price",
            label_visibility="collapsed"
        )
        st.session_state.product_data[f"{prefix}_price"] = price

st.divider()

# Total Display
total = calculate_total(st.session_state.product_data)
st.markdown(f"### Total: ₪{total:.2f}")

st.divider()

# Submit Button
col_submit, col_clear = st.columns([1, 1])

with col_submit:
    if st.button("📝 Submit Order", type="primary", use_container_width=True):
        # Validate order
        errors = validate_order(customer_name, st.session_state.product_data)

        if errors:
            for error in errors:
                st.error(error)
        else:
            # Submit order
            with st.spinner("Submitting order..."):
                success, result = submit_order(
                    customer_name,
                    order_date,
                    payment_method,
                    st.session_state.product_data,
                    phone,
                    business_id
                )

            if success:
                st.success(f"✅ Order submitted successfully! Order ID: {result}")
                # Clear form
                st.session_state.product_data = {}
                st.balloons()
                # Suggest rerun to clear inputs
                st.info("Click 'Clear Form' to enter another order")
            else:
                st.error(f"❌ Failed to submit order: {result}")

with col_clear:
    if st.button("🗑️ Clear Form", use_container_width=True):
        st.session_state.product_data = {}
        st.rerun()

# Footer
st.divider()
st.caption("Just Bake Invoice Automation System • Built with Streamlit")

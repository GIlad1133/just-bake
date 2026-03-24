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
    layout="wide"
)

# Password Protection
def check_password():
    """Returns True if the user had the correct password."""

    def password_entered():
        """Checks whether a password entered by the user is correct."""
        if st.session_state["password"] == st.secrets.get("app_password", "justbake2024"):
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # Don't store password
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        # First run, show password input
        st.title("🍕 Just Bake - Login")
        st.text_input(
            "Password",
            type="password",
            on_change=password_entered,
            key="password"
        )
        st.info("Enter the password to access the order entry system")
        return False
    elif not st.session_state["password_correct"]:
        # Password incorrect, show input + error
        st.title("🍕 Just Bake - Login")
        st.text_input(
            "Password",
            type="password",
            on_change=password_entered,
            key="password"
        )
        st.error("😕 Password incorrect")
        return False
    else:
        # Password correct
        return True

if not check_password():
    st.stop()

# Initialize Google Sheets client
@st.cache_resource
def get_sheets_client():
    """Initialize and cache Google Sheets client using Streamlit secrets or .env."""
    try:
        # Try multiple credential formats for Streamlit Cloud compatibility
        credentials_dict = None
        method_used = None

        # Method 1: Try GOOGLE_CREDENTIALS_JSON (direct JSON string in secrets)
        try:
            creds_json = st.secrets.get("GOOGLE_CREDENTIALS_JSON")
            if creds_json:
                credentials_dict = json.loads(creds_json)
                method_used = "GOOGLE_CREDENTIALS_JSON"
        except Exception as e:
            # Debug: Show what went wrong with Method 1
            if "GOOGLE_CREDENTIALS_JSON" in st.secrets:
                st.warning(f"Method 1 failed: {e}")

        # Method 2: Try nested google_sheets_credentials (original TOML format)
        if not credentials_dict:
            try:
                credentials_dict = dict(st.secrets["google_sheets_credentials"])
                method_used = "google_sheets_credentials (TOML)"
            except Exception as e:
                # Debug: Show what went wrong with Method 2
                if "google_sheets_credentials" in st.secrets:
                    st.warning(f"Method 2 failed: {e}")

        # Method 3: Fall back to .env file (for local development)
        if not credentials_dict:
            credentials_json = os.getenv("GOOGLE_SHEETS_CREDENTIALS")
            if credentials_json:
                credentials_dict = json.loads(credentials_json)
                method_used = ".env file"
            else:
                # Show available secrets for debugging (without values)
                available_secrets = list(st.secrets.keys()) if hasattr(st.secrets, 'keys') else []
                raise ValueError(f"No Google Sheets credentials found. Available secrets: {available_secrets}")

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

        # Show which method worked (only in debug/first load)
        if method_used:
            st.success(f"✅ Connected using: {method_used}")

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

@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_existing_customers():
    """Fetch existing customers with their phone numbers from Google Sheets."""
    spreadsheet = get_spreadsheet()
    if spreadsheet is None:
        return {}

    try:
        worksheet = spreadsheet.get_worksheet(0)
        # Get all data (skip header row)
        all_data = worksheet.get_all_values()[1:]

        # Build customer dictionary: {customer_name: phone_number}
        customers = {}
        for row in all_data:
            if len(row) >= 29:  # Make sure row has customer name (B) and phone (AC)
                customer_name = row[1].strip()  # Column B (index 1)
                phone = row[28].strip() if len(row) > 28 else ""  # Column AC (index 28)

                # Only add if customer name exists and not already in dict
                if customer_name and customer_name not in customers:
                    customers[customer_name] = phone

        return customers
    except Exception as e:
        st.warning(f"Could not load existing customers: {e}")
        return {}

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

# Load existing customers
existing_customers = get_existing_customers()
customer_options = ["🆕 New Customer"] + sorted(existing_customers.keys())

# Customer selection with autocomplete
col1, col2 = st.columns(2)
with col1:
    selected_customer = st.selectbox(
        "Select Customer *",
        options=customer_options,
        index=0,
        help="Select existing customer or choose 'New Customer' to enter a new name"
    )

    # If "New Customer" is selected, show text input
    if selected_customer == "🆕 New Customer":
        customer_name = st.text_input(
            "Customer Name *",
            placeholder="Enter new customer name",
            label_visibility="collapsed"
        )
    else:
        customer_name = selected_customer
        st.caption(f"✓ Selected: {customer_name}")

with col2:
    # Auto-fill phone if customer exists
    default_phone = ""
    if selected_customer != "🆕 New Customer" and selected_customer in existing_customers:
        default_phone = existing_customers[selected_customer]

    phone = st.text_input(
        "Phone Number",
        value=default_phone,
        placeholder="050-1234567 (optional)"
    )

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
            value=st.session_state.product_data.get(f"{prefix}_qty"),
            step=1,
            key=f"{prefix}_qty",
            label_visibility="collapsed",
            placeholder="0"
        )
        st.session_state.product_data[f"{prefix}_qty"] = qty if qty is not None else 0

    with col_price:
        price = st.number_input(
            "Price",
            min_value=0.0,
            value=st.session_state.product_data.get(f"{prefix}_price"),
            step=0.01,
            format="%.2f",
            key=f"{prefix}_price",
            label_visibility="collapsed",
            placeholder="0.00"
        )
        st.session_state.product_data[f"{prefix}_price"] = price if price is not None else 0.0

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
                st.balloons()
                # Clear form data
                st.session_state.product_data = {}
                # Auto-reload to clear all inputs
                import time
                time.sleep(2)  # Show success message for 2 seconds
                st.rerun()
            else:
                st.error(f"❌ Failed to submit order: {result}")

with col_clear:
    if st.button("🗑️ Clear Form", use_container_width=True):
        st.session_state.product_data = {}
        st.rerun()

# Footer
st.divider()
st.caption("Just Bake Invoice Automation System • Built with Streamlit")

"""
Google Sheets client for Just Bake.
Handles reading orders and updating invoice status.
"""

import gspread
from google.oauth2.service_account import Credentials
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import json
import os
from .models import Order, OrderItem


class GoogleSheetsClient:
    """Client for interacting with the PIZZA TIME Google Sheets."""

    # Column indices (0-based) - Matched to your "PIZZA TIME" 2026 sheet
    COL_DATE = 0                # Column A: Date
    COL_CUSTOMER_NAME = 1       # Column B: Customer Name
    COL_TOTAL_AMOUNT = 2        # Column C: Amount (₪)
    COL_PAYMENT_METHOD = 3      # Column D: payment method
    COL_CREATE_INVOICE = 4      # Column E: create invoice
    COL_INVOICE_URL = 5         # Column F: invoice_url

    # Product columns start at index 6 (Column G)
    # Each product has 2 columns: qty, price (except Cheese which is swapped!)
    COL_PRODUCTS_START = 6
    NUM_PRODUCTS = 10

    # Special handling needed:
    COL_ROW_ID = 26             # Column AA: RowId (at the end!)
    COL_STATUS = 27             # Column AB: Status/error message (we'll add this)
    COL_PHONE = 28              # Column AC: Phone Number (optional)
    COL_BUSINESS_ID = 29        # Column AD: Business ID / ח.פ. (optional, for B2B)

    # Product names (same order as PRODUCTS in products.py)
    PRODUCT_NAMES = [
        "ערכה נפוליטנית",    # Neapolitan Kit
        "ערכה כוסמין",       # Spelt Kit
        "ערכה ללא גלוטן",    # Gluten-free Kit
        "בצק נפוליטני",      # Neapolitan Dough
        "בצק כוסמין",        # Spelt Dough
        "בצק ללא גלוטן",     # Gluten-free Dough
        "רוטב לבן",          # White Sauce
        "רוטב אדום",         # Red Sauce
        "קמח פתיחה",         # Opening Flour
        "גבינה",             # Cheese
    ]

    def __init__(self, credentials_path: Optional[str] = None, spreadsheet_id: Optional[str] = None):
        """
        Initialize Google Sheets client.

        Args:
            credentials_path: Path to service account JSON or JSON string
            spreadsheet_id: Google Sheets spreadsheet ID
        """
        # Load credentials
        if credentials_path is None:
            # Try to load from environment variable
            credentials_json = os.getenv('GOOGLE_SHEETS_CREDENTIALS')
            if not credentials_json:
                raise ValueError("No credentials provided. Set GOOGLE_SHEETS_CREDENTIALS env var or pass credentials_path")

            # Parse JSON from environment variable
            credentials_dict = json.loads(credentials_json)
        elif os.path.isfile(credentials_path):
            # Load from file
            credentials_dict = json.load(open(credentials_path))
        else:
            # Assume it's a JSON string
            credentials_dict = json.loads(credentials_path)

        # Create credentials
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
        ]
        credentials = Credentials.from_service_account_info(credentials_dict, scopes=scopes)

        # Initialize gspread client
        self.client = gspread.authorize(credentials)

        # Get spreadsheet
        if spreadsheet_id is None:
            spreadsheet_id = os.getenv('GOOGLE_SHEETS_SPREADSHEET_ID')
            if not spreadsheet_id:
                raise ValueError("No spreadsheet_id provided. Set GOOGLE_SHEETS_SPREADSHEET_ID env var or pass spreadsheet_id")

        self.spreadsheet = self.client.open_by_key(spreadsheet_id)
        self.worksheet = self.spreadsheet.get_worksheet(0)  # First sheet

    def _parse_date(self, date_value: Any) -> datetime:
        """
        Parse date from Google Sheets cell.

        Handles both:
        - DD/MM/YY or DD/MM/YYYY string format
        - Excel serial date numbers

        Args:
            date_value: Cell value from Google Sheets

        Returns:
            datetime object
        """
        if isinstance(date_value, str):
            # Try DD/MM/YYYY format
            for fmt in ["%d/%m/%Y", "%d/%m/%y"]:
                try:
                    return datetime.strptime(date_value, fmt)
                except ValueError:
                    continue
            raise ValueError(f"Unable to parse date: {date_value}")

        elif isinstance(date_value, (int, float)):
            # Excel serial date (days since 1899-12-30)
            # Google Sheets uses the same epoch as Excel
            epoch = datetime(1899, 12, 30)
            return epoch + timedelta(days=date_value)

        else:
            raise ValueError(f"Unexpected date type: {type(date_value)}")

    def _extract_items(self, row: List[Any]) -> List[OrderItem]:
        """
        Extract order items from sheet row.

        Args:
            row: Row data from Google Sheets

        Returns:
            List of OrderItem objects (only items with qty > 0 and price > 0)
        """
        items = []

        for i in range(self.NUM_PRODUCTS):
            # Calculate column indices for this product
            # NOTE: Cheese (product index 9) has SWAPPED columns (Price, Qty instead of Qty, Price)
            if i == 9:  # Cheese - columns are swapped!
                price_col = self.COL_PRODUCTS_START + (i * 2)      # Y (24): Cheese Price
                qty_col = self.COL_PRODUCTS_START + (i * 2) + 1    # Z (25): Cheese Qty
            else:  # All other products: Qty, Price
                qty_col = self.COL_PRODUCTS_START + (i * 2)
                price_col = self.COL_PRODUCTS_START + (i * 2) + 1

            # Get values (handle missing columns)
            qty = int(row[qty_col]) if qty_col < len(row) and row[qty_col] else 0
            price = float(row[price_col]) if price_col < len(row) and row[price_col] else 0.0

            # Only include if both qty and price are > 0
            if qty > 0 and price > 0:
                item = OrderItem(
                    name=self.PRODUCT_NAMES[i],
                    quantity=qty,
                    price_per_unit=price
                )
                items.append(item)

        return items

    def get_pending_orders(self, max_date: Optional[datetime] = None) -> List[Order]:
        """
        Get all orders where "create invoice" = "yes".

        Returns:
            List of Order objects ready for invoice creation
        """
        # Get all rows (skip header)
        all_rows = self.worksheet.get_all_values()[1:]  # Skip header row

        pending_orders = []

        for row_idx, row in enumerate(all_rows, start=2):  # Start at 2 (row 1 is header)
            # Check if "create invoice" column is "yes"
            create_invoice_flag = row[self.COL_CREATE_INVOICE] if self.COL_CREATE_INVOICE < len(row) else ""

            if create_invoice_flag.strip().lower() == "yes":
                # Skip if payment method is "-" (incomplete/invalid order)
                payment_method = row[self.COL_PAYMENT_METHOD] if self.COL_PAYMENT_METHOD < len(row) else ""
                if payment_method.strip() == "-":
                    print(f"Skipping row {row_idx}: Payment method is '-'")
                    continue
                try:
                    # Parse order date first to check date filter
                    order_date = self._parse_date(row[self.COL_DATE])

                    # Skip if order is after max_date
                    if max_date and order_date > max_date:
                        print(f"Skipping row {row_idx}: Order date {order_date.date()} is after {max_date.date()}")
                        continue

                    # Get RowId (handle missing or empty)
                    row_id = row[self.COL_ROW_ID] if self.COL_ROW_ID < len(row) and row[self.COL_ROW_ID] else str(row_idx)

                    # Get optional fields
                    phone = row[self.COL_PHONE] if self.COL_PHONE < len(row) and row[self.COL_PHONE] else ""
                    business_id = row[self.COL_BUSINESS_ID] if self.COL_BUSINESS_ID < len(row) and row[self.COL_BUSINESS_ID] else ""

                    # Parse order data
                    order = Order(
                        row_id=str(row_id),
                        customer_name=row[self.COL_CUSTOMER_NAME],
                        order_date=order_date,
                        payment_method=row[self.COL_PAYMENT_METHOD],
                        total_amount=float(row[self.COL_TOTAL_AMOUNT]),
                        items=self._extract_items(row),
                        sheet_row_number=row_idx,
                        phone=phone,
                        business_id=business_id
                    )
                    pending_orders.append(order)

                except Exception as e:
                    print(f"Warning: Failed to parse row {row_idx}: {e}")
                    continue

        return pending_orders

    def update_order_status(
        self,
        row_number: int,
        status: str,
        invoice_url: Optional[str] = None,
        error_msg: Optional[str] = None
    ):
        """
        Update order status after invoice processing.

        Args:
            row_number: Row number in sheet (1-based)
            status: Status value ("Done", "Error", etc.)
            invoice_url: Invoice URL (if successful)
            error_msg: Error message (if failed)
        """
        # Update "create invoice" flag
        self.worksheet.update_cell(row_number, self.COL_CREATE_INVOICE + 1, status)

        # Update invoice URL if provided
        if invoice_url:
            self.worksheet.update_cell(row_number, self.COL_INVOICE_URL + 1, invoice_url)

        # Update status/error message if provided
        if error_msg:
            self.worksheet.update_cell(row_number, self.COL_STATUS + 1, error_msg)

    def mark_invoice_created(self, row_number: int, invoice_url: str):
        """
        Mark invoice as successfully created.

        Args:
            row_number: Row number in sheet (1-based)
            invoice_url: URL of created invoice
        """
        self.update_order_status(row_number, "Done", invoice_url=invoice_url)

    def mark_invoice_error(self, row_number: int, error_msg: str):
        """
        Mark invoice creation as failed.

        Args:
            row_number: Row number in sheet (1-based)
            error_msg: Error message to record
        """
        self.update_order_status(row_number, "Error", error_msg=error_msg)

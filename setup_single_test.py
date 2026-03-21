#!/usr/bin/env python3
"""
Set up sheet for single order test.
"""

import sys
sys.path.insert(0, '/home/gilad/Projects/just-bake')

from dotenv import load_dotenv
from src.google_sheets import GoogleSheetsClient

load_dotenv()

print("=" * 70)
print("Setting up sheet for SINGLE ORDER test")
print("=" * 70)
print()

# Initialize client
sheets = GoogleSheetsClient()

# Get all rows
all_rows = sheets.worksheet.get_all_values()

# Find rows with "create invoice" = "yes"
test_row = None
other_rows = []

for i, row in enumerate(all_rows[1:], start=2):  # Start from row 2
    if len(row) <= 4:
        continue

    create_invoice_flag = row[4] if len(row) > 4 else ""
    customer_name = row[1] if len(row) > 1 else ""
    amount = row[2] if len(row) > 2 else ""

    if create_invoice_flag.strip().lower() == "yes":
        if test_row is None:
            # Keep first one as "yes"
            test_row = (i, customer_name, amount)
            print(f"✅ Will process: Row {i} - {customer_name} (₪{amount})")
        else:
            # Change others to "hold"
            other_rows.append((i, customer_name, amount))
            sheets.worksheet.update_cell(i, 5, "hold")  # Column E
            print(f"⏸️  Set to 'hold': Row {i} - {customer_name} (₪{amount})")

print()
if test_row:
    print("=" * 70)
    print(f"Ready to test with 1 order: {test_row[1]} (₪{test_row[2]})")
    print("This will create a REAL invoice in production!")
    print("=" * 70)
else:
    print("⚠️  No orders with 'create invoice' = 'yes' found!")

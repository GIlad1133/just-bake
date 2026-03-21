#!/usr/bin/env python3
"""Debug row 30 with actual Order parsing."""

import sys
sys.path.insert(0, '/home/gilad/Projects/just-bake')

from dotenv import load_dotenv
from src.google_sheets import GoogleSheetsClient

load_dotenv()

sheets = GoogleSheetsClient()

# Get the specific order using the same logic as the automation
all_rows = sheets.worksheet.get_all_values()[1:]  # Skip header

row_idx = 30
row = all_rows[row_idx - 2]  # Adjust for 0-based index

print(f"=== Debugging Row {row_idx} ===")
print(f"Customer: {row[sheets.COL_CUSTOMER_NAME]}")
print(f"Sheet total: ₪{row[sheets.COL_TOTAL_AMOUNT]}")
print()

# Extract items using the same method as automation
items = sheets._extract_items(row)

print("Items extracted by automation:")
total = 0.0
for item in items:
    print(f"  {item.name}: {item.quantity} x ₪{item.price_per_unit} = ₪{item.total_price}")
    total += item.total_price

print()
print(f"Calculated total: ₪{total}")
print(f"Sheet total: ₪{float(row[sheets.COL_TOTAL_AMOUNT])}")
print(f"Difference: ₪{abs(float(row[sheets.COL_TOTAL_AMOUNT]) - total)}")
print()

# Show raw Cheese columns
print("Raw Cheese columns:")
print(f"  Column Y (24): {row[24] if len(row) > 24 else 'N/A'}")
print(f"  Column Z (25): {row[25] if len(row) > 25 else 'N/A'}")

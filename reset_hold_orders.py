#!/usr/bin/env python3
"""Reset orders on 'hold' to 'yes' for processing."""

import sys
sys.path.insert(0, '/home/gilad/Projects/just-bake')

from dotenv import load_dotenv
from src.google_sheets import GoogleSheetsClient

load_dotenv()

sheets = GoogleSheetsClient()
all_rows = sheets.worksheet.get_all_values()

print("Resetting orders from 'hold' to 'yes'...")
count = 0

for i, row in enumerate(all_rows[1:], start=2):
    if len(row) > 4:
        create_invoice = row[4].strip().lower()
        customer = row[1] if len(row) > 1 else ""

        if create_invoice == "hold":
            sheets.worksheet.update_cell(i, 5, "yes")
            print(f"✅ Row {i}: {customer} - reset to 'yes'")
            count += 1

print(f"\n✅ Reset {count} orders from 'hold' to 'yes'")

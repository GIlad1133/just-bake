#!/usr/bin/env python3
"""
Add Phone Number and Business ID columns to Google Sheet.
"""

import sys
sys.path.insert(0, '/home/gilad/Projects/just-bake')

from dotenv import load_dotenv
from src.google_sheets import GoogleSheetsClient

load_dotenv()

print("=" * 70)
print("Adding Phone Number and Business ID Columns")
print("=" * 70)
print()

# Initialize client
sheets = GoogleSheetsClient()

# Add headers to columns AC and AD
print("Adding column headers...")
sheets.worksheet.update_cell(1, 29, "Phone Number")  # Column AC (index 28)
sheets.worksheet.update_cell(1, 30, "Business ID")   # Column AD (index 29)

print("✅ Added headers:")
print("  Column AC (28): Phone Number")
print("  Column AD (29): Business ID")
print()
print("These columns are optional:")
print("  - Leave empty for regular customers")
print("  - Fill in Phone Number for all customers (recommended)")
print("  - Fill in Business ID only for business customers (B2B)")
print()
print("=" * 70)

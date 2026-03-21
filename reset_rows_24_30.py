#!/usr/bin/env python3
"""Reset rows 24 and 30 back to 'yes'."""

import sys
sys.path.insert(0, '/home/gilad/Projects/just-bake')

from dotenv import load_dotenv
from src.google_sheets import GoogleSheetsClient

load_dotenv()

sheets = GoogleSheetsClient()

print("Resetting rows 24 and 30 to 'yes'...")

# Reset row 24
sheets.worksheet.update_cell(24, 5, "yes")  # Column E
sheets.worksheet.update_cell(24, 28, "")     # Column AB (clear error)
print("✅ Row 24: אוריאל שמעוני - Reset to 'yes'")

# Reset row 30
sheets.worksheet.update_cell(30, 5, "yes")
sheets.worksheet.update_cell(30, 28, "")
print("✅ Row 30: עדן נקוה - Reset to 'yes'")

print("\n✅ Both rows ready to process!")

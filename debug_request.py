#!/usr/bin/env python3
"""
Debug what we're sending to Keep.co.il API.
"""

import sys
sys.path.insert(0, '/home/gilad/Projects/just-bake')

from dotenv import load_dotenv
from src.google_sheets import GoogleSheetsClient
from src.models import Order, KeepReceipt, KeepReceiptItem
import json

load_dotenv()

print("=" * 70)
print("Debugging Keep.co.il Request Payload")
print("=" * 70)
print()

# Initialize Google Sheets client
sheets = GoogleSheetsClient()

# Get pending orders
orders = sheets.get_pending_orders()

if not orders:
    print("No pending orders found!")
    sys.exit(1)

# Take first order
order = orders[0]

print("=== ORDER DATA ===")
print(f"Customer: {order.customer_name}")
print(f"Date: {order.order_date}")
print(f"Payment: {order.payment_method}")
print(f"Total: ₪{order.total_amount}")
print(f"Items: {len(order.items)}")
for item in order.items:
    print(f"  - {item.name}: {item.quantity} x ₪{item.price_per_unit} = ₪{item.total_price}")
print()

# Build Keep receipt
receipt_items = [
    KeepReceiptItem(
        name=item.name,
        quantity=item.quantity,
        price=int(round(item.price_per_unit * 100))  # Convert to agorot
    )
    for item in order.items
]

payment_comment = f"תשלום ב{order.payment_method}"

receipt = KeepReceipt(
    customer_name=order.customer_name,
    doc_date=order.order_date,
    items=receipt_items,
    total_amount=order.total_agorot,
    payment_method_comment=payment_comment
)

# Convert to dict (what we send to API)
receipt_dict = receipt.to_dict()

print("=== KEEP.CO.IL API REQUEST ===")
print(json.dumps(receipt_dict, indent=2, ensure_ascii=False))
print()
print("=" * 70)

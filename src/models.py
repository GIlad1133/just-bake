"""
Data models for Just Bake invoice automation.
Provides type-safe representations of orders and Keep.co.il API formats.
"""

from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime


def _sanitize_phone(phone: Optional[str]) -> str:
    """Strip everything except ASCII digits from a phone number.

    Keep.co.il rejects numbers containing formatting characters — including
    invisible Unicode punctuation like U+2011 (non-breaking hyphen) and U+202C
    (pop directional formatting) copy-pasted from spreadsheet cells — with a
    400 "Invalid client phone format". Returns "" for None/empty input.
    """
    if not phone:
        return ""
    return "".join(ch for ch in str(phone) if ch in "0123456789")


@dataclass
class OrderItem:
    """Individual product in an order (dough, kit, sauce, etc.)"""
    name: str              # Hebrew product name
    quantity: int          # Number of units
    price_per_unit: float  # Price per unit in shekels

    @property
    def total_price(self) -> float:
        """Calculate total price for this item in shekels."""
        return self.quantity * self.price_per_unit

    @property
    def total_price_agorot(self) -> int:
        """Calculate total price for this item in agorot (1 shekel = 100 agorot)."""
        return int(round(self.total_price * 100))


@dataclass
class Order:
    """Order from Google Sheets row."""
    row_id: str                          # Unique identifier for the row
    customer_name: str                   # Customer name
    order_date: datetime                 # Date of order
    payment_method: str                  # Payment method (דיגיטלי, מזומן, העברה)
    total_amount: float                  # Total in shekels
    items: List[OrderItem] = field(default_factory=list)  # Order items
    sheet_row_number: Optional[int] = None  # Row number in sheet (for updates)
    phone: str = ""                      # Customer phone number (optional)
    business_id: str = ""                # Business tax ID / ח.פ. (optional, for B2B)

    def validate_total(self, tolerance: float = 0.01) -> bool:
        """
        Validate that sum of items matches total_amount.

        Args:
            tolerance: Maximum allowed difference in shekels (default 0.01)

        Returns:
            True if totals match within tolerance, False otherwise
        """
        calculated_total = sum(item.total_price for item in self.items)
        difference = abs(calculated_total - self.total_amount)
        # Round to agorot (cents) before comparing. The business works in whole
        # agorot, and raw float subtraction (e.g. 3 × 33.33 = 99.9899…) leaves
        # ~1e-15 of representation noise that would otherwise push an exact-0.01
        # difference just over tolerance and wrongly reject a valid order.
        return round(difference, 2) <= tolerance

    @property
    def total_agorot(self) -> int:
        """Get total amount in agorot."""
        return int(round(self.total_amount * 100))


@dataclass
class KeepReceiptItem:
    """Item in Keep.co.il receipt format."""
    name: str          # Product name (Hebrew)
    quantity: int      # Quantity
    price: int         # Price per unit in agorot

    def to_dict(self) -> dict:
        """Convert to Keep.co.il API format."""
        return {
            "name": self.name,
            "quantity": self.quantity,
            "itemNetPrice": self.price,  # Keep.co.il expects itemNetPrice, not price
            "itemCurrency": "ILS",
            "isNoItemVat": True
        }


@dataclass
class KeepReceipt:
    """Receipt in Keep.co.il API format."""
    customer_name: str                    # Customer name
    doc_date: datetime                    # Document date
    items: List[KeepReceiptItem]          # Receipt items
    total_amount: int                     # Total in agorot
    payment_method_comment: str           # Comment about payment method
    phone: str = ""                       # Customer phone (optional)
    business_id: str = ""                 # Business tax ID / ח.פ. (optional, for B2B)

    def to_dict(self) -> dict:
        """
        Convert to Keep.co.il API request format.

        Returns:
            Dictionary matching Keep.co.il income API schema
        """
        # Format datetime as "YYYY-MM-DD HH:MM:SS"
        formatted_date = self.doc_date.strftime("%Y-%m-%d %H:%M:%S")

        # Build client object
        client_data = {
            "name": self.customer_name,
            "phone": _sanitize_phone(self.phone)
        }

        # Add business ID if provided (for B2B customers)
        if self.business_id:
            client_data["socialId"] = self.business_id

        return {
            "type": "receipt",
            "client": client_data,
            "docValueDate": formatted_date,
            "docLang": "he",
            "items": [item.to_dict() for item in self.items],
            "currency": "ILS",
            "originTaxDeduction": 0,
            "totalAmount": self.total_amount,
            "totalPaid": self.total_amount,
            "comment": self.payment_method_comment,
            "cc": {
                "date": formatted_date,
                "last4Digits": "0000",
                "amount": self.total_amount
            }
        }

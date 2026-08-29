"""
Tests for data models.
"""

from datetime import datetime
from src.models import Order, OrderItem, KeepReceipt, KeepReceiptItem, _sanitize_phone


def test_order_item_total_price():
    """Test OrderItem total price calculation."""
    item = OrderItem(
        name="ערכה נפוליטנית",
        quantity=2,
        price_per_unit=50.0
    )

    assert item.total_price == 100.0
    assert item.total_price_agorot == 10000


def test_order_item_agorot_rounding():
    """Test agorot conversion with rounding."""
    item = OrderItem(
        name="בצק נפוליטני",
        quantity=3,
        price_per_unit=33.33
    )

    # 3 × 33.33 = 99.99 shekels = 9999 agorot
    assert item.total_price_agorot == 9999


def test_order_validate_total_valid():
    """Test order total validation - valid case."""
    items = [
        OrderItem("ערכה נפוליטנית", 2, 50.0),
        OrderItem("רוטב אדום", 1, 10.0),
    ]

    order = Order(
        row_id="test-123",
        customer_name="Test Customer",
        order_date=datetime.now(),
        payment_method="דיגיטלי",
        total_amount=110.0,
        items=items
    )

    assert order.validate_total() is True


def test_order_validate_total_invalid():
    """Test order total validation - invalid case."""
    items = [
        OrderItem("ערכה נפוליטנית", 2, 50.0),  # Total: 100
    ]

    order = Order(
        row_id="test-123",
        customer_name="Test Customer",
        order_date=datetime.now(),
        payment_method="דיגיטלי",
        total_amount=110.0,  # Mismatch!
        items=items
    )

    assert order.validate_total() is False


def test_order_validate_total_with_tolerance():
    """Test order total validation with floating point tolerance."""
    items = [
        OrderItem("בצק נפוליטני", 3, 33.33),  # Total: 99.99
    ]

    order = Order(
        row_id="test-123",
        customer_name="Test Customer",
        order_date=datetime.now(),
        payment_method="מזומן",
        total_amount=100.0,  # 0.01 difference
        items=items
    )

    # Should pass with default tolerance (0.01)
    assert order.validate_total() is True


def test_keep_receipt_item_to_dict():
    """Test KeepReceiptItem serialization."""
    item = KeepReceiptItem(
        name="ערכה כוסמין",
        quantity=1,
        price=5000  # 50 shekels in agorot
    )

    data = item.to_dict()

    assert data == {
        "name": "ערכה כוסמין",
        "quantity": 1,
        "itemNetPrice": 5000,
        "itemCurrency": "ILS",
        "isNoItemVat": True,
    }


def test_keep_receipt_to_dict():
    """Test KeepReceipt serialization."""
    items = [
        KeepReceiptItem("ערכה נפוליטנית", 2, 5000),
        KeepReceiptItem("רוטב לבן", 1, 1000),
    ]

    receipt = KeepReceipt(
        customer_name="Test Customer",
        doc_date=datetime(2024, 3, 15, 14, 30, 0),
        items=items,
        total_amount=11000,  # 110 shekels in agorot
        payment_method_comment="תשלום בדיגיטלי"
    )

    data = receipt.to_dict()

    # Verify structure
    assert data["type"] == "receipt"
    assert data["client"]["name"] == "Test Customer"
    assert data["docValueDate"] == "2024-03-15 14:30:00"
    assert data["docLang"] == "he"
    assert data["currency"] == "ILS"
    assert data["totalAmount"] == 11000
    assert data["totalPaid"] == 11000
    assert data["comment"] == "תשלום בדיגיטלי"
    assert len(data["items"]) == 2

    # Verify items
    assert data["items"][0]["name"] == "ערכה נפוליטנית"
    assert data["items"][0]["quantity"] == 2
    assert data["items"][0]["itemNetPrice"] == 5000


def test_sanitize_phone_strips_unicode_punctuation():
    # Real-world failure: shahar avital's row had U+2011 (non-breaking hyphen)
    # and U+202C (pop directional formatting) — Keep.co.il returned
    # "Invalid client phone format" 400.
    dirty = "050‑632‑9235‬"
    assert _sanitize_phone(dirty) == "0506329235"


def test_sanitize_phone_handles_empty_and_none_like():
    assert _sanitize_phone("") == ""
    assert _sanitize_phone(None) == ""


def test_sanitize_phone_strips_ascii_formatting():
    assert _sanitize_phone("050-632-9235") == "0506329235"
    assert _sanitize_phone("(050) 632 9235") == "0506329235"
    assert _sanitize_phone("+972-50-632-9235") == "972506329235"


def test_keep_receipt_sanitizes_phone_in_payload():
    receipt = KeepReceipt(
        customer_name="שחר אביטל",
        doc_date=datetime(2026, 5, 21),
        items=[KeepReceiptItem("ערכה נפוליטנית", 1, 12000)],
        total_amount=12000,
        payment_method_comment="תשלום בPaybox",
        phone="050‑632‑9235‬",
    )
    assert receipt.to_dict()["client"]["phone"] == "0506329235"

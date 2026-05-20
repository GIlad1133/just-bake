"""Read-only orders fetcher shared across admin pages.

The Admin page has its own session-cached load_all_orders with write
invalidation. The Statistics page is read-only, so we keep a separate
fetcher here that returns a flat list of order dicts and is cached for
60s per session.
"""

from __future__ import annotations

import time
from datetime import datetime

import streamlit as st

from sheets_client import get_spreadsheet
from products import PRODUCTS


_CACHE_KEY = "_stats_orders_cache"
_CACHE_AT_KEY = "_stats_orders_cache_at"
_TTL_SEC = 60


def _safe_float(row, idx):
    try:
        return float(row[idx]) if len(row) > idx and row[idx] else 0.0
    except (ValueError, TypeError):
        return 0.0


def _safe_int(row, idx):
    try:
        return int(float(row[idx])) if len(row) > idx and row[idx] else 0
    except (ValueError, TypeError):
        return 0


def _normalize_dmy(date_str):
    if not date_str:
        return ""
    s = str(date_str).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%d/%m/%Y")
        except ValueError:
            continue
    return s


def _parse_date(date_str):
    if not date_str:
        return None
    s = str(date_str).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def fetch_all_orders():
    """Return all orders parsed into dicts. Session-cached for 60s."""
    cached_at = st.session_state.get(_CACHE_AT_KEY)
    if cached_at and (time.time() - cached_at) < _TTL_SEC:
        cached = st.session_state.get(_CACHE_KEY)
        if cached is not None:
            return cached

    spreadsheet = get_spreadsheet()
    if not spreadsheet:
        return []

    try:
        worksheet = spreadsheet.get_worksheet(0)
        rows = worksheet.get_all_values()
    except Exception as e:
        st.error(f"Failed to load orders: {e}")
        return []

    if len(rows) <= 1:
        return []

    orders = []
    for i, row in enumerate(rows[1:], start=2):
        if len(row) < 6:
            continue
        customer = row[1].strip() if len(row) > 1 else ""
        if not customer:
            continue

        products = {}
        for pi, product in enumerate(PRODUCTS):
            prefix = product["column_prefix"]
            if "qty_col" in product:
                products[f"{prefix}_qty"] = _safe_int(row, product["qty_col"])
                products[f"{prefix}_price"] = _safe_float(row, product["price_col"])
            elif pi == 9:  # Cheese: Price(Y=24) then Qty(Z=25) — swapped
                products[f"{prefix}_price"] = _safe_float(row, 24)
                products[f"{prefix}_qty"] = _safe_int(row, 25)
            else:
                qty_idx = 6 + 2 * pi
                price_idx = 6 + 2 * pi + 1
                products[f"{prefix}_qty"] = _safe_int(row, qty_idx)
                products[f"{prefix}_price"] = _safe_float(row, price_idx)

        orders.append({
            "row": i,
            "date_str": row[0] if len(row) > 0 else "",
            "date": _parse_date(row[0]),
            "customer": customer,
            "amount": _safe_float(row, 2),
            "payment_method": row[3] if len(row) > 3 else "",
            "create_invoice": row[4] if len(row) > 4 else "",
            "invoice_url": row[5] if len(row) > 5 else "",
            "row_id": row[26] if len(row) > 26 else "",
            "status": row[27] if len(row) > 27 else "",
            "phone": row[28] if len(row) > 28 else "",
            "picked_up": (
                row[32].strip().lower() == "yes"
                if len(row) > 32 and row[32]
                else False
            ),
            "dough_type": (
                row[33].strip().lower()
                if len(row) > 33 and row[33]
                else ""
            ),
            "bake_date": _normalize_dmy(row[34]) if len(row) > 34 and row[34] else "",
            "products": products,
        })

    st.session_state[_CACHE_KEY] = orders
    st.session_state[_CACHE_AT_KEY] = time.time()
    return orders


def invalidate_orders_cache():
    """Drop the cached orders so the next fetch re-reads from Sheets."""
    st.session_state.pop(_CACHE_KEY, None)
    st.session_state.pop(_CACHE_AT_KEY, None)

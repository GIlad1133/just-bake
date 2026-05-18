"""HTML5 date picker wrapped as a Streamlit custom component.

Wraps a native ``<input type="date" lang="he-IL">`` so the browser's
calendar popup respects Hebrew locale conventions — the first column
is Sunday, last is Saturday.

Streamlit's built-in ``st.date_input`` doesn't expose any way to set
the first day of week from Python (its calendar is locale-derived via
``Intl`` in the React frontend), so we wrap our own.
"""

from __future__ import annotations

import os
from datetime import datetime, date as _date

import streamlit as st
import streamlit.components.v1 as components


_COMPONENT_DIR = os.path.join(os.path.dirname(__file__), "components", "date_he")
_date_he_component = components.declare_component("date_he", path=_COMPONENT_DIR)


def date_input_dmy(
    label: str,
    value=None,
    key: str | None = None,
    on_change=None,
    label_visibility: str = "visible",
    help: str | None = None,
):
    """Drop-in replacement for ``st.date_input`` with a Sunday-first calendar.

    Returns a ``datetime.date``. Falls back to the passed value if the
    component returns nothing parseable.
    """
    if value is None:
        value = _date.today()
    if isinstance(value, datetime):
        value = value.date()

    value_iso = value.strftime("%Y-%m-%d")

    if label_visibility == "visible":
        line = f"**{label}**"
        if help:
            line += f"  \n*{help}*"
        st.markdown(line)

    raw = _date_he_component(
        value=value_iso,
        key=key,
        default=value_iso,
        on_change=on_change,
    )

    if raw:
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            return value
    return value

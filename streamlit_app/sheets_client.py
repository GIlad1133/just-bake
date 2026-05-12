"""
Shared Google Sheets client — imported by both app.py and pages/1_Admin.py.
Using a single module ensures @st.cache_resource is shared across all pages.
"""

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import os


@st.cache_resource
def get_sheets_client():
    """Initialize and cache Google Sheets client. Shared across all pages."""
    credentials_dict = None
    load_errors = []

    try:
        creds_json = st.secrets.get("GOOGLE_CREDENTIALS_JSON")
        if creds_json:
            credentials_dict = json.loads(creds_json)
    except Exception as e:
        load_errors.append(f"GOOGLE_CREDENTIALS_JSON: {e}")

    if not credentials_dict:
        try:
            credentials_dict = dict(st.secrets["google_sheets_credentials"])
        except Exception as e:
            load_errors.append(f"google_sheets_credentials: {e}")

    if not credentials_dict:
        credentials_json = os.getenv("GOOGLE_SHEETS_CREDENTIALS")
        if credentials_json:
            try:
                credentials_dict = json.loads(credentials_json)
            except Exception as e:
                load_errors.append(f".env: {e}")

    if not credentials_dict:
        raise ValueError(f"No Google Sheets credentials found. Tried: {'; '.join(load_errors)}")

    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
    ]
    credentials = Credentials.from_service_account_info(credentials_dict, scopes=scopes)
    return gspread.authorize(credentials)


@st.cache_resource
def _open_spreadsheet(spreadsheet_id: str):
    """Cached spreadsheet handle keyed by id — avoids fetching metadata on every rerun."""
    return get_sheets_client().open_by_key(spreadsheet_id)


def get_spreadsheet():
    """Get the spreadsheet by ID from secrets or env.

    Cached across reruns; if the cached handle goes stale (auth refresh,
    transient API error), we clear the cache and retry once before giving up.
    """
    spreadsheet_id = (
        st.secrets.get("spreadsheet_id")
        or os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
    )
    if not spreadsheet_id:
        raise ValueError("No spreadsheet ID found.")
    try:
        return _open_spreadsheet(spreadsheet_id)
    except Exception:
        _open_spreadsheet.clear()
        get_sheets_client.clear()
        return _open_spreadsheet(spreadsheet_id)

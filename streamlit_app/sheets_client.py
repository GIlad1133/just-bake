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

    try:
        creds_json = st.secrets.get("GOOGLE_CREDENTIALS_JSON")
        if creds_json:
            credentials_dict = json.loads(creds_json)
    except Exception:
        pass

    if not credentials_dict:
        try:
            credentials_dict = dict(st.secrets["google_sheets_credentials"])
        except Exception:
            pass

    if not credentials_dict:
        credentials_json = os.getenv("GOOGLE_SHEETS_CREDENTIALS")
        if credentials_json:
            credentials_dict = json.loads(credentials_json)

    if not credentials_dict:
        raise ValueError("No Google Sheets credentials found.")

    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
    ]
    credentials = Credentials.from_service_account_info(credentials_dict, scopes=scopes)
    return gspread.authorize(credentials)


def get_spreadsheet():
    """Get the spreadsheet by ID from secrets or env."""
    client = get_sheets_client()
    spreadsheet_id = (
        st.secrets.get("spreadsheet_id")
        or os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
    )
    if not spreadsheet_id:
        raise ValueError("No spreadsheet ID found.")
    return client.open_by_key(spreadsheet_id)

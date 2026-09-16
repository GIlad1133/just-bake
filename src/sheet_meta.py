"""Small key/value state in a Meta tab.

Used for the Telegram update offset, which must survive between runs or the
same reply is processed repeatedly.
"""

import logging

import gspread

log = logging.getLogger(__name__)

META_SHEET = "Meta"


def _sheet(spreadsheet):
    try:
        return spreadsheet.worksheet(META_SHEET)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(META_SHEET, rows=50, cols=2)
        ws.update("A1", [["key", "value"]])
        return ws


def get_meta(spreadsheet, key: str, default: str = "") -> str:
    for row in _sheet(spreadsheet).get_all_values()[1:]:
        if row and row[0] == key:
            return row[1] if len(row) > 1 else default
    return default


def set_meta(spreadsheet, key: str, value: str) -> None:
    ws = _sheet(spreadsheet)
    for i, row in enumerate(ws.get_all_values()[1:], start=2):
        if row and row[0] == key:
            ws.update_cell(i, 2, str(value))
            return
    ws.append_row([key, str(value)])

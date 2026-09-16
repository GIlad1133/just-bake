"""Answer templates and facts, stored in Sheet tabs so Gilad can edit them
from his phone without a deploy.

Read lazily — only when a post crosses the alert threshold (about once a day),
not on every run.
"""

import logging

import gspread

log = logging.getLogger(__name__)

TEMPLATES_SHEET = "Templates"
FACTS_SHEET = "Facts"

# Seeds written on first creation. Gilad edits them in the sheet afterwards.
TEMPLATE_ROWS = {
    "order": ("קודם תבדוק אם אתה יכול לעזור בכלל (גאוגרפיה), ואז עובדות יבשות על המוצר. "
              "בלי מחיר, בלי קישור, בלי שורת סיום."),
    "mentoring": ("טיפ אחד עם מספר, ומה קורה אם לא. בלי מחיר, בלי הצעת סדנה, "
                  "בלי שורת סיום."),
    "professional": "תשובה מקצועית מלאה, ערך נקי. שום דבר שיווקי.",
    "event": "כמויות, לוח זמנים, איסוף. בלי מחיר סופי לפני שיודעים כמות.",
}

FACT_ROWS = [
    "בצק בסיס לקילו קמח: 660 גרם מים (66%), 28 גרם מלח, שמרים לפי זמן התפחה",
    "24 שעות קור = 3 גרם שמרים טריים לקילו קמח",
    "48 שעות קור = 2 גרם שמרים טריים לקילו קמח",
    "72 שעות קור = 1 גרם שמרים טריים לקילו קמח",
    "כדור בצק במתכון = 250 גרם. המוצר שגלעד מוכר = כ-300 גרם, 48 שעות, טרי או קפוא",
    "טאבון: לתת להתחמם 30 דקות בכל הפעלה. אבן בסביבות 350 מעלות לפיצה",
]


def _read_tab(spreadsheet, name: str, seed_rows: list) -> list:
    try:
        ws = spreadsheet.worksheet(name)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(name, rows=200, cols=2)
        ws.update("A1", seed_rows)
        log.info(f"Created {name} tab with {len(seed_rows)} seed rows")
        return seed_rows
    return [r for r in ws.get_all_values() if any(r)]


def load_templates(spreadsheet) -> dict:
    rows = _read_tab(spreadsheet, TEMPLATES_SHEET,
                     [[k, v] for k, v in TEMPLATE_ROWS.items()])
    return {r[0]: r[1] for r in rows if len(r) >= 2 and r[0]}


def load_facts(spreadsheet) -> list:
    rows = _read_tab(spreadsheet, FACTS_SHEET, [[f] for f in FACT_ROWS])
    return [r[0] for r in rows if r and r[0].strip()]


HISTORY_SHEET = "Templates_history"


def update_template(spreadsheet, path: str, text: str) -> None:
    """Overwrite one template, keeping the previous value. A typo in /order
    would otherwise destroy wording with no undo."""
    ws = spreadsheet.worksheet(TEMPLATES_SHEET)
    rows = ws.get_all_values()
    for i, row in enumerate(rows, start=1):
        if row and row[0] == path:
            try:
                hist = spreadsheet.worksheet(HISTORY_SHEET)
            except gspread.WorksheetNotFound:
                hist = spreadsheet.add_worksheet(HISTORY_SHEET, rows=500, cols=3)
                hist.update("A1", [["path", "previous_text", "replaced_at"]])
            from datetime import datetime
            hist.append_row([path, row[1] if len(row) > 1 else "",
                             datetime.now().strftime("%d/%m/%Y %H:%M")])
            ws.update_cell(i, 2, text)
            return
    ws.append_row([path, text])


def render_guidance(templates: dict, facts: list) -> str:
    """Prompt fragment. Empty string when both tabs are empty, so the prompt
    is unchanged rather than carrying a dangling header."""
    if not templates and not facts:
        return ""
    parts = []
    if templates:
        parts.append("## מבני תשובה לפי lead_path\n" +
                     "\n".join(f"- {k}: {v}" for k, v in templates.items()))
    if facts:
        parts.append("## עובדות מאומתות — השתמש רק במספרים האלה.\n"
                     "אם המספר הדרוש לא כאן, ענה בלי מספרים. אל תמציא.\n" +
                     "\n".join(f"- {f}" for f in facts))
    return "\n\n".join(parts)

"""Header-keyed row building for the Community sheet.

Rows used to be built as positional lists, which silently misaligned when
columns were added (200 rows carry question_type="noise" because "noise" was
written one position early). Build rows from a dict keyed by header name.
"""

COMMUNITY_HEADERS = [
    "date_fetched", "group_url", "post_url", "post_author",
    "post_date", "post_text", "comments", "answer",
    "score", "score_reason", "tags", "question_type", "status", "posted_date",
    "image_url", "image_description", "post_type", "my_answer",
    # added 16/09/2026 — lead alerting
    "lead_score", "lead_path", "notified_at", "tg_message_id",
    # added 30/09/2026 — voice
    "situation",
]

_HEADER_SET = set(COMMUNITY_HEADERS)


def build_row(values: dict) -> list:
    """Map {header_name: value} to a positional row matching COMMUNITY_HEADERS.

    Raises KeyError on an unknown column name so a typo fails loudly at write
    time instead of silently landing in the wrong column.
    """
    unknown = sorted(set(values) - _HEADER_SET)
    if unknown:
        raise KeyError(f"Unknown Community columns: {unknown}")
    return [values.get(header, "") for header in COMMUNITY_HEADERS]


def row_to_dict(row: list) -> dict:
    """Inverse of build_row, tolerant of short rows from older sheet writes."""
    return {h: (row[i] if i < len(row) else "") for i, h in enumerate(COMMUNITY_HEADERS)}

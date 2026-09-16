# Facebook Lead Alerts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the once-daily Facebook group scraper into a 4-hourly pipeline that scores posts on two axes, pushes lead alerts to Telegram with a ready-to-paste reply, monitors itself, and ingests Gilad's corrections back from Telegram.

**Architecture:** The existing pipeline (`src/community_monitor.py` → Apify → Claude → Google Sheets) is kept and extended, not rebuilt. Scoring gains a second axis (`lead_score`) and a template path. A new `src/telegram_notify.py` owns all Telegram I/O and has no Sheets or Apify dependencies. A new `src/sheet_meta.py` owns small key/value state (Telegram update offset). Sheet writes move from positional lists to header-keyed dicts, which is what permanently kills the column-misalignment bug class.

**Tech Stack:** Python 3.11, `gspread`, `apify-client<3`, `anthropic` (Haiku 4.5), `requests`, `pytest` + `pytest-mock`, GitHub Actions, Telegram Bot API, healthchecks.io.

**Spec:** `docs/superpowers/specs/2026-09-16-facebook-lead-alerts-design.md`

**Already done outside this plan (no task needed):** Telegram bot `@justbake_bot` created; repo secrets `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `HEALTHCHECK_URL` set; healthchecks.io check created; `secret.txt` added to `.gitignore`.

**Manual step still outstanding for Gilad:** change the healthchecks.io cron from `*/30 4-20 * * *` to `0 4,8,12,16,20 * * *` (UTC). Until then it raises false alarms. Referenced again in Task 13.

---

## File Structure

| File | Responsibility | Status |
|---|---|---|
| `src/community_monitor.py` | Orchestration: fetch → filter → score → write → notify | Modify |
| `src/sheet_rows.py` | `COMMUNITY_HEADERS` + header-keyed row building | **Create** |
| `src/telegram_notify.py` | Format, send, and read Telegram messages. No Sheets/Apify imports | **Create** |
| `src/sheet_meta.py` | Key/value state in a `Meta` tab (Telegram offset) | **Create** |
| `src/answer_templates.py` | Lazy read of `Templates` and `Facts` tabs | **Create** |
| `tests/test_sheet_rows.py` | Row building + the noise regression | **Create** |
| `tests/test_telegram_notify.py` | Formatting, escaping, alert rule, reply auth | **Create** |
| `tests/test_scoring.py` | Claude response parsing, two-axis fields | **Create** |
| `tests/conftest.py` | Shared fixtures built from real posts in the sheet | **Create** |
| `.github/workflows/community-monitor.yml` | Cadence, concurrency, crash alert | Modify |
| `pytest.ini` | Test discovery config | **Create** |

`tests/` currently contains only `__init__.py` — there are no existing tests. Task 1 establishes the harness.

---

## Phase 1 — Foundations

### Task 1: Test harness and header-keyed rows

**Why this is first:** every later task writes to the sheet, and the current code builds rows as bare positional lists. That is what produced the `question_type="noise"` bug in 200 rows. Fixing the mechanism first means no later task can reintroduce it.

**Files:**
- Create: `pytest.ini`
- Create: `src/sheet_rows.py`
- Create: `tests/test_sheet_rows.py`

- [ ] **Step 1: Install the dev dependencies**

`pytest-mock` is listed in `requirements.txt` but is not present in `.venv`, and every mocked
test below uses its `mocker` fixture.

Run: `.venv/bin/pip install -r requirements.txt`
Then verify: `.venv/bin/python -c "import pytest_mock; print('ok')"`
Expected: `ok`

- [ ] **Step 2: Create pytest config**

```ini
# pytest.ini
[pytest]
testpaths = tests
python_files = test_*.py
python_functions = test_*
addopts = -v
```

- [ ] **Step 3: Write the failing test**

```python
# tests/test_sheet_rows.py
import pytest
from src.sheet_rows import COMMUNITY_HEADERS, build_row


def test_build_row_places_values_by_header_name():
    row = build_row({"post_url": "https://fb.com/p/1", "status": "pending", "score": 7})
    assert len(row) == len(COMMUNITY_HEADERS)
    assert row[COMMUNITY_HEADERS.index("post_url")] == "https://fb.com/p/1"
    assert row[COMMUNITY_HEADERS.index("status")] == "pending"
    assert row[COMMUNITY_HEADERS.index("score")] == 7


def test_build_row_defaults_missing_columns_to_empty_string():
    row = build_row({"post_url": "u"})
    assert row[COMMUNITY_HEADERS.index("question_type")] == ""
    assert row[COMMUNITY_HEADERS.index("my_answer")] == ""


def test_build_row_rejects_unknown_column():
    with pytest.raises(KeyError, match="typo_column"):
        build_row({"typo_column": "x"})


def test_headers_contain_the_four_new_columns():
    for col in ("lead_score", "lead_path", "notified_at", "tg_message_id"):
        assert col in COMMUNITY_HEADERS
```

- [ ] **Step 4: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_sheet_rows.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.sheet_rows'`

- [ ] **Step 5: Write the implementation**

```python
# src/sheet_rows.py
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
```

- [ ] **Step 6: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_sheet_rows.py -v`
Expected: PASS, 4 passed

- [ ] **Step 7: Commit**

```bash
git add pytest.ini src/sheet_rows.py tests/test_sheet_rows.py
git commit -m "Community: build sheet rows by header name, not position

Positional row building silently misaligned when columns were added.
Adds the four lead-alerting columns at the same time.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Fix the noise-row column bug

**Files:**
- Modify: `src/community_monitor.py` (the `COMMUNITY_HEADERS` constant at line 24, and the noise `append_row` at ~line 290)
- Modify: `tests/test_sheet_rows.py`

- [ ] **Step 1: Write the failing regression test**

```python
# append to tests/test_sheet_rows.py
from src.community_monitor import build_noise_row


def test_noise_row_writes_noise_to_status_not_question_type():
    """Regression: 200 existing rows have question_type="noise" and empty status."""
    post = {"url": "https://fb.com/p/9", "facebookUrl": "https://fb.com/groups/1",
            "text": "טאבון למכירה", "user": {"name": "דני"}, "time": "2026-09-16"}
    row = build_noise_row(post, reason="למכירה")

    assert row[COMMUNITY_HEADERS.index("status")] == "noise"
    assert row[COMMUNITY_HEADERS.index("question_type")] == ""
    assert row[COMMUNITY_HEADERS.index("score")] == -1
    assert row[COMMUNITY_HEADERS.index("score_reason")] == "למכירה"
    assert row[COMMUNITY_HEADERS.index("lead_score")] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_sheet_rows.py::test_noise_row_writes_noise_to_status_not_question_type -v`
Expected: FAIL — `ImportError: cannot import name 'build_noise_row'`

- [ ] **Step 3: Replace the header constant in community_monitor.py**

Delete the local `COMMUNITY_HEADERS` list at `src/community_monitor.py:24-30` and import it instead. Add near the other imports:

```python
from src.sheet_rows import COMMUNITY_HEADERS, build_row
```

- [ ] **Step 4: Add the noise row builder**

Add to `src/community_monitor.py`, directly below `is_noise()`:

```python
def build_noise_row(post: dict, reason: str) -> list:
    """Row for a post rejected by the noise pre-filter — no Claude call made."""
    return build_row({
        "date_fetched": datetime.now().strftime("%d/%m/%Y"),
        "group_url": post.get("facebookUrl", ""),
        "post_url": post.get("url", ""),
        "post_author": post.get("user", {}).get("name", ""),
        "post_date": str(post.get("time", ""))[:10],
        "post_text": (post.get("text") or "")[:1000],
        "score": -1,
        "score_reason": reason,
        "status": "noise",
        "lead_score": 0,
        "lead_path": "none",
    })
```

- [ ] **Step 5: Replace the inline noise append**

In `run_monitor()`, replace the whole `ws.append_row([...])` block inside the `if noise:` branch with:

```python
            if noise:
                log.info(f"Skipping noise ({reason}): {url[:60]}")
                ws.append_row(build_noise_row(post, reason))
                known_posts[url] = {"row": None, "comment_count": 0}
                saved += 1
                continue
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_sheet_rows.py -v`
Expected: PASS, 5 passed

- [ ] **Step 7: Commit**

```bash
git add src/community_monitor.py tests/test_sheet_rows.py
git commit -m "Community: fix noise rows writing 'noise' into question_type

The noise append placed the status value one column early, so 200 rows have
question_type='noise' and an empty status. The Telegram alert filter reads
status, so this had to be correct before it could be trusted.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Phase 2 — Two-axis scoring

### Task 3: Parse lead fields from the Claude response

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/test_scoring.py`
- Modify: `src/community_monitor.py` (`score_and_answer`, ~line 126-225)

- [ ] **Step 1: Create shared fixtures from real mis-scored posts**

```python
# tests/conftest.py
import pytest


@pytest.fixture
def buyer_post():
    """Real post that the old rubric scored 3. A 60-ball order."""
    return {
        "url": "https://fb.com/p/buyer",
        "facebookUrl": "https://fb.com/groups/1061644604326919",
        "text": ("רוצה ליסוע לצפון בראשון לעשות ל 100 לוחמים מילואימניקים פיצות בטאבון "
                 "יש את כל המסביב מחפש מישהו שמוכר 50-60 כדורי פיצה לטאבון 300g אשמח לעזרה"),
        "user": {"name": "מאיר"},
        "time": "2026-09-16",
        "topComments": [],
    }


@pytest.fixture
def theory_post():
    """Real post that the old rubric scored 8. High expertise, zero lead."""
    return {
        "url": "https://fb.com/p/theory",
        "facebookUrl": "https://fb.com/groups/587379969063560",
        "text": "לחם מחמצת. מה הסיפור? מה זה בכלל מחמצת? אשמח לכל התובנות שלכם 🤍 תודה.",
        "user": {"name": "רונית"},
        "time": "2026-09-16",
        "topComments": [],
    }


@pytest.fixture
def cooking_post():
    """Real post Gilad rejected: new tabun owner, but asking what to COOK."""
    return {
        "url": "https://fb.com/p/cooking",
        "facebookUrl": "https://fb.com/groups/2926500980956274",
        "text": ("רכשנו טאבון גז cozzi עם צלחת מסתובבת . ממה מתחילים ? ירקות ? "
                 "אשמח לטיפים עבור מתחילים . תודה וחג שמח"),
        "user": {"name": "אורית"},
        "time": "2026-09-16",
        "topComments": [],
    }
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_scoring.py
import pytest
from src.community_monitor import parse_score_response


def test_parses_two_axis_response():
    raw = ('{"lead_score": 10, "lead_path": "order", "lead_reason": "רוצה לקנות 60 כדורים",'
           ' "score": 3, "score_reason": "בקשת רכש", "answer": "היי מאיר",'
           ' "tags": ["בצק"], "question_type": "where_to_buy", "post_type": "question",'
           ' "image_description": null}')
    out = parse_score_response(raw)
    assert out["lead_score"] == 10
    assert out["lead_path"] == "order"
    assert out["score"] == 3


def test_strips_markdown_fences():
    raw = '```json\n{"lead_score": 0, "lead_path": "none", "score": 2}\n```'
    out = parse_score_response(raw)
    assert out["lead_score"] == 0
    assert out["lead_path"] == "none"


def test_malformed_response_returns_safe_defaults():
    out = parse_score_response("not json at all")
    assert out["lead_score"] == 0
    assert out["score"] == 0
    assert out["lead_path"] == "none"
    assert out["answer"] is None


def test_out_of_range_scores_are_clamped():
    out = parse_score_response('{"lead_score": 99, "score": -5, "lead_path": "order"}')
    assert out["lead_score"] == 10
    assert out["score"] == 0


def test_unknown_lead_path_falls_back_to_none():
    out = parse_score_response('{"lead_score": 8, "lead_path": "banana", "score": 4}')
    assert out["lead_path"] == "none"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_scoring.py -v`
Expected: FAIL — `ImportError: cannot import name 'parse_score_response'`

- [ ] **Step 4: Write the parser**

Add to `src/community_monitor.py` above `score_and_answer`:

```python
VALID_LEAD_PATHS = {"order", "mentoring", "professional", "event", "none"}


def _clamp(value, low: int, high: int, default: int = 0) -> int:
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


def parse_score_response(text: str) -> dict:
    """Parse Claude's JSON reply into a validated result dict.

    Never raises: a malformed reply yields a zero-scored result so one bad post
    cannot abort the run.
    """
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        parts = cleaned.split("```")
        cleaned = parts[1] if len(parts) > 1 else ""
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
        if not isinstance(data, dict):
            raise ValueError("not an object")
    except Exception as e:
        log.warning(f"Unparseable Claude response ({e}): {(text or '')[:120]}")
        data = {}

    path = data.get("lead_path")
    return {
        "lead_score": _clamp(data.get("lead_score"), 0, 10),
        "lead_path": path if path in VALID_LEAD_PATHS else "none",
        "lead_reason": data.get("lead_reason") or "",
        "score": _clamp(data.get("score"), 0, 10),
        "score_reason": data.get("score_reason") or "",
        "answer": data.get("answer") or None,
        "tags": data.get("tags") or [],
        "question_type": data.get("question_type") or "",
        "post_type": data.get("post_type") or "",
        "image_description": data.get("image_description") or "",
    }
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_scoring.py -v`
Expected: PASS, 5 passed

- [ ] **Step 6: Use the parser in score_and_answer**

In `score_and_answer`, replace the response-handling block (everything from `text = resp.content[0].text.strip()` through the `return json.loads(text)`) with:

```python
        return parse_score_response(resp.content[0].text)
```

And replace the `except` block's return with:

```python
    except Exception as e:
        log.exception(f"Claude error for post {post.get('url','?')[:60]}: {e}")
        result = parse_score_response("")
        result["score_reason"] = str(e)
        return result
```

- [ ] **Step 7: Run all tests**

Run: `.venv/bin/python -m pytest -v`
Expected: PASS, 10 passed

- [ ] **Step 8: Commit**

```bash
git add src/community_monitor.py tests/test_scoring.py tests/conftest.py
git commit -m "Community: validated two-axis score parsing

Adds lead_score/lead_path alongside the existing expertise score, clamps
out-of-range values, and makes a malformed Claude reply a zero-scored post
rather than an aborted run.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Rewrite the scoring prompt for two axes

**Files:**
- Modify: `src/community_monitor.py` (the prompt inside `score_and_answer`, ~line 131-205)

This task changes prompt text only. It has no unit test — prompt quality is verified by Task 5's end-to-end dry run against real posts.

- [ ] **Step 1: Replace the scoring rules section of the prompt**

In the prompt string, delete the block that begins `ענה בJSON בלבד` through the end (the old `כללי ציון` block and the `הדגש:` line), and replace with:

```python
ענה בJSON בלבד (ללא markdown):
{{
  "image_description": "<תיאור קצר של התמונה, או null>",
  "post_type": "<question|showcase|ad|sale|welcome|other>",
  "lead_score": <0-10>,
  "lead_path": "<order|mentoring|professional|event|none>",
  "lead_reason": "<משפט אחד למה הציון הזה>",
  "score": <0-10>,
  "score_reason": "<משפט קצר>",
  "answer": "<תגובה בעברית, או null אם אין מה לענות>",
  "tags": ["<נושא>"],
  "question_type": "<where_to_buy|recipe_help|technique|equipment|ingredient|general_pizza|not_relevant>"
}}

## שני ציונים נפרדים — אל תבלבל ביניהם

### score (מומחיות): כמה טוב גלעד יכול לענות מקצועית
9-10: שאלה ישירה על בצק, תסיסה, קמח או אפיית פיצה שגלעד יכול לענות עליה מניסיון
5-8: קשור לתחום, גלעד יכול להוסיף ערך
1-4: לא בתחום, או שכבר יש תשובות מלאות

### lead_score (כסף): כמה קרוב האדם לקנות מגלעד
הפוסט חייב לעבור את **שלושת השערים** כדי לקבל ציון מעל 0:
1. **כיוון**: הוא מחפש לקנות, לא מציע למכירה. מי שמוכר בצק הוא מתחרה, לא ליד.
2. **מוצר**: מה שהוא מחפש הוא משהו שגלעד מוכר — בצק, ערכות, רוטב, קמח, גבינה, סדנאות.
   לא מיקסרים, לא מלושים, לא טאבונים, לא אבני שמוט, לא שקיות תבלין.
3. **היקף**: שימוש ביתי/אישי. לא סיטונאות, לא פיצריה, לא ספקות B2B.
   מיקום גאוגרפי לא פוסל: אופה ביתי בצפון שמחפש קמח הוא ליד.

10: עובר את שלושת השערים — רוצה לקנות בצק/ערכה/רוטב/קמח/גבינה בכל כמות,
    **או** בעל טאבון חדש בלי ידע **שמכוון לפיצה ובצק**
7-9: מחפש ספק לאירוע פרטי, מתעניין בסדנה, שאלה על מוצר ספציפי
4-6: אופה ביתי מנוסה שמכין לבד
1-3: לומד תאוריה, או ציוד שגלעד לא בקיא בו
0: מוכר משהו, תמונה בלי שאלה, פרסומת, או כל פנייה עסקית/פיצרייה/סיטונאות

**חשוב — שער 2 חל גם על בעל טאבון חדש.** מי שקנה טאבון ושואל מה **לבשל** בו
(ירקות, בשר, טיפים כלליים) אין לו בעיית בצק והוא לא ליד. ציון נמוך, ו-answer=null.

## lead_path — קובע את מבנה התשובה
order: רוצה לקנות בצק עכשיו
mentoring: בעל טאבון חדש שמכוון לפיצה
event: מחפש ספק לאירוע פרטי
professional: שאלה מקצועית טהורה (score גבוה, lead נמוך)
none: אין מה לענות

## כללי ניסוח לתשובה — חובה
1. פתיחה אנושית קצרה.
2. **טיפ אחד בלבד**, לא שניים. אל תסביר לו דבר שהוא כבר יודע או כבר קנה.
3. **תמיד מספר** — 30 דקות, 350 מעלות, 48 שעות, 300 גרם. טיפ בלי מספר הוא מילוי.
4. תגיד מה קורה אם לא — "אחרת תקבל תוצאה מבאסת".
5. **בלי שורת סיום.** בלי "תשאל אותי", בלי קישור, בלי הזמנה. תסיים על עובדה.
6. **בלי מחיר בהודעה הראשונה, גם ב-order.** קודם תבדוק שאתה יכול לעזור
   ("אם איזור פתח תקווה בכיוון שלך אשמח לעזור"), ואז תגיד מה המוצר.
7. בלי אימוג'י. ":)" מותר.
8. שתיים עד ארבע שורות.

אם אין מה לענות — answer=null. עדיף לא לענות מאשר לדחוף הצעה.
```

- [ ] **Step 2: Verify the prompt still formats**

Run: `.venv/bin/python -c "import src.community_monitor as m; print('imports ok')"`
Expected: `imports ok` (catches unbalanced braces in the f-string)

- [ ] **Step 3: Commit**

```bash
git add src/community_monitor.py
git commit -m "Community: score posts on lead and expertise axes separately

The old rubric put 'sale' in the 1-4 band, so people wanting to BUY dough
scored below people asking theory questions. Adds a three-gate lead score
and the voice rules derived from Gilad's own replies.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Dry-run the new scoring against real posts

**Files:**
- Create: `scripts/score_dryrun.py`

This is a throwaway verification script. It is deleted in Task 18, per the repo convention of not keeping temp scripts.

- [ ] **Step 1: Write the dry-run script**

```python
# scripts/score_dryrun.py
"""Score a handful of known posts with the new prompt and print the result.

Costs a few Claude Haiku calls (fractions of a cent). No sheet writes.
Run: .venv/bin/python scripts/score_dryrun.py
"""
import os
import sys
import anthropic
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.community_monitor import score_and_answer

load_dotenv()

CASES = [
    ("SHOULD BE lead 10 / order", {
        "url": "x", "text": "מחפש מישהו שמוכר 50-60 כדורי פיצה לטאבון 300g לאירוע",
        "user": {"name": "מאיר"}, "time": "2026-09-16", "topComments": []}),
    ("SHOULD BE lead 0-3 / professional, high score", {
        "url": "x", "text": "לחם מחמצת. מה הסיפור? מה זה בכלל מחמצת?",
        "user": {"name": "רונית"}, "time": "2026-09-16", "topComments": []}),
    ("SHOULD BE lead LOW, answer=null (asking what to COOK)", {
        "url": "x", "text": "רכשנו טאבון גז cozzi. ממה מתחילים? ירקות? אשמח לטיפים",
        "user": {"name": "אורית"}, "time": "2026-09-16", "topComments": []}),
    ("SHOULD BE lead 0 (selling)", {
        "url": "x", "text": "טאבון איכותי גדול מבער עוצמתי 0545250429 גמיש במחיר",
        "user": {"name": "דני"}, "time": "2026-09-16", "topComments": []}),
    ("SHOULD BE lead 0 (mixer — outside expertise)", {
        "url": "x", "text": "מחפש לקנות מיקסר עד 3500 שח, עד 2 קילו בצק",
        "user": {"name": "יוסי"}, "time": "2026-09-16", "topComments": []}),
]

claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
for label, post in CASES:
    r = score_and_answer(post, claude)
    print(f"\n=== {label}")
    print(f"  lead={r['lead_score']} path={r['lead_path']} expertise={r['score']}")
    print(f"  why : {r['lead_reason'][:110]}")
    print(f"  ans : {(r['answer'] or '(none)')[:200]}")
```

- [ ] **Step 2: Run it**

Run: `.venv/bin/python scripts/score_dryrun.py`

Expected, and **stop and revise the Task 4 prompt if any of these fail**:
- Case 1: `lead=10`, `path=order`, answer contains no price and no link
- Case 2: `lead` ≤ 3, `score` ≥ 8, `path=professional`
- Case 3: `lead` ≤ 3, `answer` is `(none)`
- Case 4: `lead=0`
- Case 5: `lead=0`

- [ ] **Step 3: Commit only if the prompt needed changes**

```bash
git add src/community_monitor.py
git commit -m "Community: tune lead scoring prompt against real posts

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Phase 3 — Cost and cadence

### Task 6: Filter posts at Apify instead of paying for duplicates

**Files:**
- Modify: `src/community_monitor.py` (`fetch_posts`, lines 71-88)
- Create: `tests/test_fetch_input.py`

**Measured facts this implements:** the actor charges $0.008 per run plus ~$0.006 per post examined; `onlyPostsNewerThan` filters *before* billing (verified 16/09). `resultsLimit: 10` has been truncating the daily scrape, so coverage is deliberately partial.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_fetch_input.py
from datetime import datetime, timedelta, timezone
from src.community_monitor import build_run_input, LOOKBACK_HOURS


def test_run_input_includes_iso_cutoff_not_relative_string():
    inp = build_run_input(["https://fb.com/groups/1"])
    cutoff = inp["onlyPostsNewerThan"]
    assert cutoff.endswith("Z"), "Apify needs an ISO timestamp, not a relative string"
    parsed = datetime.fromisoformat(cutoff.replace("Z", "+00:00"))
    expected = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    assert abs((parsed - expected).total_seconds()) < 120


def test_lookback_exceeds_cadence_so_a_delayed_run_loses_nothing():
    assert LOOKBACK_HOURS > 4


def test_run_input_maps_every_group():
    urls = ["https://fb.com/groups/1", "https://fb.com/groups/2"]
    assert build_run_input(urls)["startUrls"] == [{"url": u} for u in urls]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_fetch_input.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_run_input'`

- [ ] **Step 3: Write the implementation**

Add to `src/community_monitor.py`, and add `timezone` to the existing `datetime` import:

```python
LOOKBACK_HOURS = 5      # > the 4h cadence, so a delayed run still overlaps
POSTS_PER_GROUP = 5     # deliberate coverage cap; cost tracks posts examined


def build_run_input(group_urls: list) -> dict:
    """Apify input. onlyPostsNewerThan filters BEFORE billing (verified 16/09/2026),
    so it is the only lever that stops us re-buying posts already in the sheet."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)) \
        .replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "startUrls": [{"url": url} for url in group_urls],
        "resultsLimit": POSTS_PER_GROUP,
        "maxComments": 3,
        "sortOrder": "RECENT_POSTS",
        "onlyPostsNewerThan": cutoff,
        "proxyConfiguration": {"useApifyProxy": True},
    }
```

Then replace the body of `fetch_posts` so it uses it:

```python
def fetch_posts(group_urls: list, apify_token: str) -> list:
    client = ApifyClient(apify_token)
    run_input = build_run_input(group_urls)
    log.info(f"Fetching from {len(group_urls)} groups since {run_input['onlyPostsNewerThan']}")
    run = client.actor("apify/facebook-groups-scraper").call(run_input=run_input)
    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    valid = [item for item in items if item.get("text") and item.get("url")]
    for item in valid:
        attachments = item.get("attachments") or []
        item["image_url"] = next(
            (a.get("thumbnail") or a.get("photo_image", {}).get("uri")
             for a in attachments if a.get("thumbnail") or a.get("photo_image")),
            None,
        )
    log.info(f"Got {len(valid)} posts ({sum(1 for p in valid if p.get('image_url'))} with images)")
    return valid
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_fetch_input.py -v`
Expected: PASS, 3 passed

- [ ] **Step 5: Remove the now-redundant client-side date filter**

`_is_recent()` filtered to `RECENT_DAYS = 3` in Python, after we had already paid Apify. Apify now filters server-side. In `run_monitor()`, delete the line `posts = [p for p in posts if _is_recent(p)]` and the log line referencing `RECENT_DAYS`, then delete `_is_recent` and the `RECENT_DAYS` constant.

- [ ] **Step 6: Run all tests**

Run: `.venv/bin/python -m pytest -v`
Expected: PASS, 18 passed

- [ ] **Step 7: Commit**

```bash
git add src/community_monitor.py tests/test_fetch_input.py
git commit -m "Community: filter posts at Apify to stop re-buying duplicates

Apify bills per post extracted, before our dedup runs, so the daily job has
been paying for ~63 posts to learn about ~14 new ones. onlyPostsNewerThan
filters before billing (verified). Also drops resultsLimit 10 -> 5 as a
deliberate coverage cap.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Move to a 4-hour cadence with no overlapping runs

**Files:**
- Modify: `.github/workflows/community-monitor.yml`

- [ ] **Step 1: Replace the trigger block**

Replace lines 3-6 (`on:` through `workflow_dispatch:`) with:

```yaml
on:
  schedule:
    # 04:00/08:00/12:00/16:00/20:00 UTC = 07:00/11:00/15:00/19:00/23:00 Israel (summer).
    # Must stay identical to the healthchecks.io cron or that alarms falsely.
    - cron: '0 4,8,12,16,20 * * *'
  workflow_dispatch:

# Telegram replies are drained from a shared queue; two runs at once would
# double-process them. Queue rather than overlap.
concurrency:
  group: community-monitor
  cancel-in-progress: false
```

- [ ] **Step 2: Add the new secrets to the run step**

In the `Run community monitor` step's `env:` block, add:

```yaml
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          HEALTHCHECK_URL: ${{ secrets.HEALTHCHECK_URL }}
          DASHBOARD_URL: https://just-bake.streamlit.app/Community
```

- [ ] **Step 3: Validate the YAML**

Run: `grep -A2 'schedule:' .github/workflows/community-monitor.yml && grep -c 'concurrency:' .github/workflows/community-monitor.yml`
Expected: the cron line reads `- cron: '0 4,8,12,16,20 * * *'`, and the concurrency count is `1`.
(`pyyaml` is deliberately not added as a dependency for two one-off checks.)

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/community-monitor.yml
git commit -m "Community: run every 4 hours instead of daily

Latency 24h -> 3-4h for less than the current spend, once Apify stops being
billed for duplicates. Adds a concurrency group so runs queue rather than
overlap, which matters once Telegram replies are drained from a shared queue.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Phase 4 — Telegram alerts

### Task 8: Format an alert message

**Files:**
- Create: `src/telegram_notify.py`
- Create: `tests/test_telegram_notify.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_telegram_notify.py
from src.telegram_notify import format_alert, should_notify


def test_alert_shows_path_and_both_scores():
    text = format_alert(
        post={"text": "מחפש 60 כדורי בצק", "url": "https://fb.com/p/1"},
        result={"lead_score": 10, "lead_path": "order", "score": 3, "answer": "היי מאיר"},
        group_name="הטאבון הביתי")
    assert "10" in text
    assert "הזמנה" in text
    assert "הטאבון הביתי" in text


def test_answer_is_wrapped_in_code_for_tap_to_copy():
    text = format_alert(
        post={"text": "x", "url": "u"},
        result={"lead_score": 9, "lead_path": "order", "score": 4, "answer": "התשובה"},
        group_name="g")
    assert "<code>התשובה</code>" in text


def test_html_special_characters_are_escaped():
    """An unescaped < or & in a post makes Telegram reject the whole message."""
    text = format_alert(
        post={"text": "עלות < 100 & עוד", "url": "u"},
        result={"lead_score": 8, "lead_path": "event", "score": 5, "answer": "a & b"},
        group_name="g")
    assert "&lt;" in text and "&amp;" in text
    assert "< 100 &" not in text


def test_long_post_is_truncated():
    text = format_alert(
        post={"text": "א" * 900, "url": "u"},
        result={"lead_score": 8, "lead_path": "order", "score": 5, "answer": "a"},
        group_name="g")
    assert len(text) < 1200


def test_missing_answer_does_not_crash():
    text = format_alert(
        post={"text": "x", "url": "u"},
        result={"lead_score": 7, "lead_path": "none", "score": 2, "answer": None},
        group_name="g")
    assert isinstance(text, str)


def test_notify_on_high_lead():
    assert should_notify(lead_score=7, expertise_score=1, notified_at="") is True


def test_notify_on_high_expertise():
    assert should_notify(lead_score=0, expertise_score=9, notified_at="") is True


def test_no_notify_below_both_thresholds():
    assert should_notify(lead_score=6, expertise_score=8, notified_at="") is False


def test_no_notify_when_already_notified():
    assert should_notify(lead_score=10, expertise_score=10, notified_at="16/09/2026 11:00") is False


def test_blank_notified_at_is_still_eligible():
    assert should_notify(lead_score=10, expertise_score=0, notified_at="   ") is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_telegram_notify.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.telegram_notify'`

- [ ] **Step 3: Write the implementation**

```python
# src/telegram_notify.py
"""Telegram delivery for Just Bake lead alerts.

Push-only by design: alerts go to one fixed chat id, never to whoever last
messaged the bot. The bot's username is public, so anyone can press Start;
the fixed destination is what makes that harmless.

No Sheets or Apify imports — this module only knows about Telegram.
"""

import html
import logging

import requests

log = logging.getLogger(__name__)

API = "https://api.telegram.org/bot{token}/{method}"
EXCERPT_CHARS = 180
ANSWER_CHARS = 700

LEAD_THRESHOLD = 7
EXPERTISE_THRESHOLD = 9

PATH_LABELS = {
    "order":        ("🔥", "הזמנה"),
    "mentoring":    ("🌱", "ליווי"),
    "event":        ("📅", "אירוע"),
    "professional": ("💬", "מקצועי"),
    "none":         ("💬", "כללי"),
}


def should_notify(lead_score: int, expertise_score: int, notified_at: str) -> bool:
    """One alert per post, ever. An empty notified_at means still eligible."""
    if (notified_at or "").strip():
        return False
    return lead_score >= LEAD_THRESHOLD or expertise_score >= EXPERTISE_THRESHOLD


def format_alert(post: dict, result: dict, group_name: str) -> str:
    """HTML-formatted alert. Everything interpolated is escaped — an unescaped
    '<' or '&' from a post body makes Telegram reject the entire message."""
    emoji, label = PATH_LABELS.get(result.get("lead_path"), PATH_LABELS["none"])
    excerpt = html.escape((post.get("text") or "")[:EXCERPT_CHARS])
    answer = html.escape((result.get("answer") or "")[:ANSWER_CHARS])

    lines = [
        f"{emoji} <b>ליד {result.get('lead_score', 0)}</b> · מסלול: {label} · {html.escape(group_name)}",
        f"<i>expertise {result.get('score', 0)}</i>",
        "",
        f'<i>"{excerpt}"</i>',
    ]
    if answer:
        lines += ["", "👇 <b>התשובה המוצעת</b> (לחיצה מעתיקה):", f"<code>{answer}</code>"]
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_telegram_notify.py -v`
Expected: PASS, 10 passed

- [ ] **Step 5: Commit**

```bash
git add src/telegram_notify.py tests/test_telegram_notify.py
git commit -m "Telegram: format lead alerts with tap-to-copy answers

Answer goes in a <code> block because Telegram makes those tap-to-copy on
mobile. All interpolated text is HTML-escaped.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Send the alert

**Files:**
- Modify: `src/telegram_notify.py`
- Modify: `tests/test_telegram_notify.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_telegram_notify.py
from src.telegram_notify import send_alert


def test_send_returns_message_id(mocker):
    post = mocker.patch("src.telegram_notify.requests.post")
    post.return_value.status_code = 200
    post.return_value.json.return_value = {"ok": True, "result": {"message_id": 42}}

    mid = send_alert("tok", "123", "hello", "https://fb.com/p/1", "https://dash")
    assert mid == 42

    body = post.call_args.kwargs["json"]
    assert body["chat_id"] == "123"
    assert body["parse_mode"] == "HTML"
    buttons = body["reply_markup"]["inline_keyboard"][0]
    assert all("url" in b for b in buttons), "URL buttons only — no callbacks, no listener"


def test_send_failure_returns_none_and_does_not_raise(mocker):
    """A Telegram outage must never break the scrape or lose the sheet row."""
    post = mocker.patch("src.telegram_notify.requests.post")
    post.return_value.status_code = 403
    post.return_value.text = "bot can't initiate conversation"
    assert send_alert("tok", "123", "hi", "u", "d") is None


def test_send_network_error_returns_none(mocker):
    mocker.patch("src.telegram_notify.requests.post", side_effect=OSError("boom"))
    assert send_alert("tok", "123", "hi", "u", "d") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_telegram_notify.py -k send -v`
Expected: FAIL — `ImportError: cannot import name 'send_alert'`

- [ ] **Step 3: Write the implementation**

```python
# append to src/telegram_notify.py
def send_alert(token: str, chat_id: str, text: str,
               post_url: str, dashboard_url: str) -> int | None:
    """Send one alert. Returns the Telegram message_id, or None on any failure.

    Never raises: the sheet row is written regardless, and notified_at stays
    empty so the next run retries.
    """
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "reply_markup": {"inline_keyboard": [[
            {"text": "📄 לפוסט", "url": post_url},
            {"text": "📊 לדשבורד", "url": dashboard_url},
        ]]},
    }
    try:
        resp = requests.post(API.format(token=token, method="sendMessage"),
                             json=payload, timeout=20)
        if resp.status_code != 200:
            log.warning(f"Telegram sendMessage {resp.status_code}: {resp.text[:200]}")
            return None
        return resp.json().get("result", {}).get("message_id")
    except Exception as e:
        log.warning(f"Telegram send failed: {e}")
        return None
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_telegram_notify.py -v`
Expected: PASS, 13 passed

- [ ] **Step 5: Commit**

```bash
git add src/telegram_notify.py tests/test_telegram_notify.py
git commit -m "Telegram: send alerts, failing soft on any error

URL buttons only, so no listener process is needed. A send failure leaves
notified_at empty and the next run retries.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: Wire alerts into the run

**Files:**
- Modify: `src/community_monitor.py` (`run_monitor`)

- [ ] **Step 1: Add group-name lookup and the alert helper**

Add to `src/community_monitor.py`:

```python
from src import telegram_notify

GROUP_NAMES = {
    "1061644604326919": "הטאבון הביתי",
    "4432265433559920": "פיצה נפוליטנית",
    "2030269437295695": "אפייה ביתית",
    "587379969063560": "מחמצת ולחם",
    "695285311378525": "טאבון ופיצה",
    "hometabun": "Home Tabun",
    "2926500980956274": "נפלאות הטאבון",
}


def group_name(group_url: str) -> str:
    for key, name in GROUP_NAMES.items():
        if key in (group_url or ""):
            return name
    return "קבוצה"


def maybe_alert(post: dict, result: dict, cfg: dict) -> tuple[str, str]:
    """Send an alert if the post qualifies. Returns (notified_at, tg_message_id),
    both empty strings when nothing was sent."""
    if not cfg.get("telegram_token") or not cfg.get("telegram_chat_id"):
        return "", ""
    if not telegram_notify.should_notify(result["lead_score"], result["score"], ""):
        return "", ""

    text = telegram_notify.format_alert(post, result, group_name(post.get("facebookUrl", "")))
    mid = telegram_notify.send_alert(
        cfg["telegram_token"], cfg["telegram_chat_id"], text,
        post.get("url", ""), cfg["dashboard_url"])
    if mid is None:
        return "", ""
    log.info(f"Alerted lead={result['lead_score']} path={result['lead_path']} msg={mid}")
    return datetime.now().strftime("%d/%m/%Y %H:%M"), str(mid)
```

- [ ] **Step 2: Read the new config in run_monitor**

At the top of `run_monitor()`, alongside the existing `os.getenv` calls:

```python
    cfg = {
        "telegram_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
        "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID", ""),
        "dashboard_url": os.getenv("DASHBOARD_URL", "https://just-bake.streamlit.app/Community"),
        "healthcheck_url": os.getenv("HEALTHCHECK_URL", ""),
    }
```

Leave these out of the existing `if not all([...])` required-vars check — the scrape must still work if Telegram is unconfigured.

- [ ] **Step 3: Replace the new-post append with a header-keyed row plus alert**

Replace the `ws.append_row([...])` in the new-post branch with:

```python
            result = score_and_answer(post, claude)
            notified_at, tg_message_id = maybe_alert(post, result, cfg)

            ws.append_row(build_row({
                "date_fetched": datetime.now().strftime("%d/%m/%Y"),
                "group_url": post.get("facebookUrl", ""),
                "post_url": url,
                "post_author": post.get("user", {}).get("name", ""),
                "post_date": str(post.get("time", ""))[:10],
                "post_text": (post.get("text") or "")[:1000],
                "comments": comments_flat[:800],
                "answer": result.get("answer") or "",
                "score": result["score"],
                "score_reason": result["score_reason"],
                "tags": ", ".join(result["tags"]),
                "question_type": result["question_type"],
                "status": "pending",
                "image_url": post.get("image_url") or "",
                "image_description": result["image_description"],
                "post_type": result["post_type"],
                "lead_score": result["lead_score"],
                "lead_path": result["lead_path"],
                "notified_at": notified_at,
                "tg_message_id": tg_message_id,
            }))
            known_posts[url] = {"row": None, "comment_count": len(comments_flat)}
            saved += 1
```

- [ ] **Step 4: Verify it imports and all tests pass**

Run: `.venv/bin/python -m pytest -v && .venv/bin/python -c "import src.community_monitor; print('ok')"`
Expected: 21 passed, then `ok`

- [ ] **Step 5: Commit**

```bash
git add src/community_monitor.py
git commit -m "Community: send a Telegram alert when a post crosses the threshold

Alerts on lead_score >= 7 or expertise_score >= 9, roughly one a day. Records
notified_at and tg_message_id so a post is never alerted twice and replies can
be matched back to it.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 11: Templates and Facts tabs

**Files:**
- Create: `src/answer_templates.py`
- Create: `tests/test_answer_templates.py`
- Modify: `src/community_monitor.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_answer_templates.py
from src.answer_templates import render_guidance, TEMPLATE_ROWS


def test_all_four_paths_have_a_seed_template():
    for path in ("order", "mentoring", "professional", "event"):
        assert path in TEMPLATE_ROWS


def test_guidance_includes_templates_and_facts():
    out = render_guidance(
        templates={"order": "תבדוק גאוגרפיה, אז עובדות"},
        facts=["24 שעות = 3 גרם שמרים טריים לקילו"])
    assert "order" in out
    assert "3 גרם שמרים" in out


def test_guidance_is_empty_when_sheet_tabs_are_empty():
    assert render_guidance(templates={}, facts=[]) == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_answer_templates.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# src/answer_templates.py
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
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_answer_templates.py -v`
Expected: PASS, 3 passed

- [ ] **Step 5: Thread guidance into scoring**

Change `score_and_answer`'s signature to `def score_and_answer(post: dict, claude, guidance: str = "") -> dict:` and insert `{guidance}` into the prompt immediately above the `ענה בJSON בלבד` line.

In `run_monitor()`, after opening the spreadsheet, load once per run:

```python
    guidance = answer_templates.render_guidance(
        answer_templates.load_templates(spreadsheet),
        answer_templates.load_facts(spreadsheet))
```

and pass `guidance` at both `score_and_answer(post, claude)` call sites. Add `from src import answer_templates` to the imports.

- [ ] **Step 6: Run all tests**

Run: `.venv/bin/python -m pytest -v`
Expected: PASS, 24 passed

- [ ] **Step 7: Commit**

```bash
git add src/answer_templates.py tests/test_answer_templates.py src/community_monitor.py
git commit -m "Community: templates and facts live in Sheet tabs

Gilad edits wording and verified numbers from his phone with no deploy. Facts
exist because the model invented a W-value for gluten-free flour on a post
that scored 9.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Phase 5 — Monitoring

### Task 12: Healthcheck ping and daily summary

**Files:**
- Modify: `src/telegram_notify.py`
- Modify: `src/community_monitor.py`
- Modify: `tests/test_telegram_notify.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_telegram_notify.py
from src.telegram_notify import ping_healthcheck, send_plain


def test_ping_is_a_no_op_when_url_unset(mocker):
    get = mocker.patch("src.telegram_notify.requests.get")
    ping_healthcheck("")
    get.assert_not_called()


def test_ping_failure_is_swallowed(mocker):
    mocker.patch("src.telegram_notify.requests.get", side_effect=OSError("down"))
    ping_healthcheck("https://hc-ping.com/abc")  # must not raise


def test_ping_appends_fail_suffix(mocker):
    get = mocker.patch("src.telegram_notify.requests.get")
    ping_healthcheck("https://hc-ping.com/abc", suffix="/fail")
    assert get.call_args.args[0] == "https://hc-ping.com/abc/fail"


def test_send_plain_posts_text(mocker):
    post = mocker.patch("src.telegram_notify.requests.post")
    post.return_value.status_code = 200
    post.return_value.json.return_value = {"result": {"message_id": 7}}
    assert send_plain("tok", "1", "סיכום יומי") == 7
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_telegram_notify.py -k "ping or plain" -v`
Expected: FAIL — `ImportError: cannot import name 'ping_healthcheck'`

- [ ] **Step 3: Write the implementation**

```python
# append to src/telegram_notify.py
def ping_healthcheck(url: str, suffix: str = "") -> None:
    """Dead-man's switch ping. Silent no-op when unconfigured; never raises,
    because a monitoring failure must not fail the job it monitors."""
    if not url:
        return
    try:
        requests.get(url + suffix, timeout=10)
    except Exception as e:
        log.warning(f"Healthcheck ping failed: {e}")


def send_plain(token: str, chat_id: str, text: str) -> int | None:
    """Plain message with no buttons — used for the daily summary."""
    try:
        resp = requests.post(API.format(token=token, method="sendMessage"),
                             json={"chat_id": chat_id, "text": text}, timeout=20)
        if resp.status_code != 200:
            log.warning(f"Telegram sendMessage {resp.status_code}: {resp.text[:200]}")
            return None
        return resp.json().get("result", {}).get("message_id")
    except Exception as e:
        log.warning(f"Telegram send failed: {e}")
        return None
```

- [ ] **Step 4: Ping and summarise in run_monitor**

At the very end of `run_monitor()`, replace the closing `log.info(...)` and `return saved` with:

```python
    log.info(f"Done. Saved {saved} new posts, updated {updated} existing posts.")
    telegram_notify.ping_healthcheck(cfg["healthcheck_url"])

    # Last scheduled run of the day (20:00 UTC) sends the summary. Its absence
    # is the signal — see the dead-man's switch for the case where no run happens.
    if datetime.now(timezone.utc).hour >= 20 and cfg.get("telegram_token"):
        telegram_notify.send_plain(
            cfg["telegram_token"], cfg["telegram_chat_id"],
            f"📊 סיכום יום\nפוסטים חדשים: {saved}\nעודכנו: {updated}\nהתראות: {alerted}")
    return saved
```

Initialise `alerted = 0` next to `saved = updated = 0`, and increment it inside the new-post branch whenever `tg_message_id` is non-empty.

- [ ] **Step 5: Run all tests**

Run: `.venv/bin/python -m pytest -v`
Expected: PASS, 28 passed

- [ ] **Step 6: Commit**

```bash
git add src/telegram_notify.py src/community_monitor.py tests/test_telegram_notify.py
git commit -m "Community: healthcheck ping and daily summary

A 16-day outage went unnoticed in September because a dashboard with no new
rows looks like a quiet fortnight. Silence has to be distinguishable from
failure now that this drives alerts.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 13: Crash alert in the workflow

**Files:**
- Modify: `.github/workflows/community-monitor.yml`

- [ ] **Step 1: Replace the failure step**

Replace the existing `Upload logs on failure` step with:

```yaml
      - name: Alert on failure
        if: failure()
        run: |
          curl -s -X POST \
            "https://api.telegram.org/bot${{ secrets.TELEGRAM_BOT_TOKEN }}/sendMessage" \
            -d chat_id="${{ secrets.TELEGRAM_CHAT_ID }}" \
            -d text="⚠️ Community monitor נכשל. ריצה ${{ github.run_id }}"
          if [ -n "${{ secrets.HEALTHCHECK_URL }}" ]; then
            curl -s -m 10 "${{ secrets.HEALTHCHECK_URL }}/fail" || true
          fi

      - name: Upload logs on failure
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: community-monitor-logs
          path: "*.log"
          retention-days: 7
```

This step runs *because* the job failed, so it does not depend on the Python working — which is exactly the failure mode that went unnoticed for 16 days in September.

- [ ] **Step 2: Validate the YAML**

Run: `grep -c 'if: failure()' .github/workflows/community-monitor.yml`
Expected: `2` — one for the Telegram alert, one for the log upload.

- [ ] **Step 3: Trigger a manual run and confirm the alert path**

Run: `gh workflow run "Community Monitor" && sleep 90 && gh run list --workflow="Community Monitor" --limit 1`
Expected: a run appears. If it succeeds, a healthcheck ping lands; if it fails, a Telegram message arrives.

- [ ] **Step 4: Remind Gilad of the manual healthchecks edit**

The healthchecks.io check is still on `*/30 4-20 * * *`. It must be changed to `0 4,8,12,16,20 * * *` (UTC) or it will alarm every few hours. This cannot be done from code.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/community-monitor.yml
git commit -m "Community: Telegram alert when the workflow itself fails

Runs via if:failure() so it does not depend on our Python executing, which is
the failure mode that went unnoticed for 16 days.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Phase 6 — Reply channel

### Task 14: Drain replies safely

**Files:**
- Create: `src/sheet_meta.py`
- Modify: `src/telegram_notify.py`
- Modify: `tests/test_telegram_notify.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_telegram_notify.py
from src.telegram_notify import fetch_replies


def _update(uid, from_id, text, reply_to=None):
    msg = {"message_id": uid + 100, "from": {"id": from_id}, "text": text}
    if reply_to:
        msg["reply_to_message"] = {"message_id": reply_to}
    return {"update_id": uid, "message": msg}


def test_only_the_owner_chat_is_accepted(mocker):
    """The bot username is public — anyone can press Start and send messages."""
    get = mocker.patch("src.telegram_notify.requests.get")
    get.return_value.status_code = 200
    get.return_value.json.return_value = {"ok": True, "result": [
        _update(1, 314244953, "מהבעלים"),
        _update(2, 999999999, "/fact גבינה חינם"),
    ]}
    replies, next_offset = fetch_replies("tok", "314244953", 0)
    assert len(replies) == 1
    assert replies[0]["text"] == "מהבעלים"
    assert next_offset == 3, "offset must advance past ignored updates too"


def test_offset_unchanged_when_queue_is_empty(mocker):
    get = mocker.patch("src.telegram_notify.requests.get")
    get.return_value.status_code = 200
    get.return_value.json.return_value = {"ok": True, "result": []}
    replies, next_offset = fetch_replies("tok", "1", 57)
    assert replies == []
    assert next_offset == 57


def test_reply_target_is_extracted(mocker):
    get = mocker.patch("src.telegram_notify.requests.get")
    get.return_value.status_code = 200
    get.return_value.json.return_value = {"ok": True, "result": [
        _update(5, 314244953, "התשובה שלי", reply_to=42)]}
    replies, _ = fetch_replies("tok", "314244953", 0)
    assert replies[0]["reply_to"] == 42


def test_network_failure_returns_empty_and_keeps_offset(mocker):
    mocker.patch("src.telegram_notify.requests.get", side_effect=OSError("down"))
    replies, next_offset = fetch_replies("tok", "1", 12)
    assert replies == []
    assert next_offset == 12
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_telegram_notify.py -k replies -v`
Expected: FAIL — `ImportError: cannot import name 'fetch_replies'`

- [ ] **Step 3: Write the implementation**

```python
# append to src/telegram_notify.py
def fetch_replies(token: str, chat_id: str, offset: int) -> tuple[list, int]:
    """Drain queued updates. Returns (owner_messages, next_offset).

    Telegram queues updates for 24 hours, so a scheduled run is enough — no
    webhook and no always-on listener.

    from.id is set by Telegram's servers and cannot be spoofed by a sender, so
    the equality check below is the whole authorisation model. The offset
    advances past ignored updates too, otherwise a stranger's message would be
    re-fetched forever.
    """
    try:
        resp = requests.get(API.format(token=token, method="getUpdates"),
                            params={"offset": offset, "timeout": 0}, timeout=30)
        if resp.status_code != 200:
            log.warning(f"Telegram getUpdates {resp.status_code}: {resp.text[:200]}")
            return [], offset
        updates = resp.json().get("result", []) or []
    except Exception as e:
        log.warning(f"Telegram getUpdates failed: {e}")
        return [], offset

    if not updates:
        return [], offset

    owner = str(chat_id)
    replies = []
    for update in updates:
        msg = update.get("message") or {}
        if str((msg.get("from") or {}).get("id")) != owner:
            continue
        replies.append({
            "text": (msg.get("text") or "").strip(),
            "reply_to": (msg.get("reply_to_message") or {}).get("message_id"),
            "message_id": msg.get("message_id"),
        })

    next_offset = max(u["update_id"] for u in updates) + 1
    log.info(f"Drained {len(updates)} updates, {len(replies)} from owner")
    return replies, next_offset
```

- [ ] **Step 4: Write the offset store**

```python
# src/sheet_meta.py
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
```

- [ ] **Step 5: Run tests**

Run: `.venv/bin/python -m pytest -v`
Expected: PASS, 32 passed

- [ ] **Step 6: Commit**

```bash
git add src/telegram_notify.py src/sheet_meta.py tests/test_telegram_notify.py
git commit -m "Telegram: drain owner replies from the update queue

Telegram queues updates for 24h, so the scheduled run is enough and no
listener process is needed. from.id equality is the whole auth model; the
offset advances past ignored updates so strangers cannot wedge the queue.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 15: Act on replies, and acknowledge every one

**Files:**
- Modify: `src/community_monitor.py`
- Create: `tests/test_reply_actions.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_reply_actions.py
from src.community_monitor import classify_reply


def test_free_text_reply_to_an_alert_is_an_answer():
    out = classify_reply({"text": "היי מאיר, אם פתח תקווה בכיוון שלך", "reply_to": 42})
    assert out["kind"] == "answer"
    assert out["target"] == 42


def test_fact_command_is_extracted():
    out = classify_reply({"text": "/fact שמרים יבשים = שליש מהטריים", "reply_to": None})
    assert out["kind"] == "fact"
    assert out["payload"] == "שמרים יבשים = שליש מהטריים"


def test_template_command_names_its_path():
    out = classify_reply({"text": "/order תבדוק גאוגרפיה קודם", "reply_to": None})
    assert out["kind"] == "template"
    assert out["path"] == "order"
    assert out["payload"] == "תבדוק גאוגרפיה קודם"


def test_bad_marks_scoring_wrong():
    out = classify_reply({"text": "/bad", "reply_to": 42})
    assert out["kind"] == "bad"
    assert out["target"] == 42


def test_free_text_without_a_reply_target_is_ignored():
    out = classify_reply({"text": "סתם הודעה", "reply_to": None})
    assert out["kind"] == "ignored"


def test_empty_command_payload_is_ignored():
    assert classify_reply({"text": "/fact", "reply_to": None})["kind"] == "ignored"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_reply_actions.py -v`
Expected: FAIL — `ImportError: cannot import name 'classify_reply'`

- [ ] **Step 3: Write the classifier**

```python
# add to src/community_monitor.py
TEMPLATE_COMMANDS = {"/order": "order", "/mentoring": "mentoring",
                     "/event": "event", "/pro": "professional"}


def classify_reply(reply: dict) -> dict:
    """Turn a raw Telegram reply into an action. Never raises."""
    text = (reply.get("text") or "").strip()
    target = reply.get("reply_to")

    if not text:
        return {"kind": "ignored"}

    if text in ("/bad", "/skip"):
        return {"kind": "bad", "target": target} if target else {"kind": "ignored"}

    head, _, rest = text.partition(" ")
    payload = rest.strip()

    if head == "/fact":
        return {"kind": "fact", "payload": payload} if payload else {"kind": "ignored"}

    if head in TEMPLATE_COMMANDS:
        return ({"kind": "template", "path": TEMPLATE_COMMANDS[head], "payload": payload}
                if payload else {"kind": "ignored"})

    if text.startswith("/"):
        return {"kind": "ignored"}

    return {"kind": "answer", "target": target, "payload": text} if target else {"kind": "ignored"}
```

- [ ] **Step 4: Apply the actions in run_monitor**

Add to `src/community_monitor.py`:

```python
def apply_replies(spreadsheet, ws, cfg) -> int:
    """Drain and apply Telegram replies. Every processed reply is acknowledged —
    without an ack, a reply silently lost to Telegram's 24h expiry looks exactly
    like one that was saved."""
    if not cfg.get("telegram_token"):
        return 0

    offset = int(sheet_meta.get_meta(spreadsheet, "telegram_offset", "0") or 0)
    replies, next_offset = telegram_notify.fetch_replies(
        cfg["telegram_token"], cfg["telegram_chat_id"], offset)
    if next_offset != offset:
        sheet_meta.set_meta(spreadsheet, "telegram_offset", next_offset)

    rows = ws.get_all_values()
    by_msg_id = {}
    for i, row in enumerate(rows[1:], start=2):
        data = row_to_dict(row)
        if data.get("tg_message_id"):
            by_msg_id[str(data["tg_message_id"])] = i

    applied = 0
    for reply in replies:
        action = classify_reply(reply)
        kind = action["kind"]
        ack = None

        if kind == "answer":
            row_num = by_msg_id.get(str(action["target"]))
            if row_num:
                ws.update_cell(row_num, COMMUNITY_HEADERS.index("my_answer") + 1, action["payload"])
                ws.update_cell(row_num, COMMUNITY_HEADERS.index("status") + 1, "posted")
                ack = "✅ נשמר כתשובה שלך, והפוסט סומן כפורסם"
            else:
                ack = "⚠️ לא מצאתי את הפוסט שהגבת עליו"

        elif kind == "bad":
            row_num = by_msg_id.get(str(action["target"]))
            if row_num:
                ws.update_cell(row_num, COMMUNITY_HEADERS.index("status") + 1, "bad_score")
                ack = "✅ סומן כניקוד שגוי"

        elif kind == "fact":
            spreadsheet.worksheet(answer_templates.FACTS_SHEET).append_row([action["payload"]])
            ack = f"✅ נוסף לעובדות: {action['payload'][:60]}"

        elif kind == "template":
            answer_templates.update_template(spreadsheet, action["path"], action["payload"])
            ack = f"✅ תבנית {action['path']} עודכנה: {action['payload'][:60]}"

        if ack:
            telegram_notify.send_plain(cfg["telegram_token"], cfg["telegram_chat_id"], ack)
            applied += 1

    if applied:
        log.info(f"Applied {applied} Telegram replies")
    return applied
```

Add `from src import sheet_meta` and `from src.sheet_rows import row_to_dict` to the imports, and call `apply_replies(spreadsheet, ws, cfg)` in `run_monitor()` immediately after `known_posts` is loaded and before `fetch_posts`.

- [ ] **Step 5: Add the template updater with history**

```python
# append to src/answer_templates.py
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
```

- [ ] **Step 6: Run all tests**

Run: `.venv/bin/python -m pytest -v`
Expected: PASS, 38 passed

- [ ] **Step 7: Commit**

```bash
git add src/community_monitor.py src/answer_templates.py tests/test_reply_actions.py
git commit -m "Community: ingest Telegram replies into the voice training set

The my_answer loop from f2313b1 has sat at 2 of the 10 answers it needs since
July, because feeding it meant opening the dashboard. Replying to an alert now
saves the answer, and /fact and /order edit the Sheet tabs from the phone.
Every processed reply is acknowledged so a silent loss is visible.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 16: End-to-end verification and cleanup

**Files:**
- Delete: `scripts/score_dryrun.py`

- [ ] **Step 1: Run the full suite**

Run: `.venv/bin/python -m pytest -v`
Expected: PASS, 38 passed

- [ ] **Step 2: Trigger a real run**

Run: `gh workflow run "Community Monitor"` then `gh run watch`
Expected: SUCCEEDED. Check: healthchecks.io shows a fresh ping; the `Community` sheet has new rows with `lead_score`/`lead_path` populated; `Templates`, `Facts` and `Meta` tabs now exist.

- [ ] **Step 3: Verify the reply loop by hand**

Reply to any alert in Telegram with `/fact בדיקה`.
Trigger another run: `gh workflow run "Community Monitor"`.
Expected: a `✅ נוסף לעובדות: בדיקה` message arrives, and the row appears in the `Facts` tab. Then delete that test row from the sheet.

- [ ] **Step 4: Check the Apify spend**

Run: `.venv/bin/python -c "
import json,os,urllib.request
from dotenv import load_dotenv; load_dotenv()
r=urllib.request.Request('https://api.apify.com/v2/users/me/usage/monthly',
  headers={'Authorization':'Bearer '+os.getenv('APIFY_API_TOKEN')})
print('usage: \$%.4f' % json.load(urllib.request.urlopen(r))['data']['totalUsageCreditsUsdBeforeVolumeDiscount'])"`

Expected: the per-run delta is well under $0.05. If a single run costs more than $0.05, reduce `POSTS_PER_GROUP` before leaving the schedule enabled.

- [ ] **Step 5: Delete the temp script**

```bash
rm scripts/score_dryrun.py
rmdir scripts 2>/dev/null || true
```

- [ ] **Step 6: Commit**

```bash
git add -A src tests docs .github pytest.ini
git commit -m "Community: remove scoring dry-run script after verification

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Self-review notes

**Spec coverage check:**

| Spec section | Task |
|---|---|
| §4 two-axis scoring | 3, 4, 5 |
| §4.1 three gates | 4 (prompt), 5 (verified against real posts) |
| §4.4 alert rule | 8 |
| §5 templates + §5.1 voice rules | 4 (prompt rules), 11 (Sheet storage) |
| §6 facts table | 11 |
| §7 Telegram, dedup, failure behaviour | 8, 9, 10 |
| §8 cadence, `onlyPostsNewerThan`, ISO timestamp | 6, 7 |
| §9 three monitoring layers | 12 (ping + summary), 13 (crash alert) |
| §10 schema changes | 1 (columns), 11 (tabs), 14 (`Meta` tab) |
| §11 noise column bug | 2 |
| §12 testing | every task |
| §13 risks — never auto-post | No task posts to Facebook anywhere in this plan |
| §15 reply channel | 14, 15 |
| §15.3 concurrency, offset, ack, history | 7, 14, 15 |

**Not covered by code, tracked as manual items:** the healthchecks.io cron edit (Task 13 Step 4), and Gilad's remaining §6.2 facts — which are now answerable via `/fact` from his phone rather than needing a task.

**Naming consistency verified:** `build_row`/`row_to_dict` (`sheet_rows`), `format_alert`/`send_alert`/`send_plain`/`should_notify`/`ping_healthcheck`/`fetch_replies` (`telegram_notify`), `load_templates`/`load_facts`/`render_guidance`/`update_template` (`answer_templates`), `get_meta`/`set_meta` (`sheet_meta`), `parse_score_response`/`classify_reply`/`maybe_alert`/`apply_replies`/`build_run_input`/`build_noise_row`/`group_name` (`community_monitor`). Every name used in a later task is defined in an earlier one.

# just-bake voice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One `voice/` folder in this repo that both the community bot (GitHub Actions) and a Claude Code skill read, so drafts sound like Gilad and learn from his Telegram replies.

**Architecture:** A new `src/voice.py` loads `voice/` (rules, examples, canned answers), picks random same-situation examples, and writes a plain-text draft in a second Claude call. `community_monitor.py` keeps scoring (JSON, no answer), calls the writer only for posts that alert, and syncs `my_answer` rows back into `voice/examples.jsonl`, which the workflow commits.

**Tech Stack:** Python 3.11, anthropic SDK, gspread, pytest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-30-just-bake-voice-design.md`

**Seed data (outside the repo):** `~/Projects/just-bake-content/voice/`:
`corpus_fb_comments.json`, `review_decisions.jsonl`, `sheet_pairs.jsonl`, `rewrites/`, `corpus_fb_posts.json`.

**Run tests with:** `.venv/bin/python -m pytest` (59 tests pass at start).

---

## File map

| File | Responsibility |
|---|---|
| `voice/voice.md` (new) | Rules + glossary, Hebrew, each rule with its source |
| `voice/examples.jsonl` (new, generated) | Gilad's real texts, one JSON per line |
| `voice/canned.md` (new) | Verbatim answers (2 recipes) |
| `voice/hooks.md` (new) | Post openings that are his (Claude Code skill only) |
| `voice/rewrites/` (new) | Draft→final records |
| `tools/seed_voice.py` (new) | One-time builder of `examples.jsonl` from the seed data |
| `src/voice.py` (new) | Load voice, select examples, build messages, write draft, learn from Sheet rows |
| `src/community_monitor.py` | Scoring without answer; call writer; sync learned examples |
| `src/sheet_rows.py` | Add `situation` column |
| `src/telegram_notify.py` | Show draft warning in alert |
| `.github/workflows/community-monitor.yml` | Commit learned examples |
| `tools/voice_eval.py` (new) | Side-by-side eval on real pairs |
| `~/.claude/skills/just-bake-voice/SKILL.md` (new, outside repo) | Claude Code skill |
| `~/.claude/brand-kits/just-bake/brand.json` (outside repo) | Voice shrinks to a pointer |

---

### Task 1: Hand-written voice files

**Files:**
- Create: `voice/voice.md`, `voice/canned.md`, `voice/hooks.md`, `voice/rewrites/2026-09-30_em_hamoshavot_simchat_torah.md`

- [ ] **Step 1: Create `voice/voice.md`**

```markdown
# הקול של גלעד

כל כלל כאן בא מתיקון של גלעד או ממה שרואים בתגובות שלו. המקור בסוגריים.

## איך גלעד כותב

- קצר. לרוב שורה אחת או שתיים, לפעמים מילה אחת ("תקין."). לא להוסיף שורות רק כדי להסביר. (123 תגובות בפייסבוק)
- עונים על מה שנשאל. שאלו איפה קונים, עונים איפה, לא מה זה. (גלעד, 30/09/2026, קמח סמולה)
- תשובה טכנית בגוף רבים סתמי: "מדליקים", "בודקים", "מורידים את האש", "חשוב לא להתבלבל". לא ציווי בגוף שני ("תדליק", "תן"). (גלעד, 30/09/2026)
- כשחסר מידע לאבחון, לא עונים רק בשאלה. מפצלים: "אם עבר X זמן אז ככה, אחרת ככה" או "עבר את המבחן? ככה. לא עבר? ככה." (גלעד, 30/09/2026)
- כשמציעים משהו, שורה אחת: איפה הוא + הזמנה. למשל "אני מפתח תקוה ומוכר כדורי בצק, מוזמן לשלוח הודעה". הזמנה לשלוח הודעה או להגיע היא בסדר. (תגובות בפייסבוק)
- כשיש אינטרס, אומרים אותו בגלוי: "גילוי נאות - אני מעביר סדנאות", "בלי שמץ של פרסום". (תגובות בפייסבוק)
- כשלא בטוחים, אומרים: "לדעתי", "אם אני לא טועה", "אל תתפוס אותי במילה". (תגובות בפייסבוק)
- אימוג'י בסדר, לרוב כפול: 🍕🍕, 🙏🏼. ":)" גם בסדר. (תגובות בפייסבוק)
- בלי מקף ארוך (— או –) בשום מקום, רק פסיק או מקף רגיל, גם בטווחים: 350-450. (brand.json)
- לא להעתיק מחיר מדוגמה. מחירים רק מהעובדות, ואם אין שם מחיר, בלי מחיר. (גלעד, 30/09/2026)
- לא לחזור על אותו ניסוח. אנשים בקבוצה רואים את כל התגובות, ותשובה בניסוח אחד חושפת שזה לא הוא. (גלעד, 30/09/2026)
- לא לענות לבקשה כללית בלי בעיה ספציפית ("טיפים לפעם ראשונה"). (גלעד, 30/09/2026)

## מה לא לכתוב

- משפטים מקבילים עם ריתמוס ("רגע אחרי X, רגע לפני Y"), שאלות רטוריות ("ומה יותר כיף מ...?"), "לא רק X אלא גם Y". (brand.json)
- איומים על התוצאה ("אחרת תקבל תוצאה מבאסת"), פתיחות כמו "איזה כיף, טאבון חדש!". (השוואה לתשובות של גלעד, 30/09/2026)
- מונחים באנגלית כשיש מילה שגלעד משתמש בה (cornicione → שוליים). (השוואה לתשובות של גלעד)
- להזכיר מגיבים אחרים בשם ("Nathan צודק"). (השוואה לתשובות של גלעד)

## לקהל של שכנים (פוסטים בשכונה, לא קבוצות טאבון)

- "48 שעות התפחה" זה לאופים. לשכנים מדברים על מה שהם מקבלים: חוסך זמן, כיף עם הילדים, טרי. (גלעד, 30/09/2026)
- בלי שורת מפרט טלגרפית ("בצק נפוליטני בהתפחה של 48 שעות, לתנור ביתי או טאבון. טרי או קפוא."). מדברים על המוצר בגוף ראשון כמו לשכן. (גלעד, 30/09/2026: "זה הטון שלך ולא שלי")
- שורה אחת על המוצר, לא כמה שורות הרגעה אחת אחרי השנייה. (גלעד, 30/09/2026: "יש פה יותר מדי")
- לסיים בצעד הבא של הקורא: "לכם נשאר רק להזמין ולאפות". (גלעד, 30/09/2026)
- בצק מהפריזר לא נכנס ישר לתנור, צריך שעות הפשרה. לא להבטיח פיצה מיידית. (brand.json)
- המוצר נקרא מארז או ערכה, אף פעם לא קופסאות. (brand.json)

## מונחים

שמרים (לא שמיר), ביגה, פוליש, אוטוליז, מחמצת, הידרציה, קמח 00, קמח כוסמין, טאבון, כדור בצק (לא גוש), פתיחת בצק (לא מתיחה), חלון גלוטן, קיפולים, סמולינה/קמח סמולה (חיטת דורום, לא סולת טחונה).
```

- [ ] **Step 2: Create `voice/canned.md`**

Format: `## <name>`, then a `when:` line, a blank line, then the text pasted verbatim.

```markdown
# תשובות קבועות

תשובות שגלעד מדביק כמו שהן. הבוט מחזיר את הטקסט בלי לשנות אותו.

## recipe_48h
when: מבקשים מתכון לבצק פיצה נפוליטנית, 48 או 72 שעות, קמח פיצה או קאפוטו

מתכון קל ופשוט לבצק פיצה:
1000 גרם קמח פיצה
660 גרם מים
28 גרם מלח
2 גרם שמרים טריים

אופן ההכנה:
לשים בקערה את הקמח והמים ולערבב יחד רק עד לאיחוד (דקה במיקסר). להעביר למקרר למנוחה של 30-60 דקות. להוסיף שמרים וללוש 5 דקות. להוסיף את המלח וללוש עוד 5-10 דקות עד שמתקבל בצק חלק.

להשאיר בטמפרטורת החדר כשעתיים (בקיץ מספיקה שעה), ואז למקרר ל-48 שעות.

להוציא מהמקרר, לחלק לכדורים במשקל 250 גרם, לכדרר ולהתפיח בטמפרטורת החדר עד הכפלת הנפח (בחורף זה יכול לקחת 5 שעות, בקיץ שעה וחצי שעתיים).

## recipe_24h_bread_flour
when: מבקשים מתכון פשוט ל-24 שעות, או עם קמח לחם רגיל ולא קמח פיצה

1000 גרם קמח לחם
600 גרם מים
3 גרם שמרים טריים
30 גרם מלח 
20 גרם שמן זית 
20 גרם סוכר

לישה איטית במיקסר למשך כ10-12 דקות
שעה מנוחה בטמפ' החדר
כדרור לכדורים ולמקרר למשך 24 שעות. 

אחרי 24 שעות התפחה בטמפ' החדר למשך שעתיים שלוש. 
```

Before saving, copy the second recipe's text exactly from `~/Projects/just-bake-content/voice/corpus_fb_comments.json` entry `"id": 1` (keep trailing spaces as in the source).

- [ ] **Step 3: Create `voice/hooks.md`**

```markdown
# פתיחות לפוסטים

פתיחות ורעיונות שגלעד סימן כשלו (30/09/2026). רק לסקיל just-bake-voice בזמן כתיבת פוסט.
לא להעתיק מילה במילה, לקחת את הצורה: רגע שכולם בשכונה חיים עכשיו, בגוף ראשון.

- דני רופ הבטיח גשם, אני מבטיח ריח של פיצה בבית 🌧️🍕
- ריח של גשם בחוץ וריח של פיצה בבית 🌧️🍕
- שכנים יקרים! בשנתיים האחרונות, מאז שהמלחמה התחילה, הבצקים והפיצות שלי הפכו לחלק מהנוף אצלנו בשכונה. ועכשיו אני מתרגש ברמות של חלה… (טוב, בעצם פיצה 🍕)
- טיסה לנאפולי: 600$ ✈️ הבצק שלנו: 12 ₪ 🍕 לכדור תעשו את החשבון! 😉
- האמת? רוב האנשים שמגיעים אליי לסדנה מגיעים לחוצים.
- לבן שלי גילו צליאק, ומאז הבצק ללא גלוטן שאני מכין הפסיק להיות עוד שורה במחירון, זו הפיצה שהילד שלי אוכל.
- ראש השנה זה לא בדיוק חג של פיצה, נכון.
- יום העצמאות עבר 🇮🇱 אכלנו בשר, הרבה בשר.
- איך נגמרו הבצקים?? זאת שאלה שלא תשאלו את עצמכם כשתזמינו ממני 🍕
- חברים יקרים! לבקשת הקהל, המבצע ימשיך גם השבוע 🫶🏼🍕🍕
- שמחת תורה בסופש, ואיתו נגמרים גם מחירי החג 🍕 (פוסט שגלעד אישר, 30/09/2026)

## מבנה שעובד

שורה או שתיים של רגע אמיתי, שורה אחת על המוצר בגוף ראשון, מחירים, איסוף וטלפון. בלי "על מה מדובר?", בלי בולטים של אימוג'י.

## אירועים שגלעד כותב עליהם

חגים (ראש השנה, סוכות, שמחת תורה, פסח, יום העצמאות, ל"ג בעומר, שבועות), גשם וחורף, מונדיאל, תחילת שנת לימודים, חופש גדול, בלאק פריידי, סדנאות, מוצר חדש (קלצונה שוקולד, ללא גלוטן).
```

- [ ] **Step 4: Copy the rewrite record**

```bash
mkdir -p voice/rewrites
cp ~/Projects/just-bake-content/voice/rewrites/2026-09-30_em_hamoshavot_simchat_torah.md voice/rewrites/
```

- [ ] **Step 5: Commit**

```bash
git add voice/voice.md voice/canned.md voice/hooks.md voice/rewrites/
git commit -m "voice: rules, canned answers and hooks"
```

---

### Task 2: `src/voice.py` loading

**Files:**
- Create: `src/voice.py`
- Test: `tests/test_voice.py`

- [ ] **Step 1: Write the failing tests**

```python
import json

from src.voice import load_voice, parse_canned


def _write_voice(tmp_path, examples, rules="כלל אחד", canned="## recipe\nwhen: מתכון\n\nטקסט"):
    (tmp_path / "voice.md").write_text(rules, encoding="utf-8")
    (tmp_path / "examples.jsonl").write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in examples), encoding="utf-8")
    (tmp_path / "canned.md").write_text(canned, encoding="utf-8")
    return tmp_path


def test_loads_rules_examples_and_canned(tmp_path):
    path = _write_voice(tmp_path, [{"situation": "tech_answer", "text": "תקין."}])
    voice = load_voice(path)
    assert voice.rules == "כלל אחד"
    assert voice.examples[0]["text"] == "תקין."
    assert voice.canned["recipe"]["text"] == "טקסט"


def test_missing_folder_returns_none(tmp_path):
    assert load_voice(tmp_path / "nope") is None


def test_empty_rules_returns_none(tmp_path):
    assert load_voice(_write_voice(tmp_path, [], rules="  ")) is None


def test_canned_keeps_text_verbatim_and_reads_when():
    md = "# title\n\n## recipe_48h\nwhen: מבקשים מתכון\n\n1000 גרם קמח\n660 גרם מים\n\n## other\nwhen: x\n\ny"
    canned = parse_canned(md)
    assert canned["recipe_48h"] == {"when": "מבקשים מתכון", "text": "1000 גרם קמח\n660 גרם מים"}
    assert canned["other"]["text"] == "y"
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_voice.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.voice'`

- [ ] **Step 3: Implement**

```python
"""Gilad's voice: the one place both the bot and Claude Code read.

Loads voice/ (rules, examples, canned answers), picks examples for a post and
writes a draft. No Sheets or Apify imports -- rows come in as plain dicts.
"""

import json
import logging
import random
import re
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

VOICE_DIR = Path(__file__).resolve().parent.parent / "voice"


@dataclass
class Voice:
    rules: str
    examples: list
    canned: dict  # name -> {"when": str, "text": str}


def parse_canned(md: str) -> dict:
    """Sections are '## name', an optional 'when:' line, then the verbatim text."""
    out = {}
    for block in re.split(r"^## ", md, flags=re.M)[1:]:
        head, _, body = block.partition("\n")
        lines = body.strip("\n").split("\n")
        when = ""
        if lines and lines[0].startswith("when:"):
            when = lines.pop(0)[len("when:"):].strip()
        text = "\n".join(lines).strip()
        if head.strip() and text:
            out[head.strip()] = {"when": when, "text": text}
    return out


def load_voice(path: Path = VOICE_DIR) -> "Voice | None":
    """None when the folder is missing or broken. The caller still alerts,
    just without a draft -- a lead must never be dropped over a voice file."""
    try:
        rules = (path / "voice.md").read_text(encoding="utf-8").strip()
        examples = [json.loads(line) for line in
                    (path / "examples.jsonl").read_text(encoding="utf-8").splitlines()
                    if line.strip()]
        canned = parse_canned((path / "canned.md").read_text(encoding="utf-8"))
    except Exception as e:
        log.warning(f"Voice folder unusable ({e})")
        return None
    if not rules:
        log.warning("voice.md is empty")
        return None
    return Voice(rules=rules, examples=examples, canned=canned)
```

(`random` is used in Task 3.)

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_voice.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/voice.py tests/test_voice.py
git commit -m "voice: load rules, examples and canned answers"
```

---

### Task 3: Example selection

**Files:**
- Modify: `src/voice.py`
- Test: `tests/test_voice.py`

- [ ] **Step 1: Write the failing tests** (append to `tests/test_voice.py`)

```python
from src.voice import select_examples


def _ex(i, situation="tech_answer", audience="taboon_group", **kw):
    return {"id": f"e{i}", "situation": situation, "audience": audience, "text": f"t{i}", **kw}


def test_picks_only_matching_situation():
    examples = [_ex(1), _ex(2, situation="lead_order")]
    assert [e["id"] for e in select_examples(examples, "tech_answer", "taboon_group", "seed")] == ["e1"]


def test_same_audience_first_then_fallback():
    examples = [_ex(1), _ex(2, audience="neighborhood"), _ex(3, audience="neighborhood")]
    picked = select_examples(examples, "tech_answer", "taboon_group", "seed", k=2)
    assert picked[0]["id"] == "e1"
    assert len(picked) == 2


def test_skips_null_text_ignored_and_not_bot_use():
    examples = [_ex(1, text=None), _ex(2, ignored=True), _ex(3, bot_use=False), _ex(4)]
    assert [e["id"] for e in select_examples(examples, "tech_answer", "taboon_group", "s")] == ["e4"]


def test_same_seed_same_pick_different_seed_varies():
    examples = [_ex(i) for i in range(12)]
    a = select_examples(examples, "tech_answer", "taboon_group", "post-A", k=4)
    assert a == select_examples(examples, "tech_answer", "taboon_group", "post-A", k=4)
    picks = {tuple(e["id"] for e in select_examples(examples, "tech_answer", "taboon_group", f"p{i}", k=4))
             for i in range(10)}
    assert len(picks) > 1  # variety is a hard requirement
```

`_ex(1, text=None)` overrides `text` because `**kw` comes last in the dict literal.

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_voice.py -v`
Expected: FAIL with `ImportError: cannot import name 'select_examples'`

- [ ] **Step 3: Implement** (append to `src/voice.py`)

```python
EXAMPLES_PER_DRAFT = 4


def _usable(example: dict, situation: str) -> bool:
    return (example.get("situation") == situation
            and bool(example.get("text"))
            and example.get("bot_use", True)
            and not example.get("ignored"))


def select_examples(examples: list, situation: str, audience: str, seed: str,
                    k: int = EXAMPLES_PER_DRAFT) -> list:
    """Random, not newest-first: different examples each time is what keeps the
    drafts from repeating one phrasing. Seeded by the post URL so a given post
    always gets the same examples (reproducible tests and reruns)."""
    usable = [e for e in examples if _usable(e, situation)]
    same = [e for e in usable if e.get("audience") == audience]
    others = [e for e in usable if e.get("audience") != audience]
    rng = random.Random(seed)
    picked = rng.sample(same, min(k, len(same)))
    picked += rng.sample(others, min(k - len(picked), len(others)))
    return picked
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_voice.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add src/voice.py tests/test_voice.py
git commit -m "voice: random same-situation example selection"
```

---

### Task 4: Messages and draft writing

**Files:**
- Modify: `src/voice.py`
- Test: `tests/test_voice.py`

- [ ] **Step 1: Write the failing tests** (append)

```python
from types import SimpleNamespace

from src.voice import Voice, build_messages, write_reply


class FakeClaude:
    def __init__(self, text="טיוטה", fail=False):
        self.text, self.fail, self.calls = text, fail, []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("boom")
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self.text)])


def _voice(examples=None, canned=None):
    return Voice(rules="כללים", examples=examples or [], canned=canned or {})


def test_examples_become_alternating_turns_then_the_post():
    ex = [_ex(1, context="שאלה 1"), _ex(2, context="")]
    system, messages = build_messages(_voice(), "הפוסט", ex, recent=[], facts=[])
    assert [m["role"] for m in messages] == ["user", "assistant", "user", "assistant", "user"]
    assert messages[0]["content"] == "שאלה 1"
    assert messages[1]["content"] == "t1"
    assert messages[2]["content"] == "(tech_answer)"   # empty context falls back to the situation
    assert messages[-1]["content"] == "הפוסט"
    assert "כללים" in system


def test_recent_and_facts_go_into_system():
    system, _ = build_messages(_voice(), "p", [], recent=["מוזמן אליי לפתח תקווה"], facts=["כדור 300 גרם"])
    assert "מוזמן אליי לפתח תקווה" in system
    assert "כדור 300 גרם" in system


def test_canned_is_returned_verbatim_without_calling_claude():
    claude = FakeClaude()
    voice = _voice(canned={"recipe_48h": {"when": "", "text": "1000 גרם קמח"}})
    draft, warning = write_reply("p", "tech_answer", "taboon_group", "recipe_48h", voice, claude, "s")
    assert draft == "1000 גרם קמח" and warning is None
    assert claude.calls == []


def test_no_answer_situation_gives_no_draft():
    draft, warning = write_reply("p", "no_answer", "taboon_group", None, _voice(), FakeClaude(), "s")
    assert draft is None and warning is None


def test_missing_voice_warns():
    draft, warning = write_reply("p", "tech_answer", "taboon_group", None, None, FakeClaude(), "s")
    assert draft is None and "בלי קול" in warning


def test_few_examples_warns_but_still_drafts():
    draft, warning = write_reply("p", "tech_answer", "taboon_group", None, _voice([_ex(1)]), FakeClaude(), "s")
    assert draft == "טיוטה"
    assert "אין דוגמאות" in warning


def test_enough_examples_no_warning():
    draft, warning = write_reply("p", "tech_answer", "taboon_group", None,
                                 _voice([_ex(1), _ex(2), _ex(3)]), FakeClaude(), "s")
    assert draft == "טיוטה" and warning is None


def test_claude_error_warns_and_never_raises():
    draft, warning = write_reply("p", "tech_answer", "taboon_group", None,
                                 _voice([_ex(1), _ex(2)]), FakeClaude(fail=True), "s")
    assert draft is None and "נכשל" in warning
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_voice.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_messages'`

- [ ] **Step 3: Implement** (append to `src/voice.py`)

```python
MIN_EXAMPLES = 2
WRITER_MODEL = "claude-sonnet-5"

# Plain Hebrew on purpose: the prompt's style leaks into the output.
WRITER_INTRO = ("אתה כותב תגובה בפייסבוק בשם גלעד מ\"פשוט לאפות\", שמוכר בצק לפיצה בפתח תקווה. "
                "כתוב בדיוק כמו התשובות הקודמות שלו בשיחה הזאת: אותו אורך, אותן מילים, אותו גוף. "
                "תחזיר רק את טקסט התגובה.")


def build_messages(voice: Voice, post_text: str, examples: list,
                   recent: list, facts: list) -> tuple:
    """Examples as past turns (post -> Gilad's reply), then the real post.
    Continuing a conversation where the model already 'is' Gilad beats asking
    it to imitate him."""
    system = WRITER_INTRO + "\n\n" + voice.rules
    if facts:
        system += "\n\nעובדות. מספרים רק מכאן, ואם אין מספר מתאים, בלי מספר:\n"
        system += "\n".join(f"- {f}" for f in facts)
    if recent:
        system += "\n\nכבר נכתב בקבוצה הזאת לאחרונה. לא לחזור על הפתיחות או הביטויים האלה:\n"
        system += "\n".join(f"- {r[:200]}" for r in recent)
    messages = []
    for e in examples:
        messages.append({"role": "user", "content": e.get("context") or f"({e['situation']})"})
        messages.append({"role": "assistant", "content": e["text"]})
    messages.append({"role": "user", "content": post_text})
    return system, messages


def write_reply(post_text: str, situation: str, audience: str, canned_name,
                voice, claude, seed: str, recent=(), facts=()) -> tuple:
    """Returns (draft or None, warning or None). Never raises: the alert goes
    out either way, the draft is a bonus."""
    if voice is None:
        return None, "⚠️ בלי קול, אין טיוטה"
    if canned_name and canned_name in voice.canned:
        return voice.canned[canned_name]["text"], None
    if situation == "no_answer":
        return None, None

    examples = select_examples(voice.examples, situation, audience, seed)
    warning = "⚠️ אין דוגמאות למצב הזה, הטיוטה ניחוש" if len(examples) < MIN_EXAMPLES else None
    system, messages = build_messages(voice, post_text, examples, list(recent), list(facts))
    try:
        resp = claude.messages.create(model=WRITER_MODEL, max_tokens=800,
                                      system=system, messages=messages)
        text = next((b.text for b in resp.content if b.type == "text"), "").strip()
    except Exception as e:
        log.warning(f"Draft writing failed: {e}")
        return None, "⚠️ כתיבת הטיוטה נכשלה"
    return (text or None), warning
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_voice.py -v`
Expected: 16 passed

- [ ] **Step 5: Commit**

```bash
git add src/voice.py tests/test_voice.py
git commit -m "voice: write drafts from examples as past turns"
```

---

### Task 5: Learning from Sheet rows

**Files:**
- Modify: `src/voice.py`, `src/sheet_rows.py:8-15`
- Test: `tests/test_voice.py`

- [ ] **Step 1: Write the failing tests** (append)

```python
from src.voice import learned_examples, append_examples, recent_group_replies


def _row(url, my_answer, **kw):
    base = {"post_url": url, "my_answer": my_answer, "post_text": "הפוסט", "group_url": "g1",
            "lead_path": "order", "situation": "", "posted_date": "", "date_fetched": "30/09/2026",
            "answer": ""}
    return {**base, **kw}


def test_new_my_answer_becomes_telegram_example():
    new = learned_examples([_row("u1", "מוזמן אליי")], known_urls=set())
    assert new == [{"id": "tg-u1", "situation": "lead_order", "audience": "taboon_group",
                    "context": "הפוסט", "text": "מוזמן אליי", "source": "telegram",
                    "date": "30/09/2026", "post_url": "u1", "bot_use": True}]


def test_known_url_and_empty_answer_are_skipped():
    rows = [_row("u1", "x"), _row("u2", "  ")]
    assert learned_examples(rows, known_urls={"u1"}) == []


def test_situation_column_wins_over_lead_path():
    new = learned_examples([_row("u1", "x", situation="where_to_buy")], known_urls=set())
    assert new[0]["situation"] == "where_to_buy"


def test_same_url_twice_in_rows_is_learned_once():
    assert len(learned_examples([_row("u1", "a"), _row("u1", "a")], known_urls=set())) == 1


def test_append_writes_jsonl(tmp_path):
    path = tmp_path / "examples.jsonl"
    path.write_text('{"id": "old"}\n', encoding="utf-8")
    append_examples(path, [{"id": "new", "text": "שלום"}])
    lines = path.read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[1]) == {"id": "new", "text": "שלום"}


def test_recent_group_replies_prefers_gilads_text_and_limits():
    rows = [_row(f"u{i}", "", group_url="g1", answer=f"a{i}") for i in range(15)]
    rows.append(_row("mine", "שלי", group_url="g1", answer="בוט"))
    rows.append(_row("other", "", group_url="g2", answer="אחר"))
    recent = recent_group_replies(rows, "g1", n=10)
    assert recent[0] == "שלי"
    assert len(recent) == 10
    assert "אחר" not in recent
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_voice.py -v`
Expected: FAIL with `ImportError: cannot import name 'learned_examples'`

- [ ] **Step 3: Add the `situation` column** in `src/sheet_rows.py`, after `"tg_message_id",`:

```python
    "lead_score", "lead_path", "notified_at", "tg_message_id",
    # added 30/09/2026 — voice
    "situation",
]
```

`get_or_create_community_sheet` already widens the sheet and rewrites the header row when `COMMUNITY_HEADERS` changes.

- [ ] **Step 4: Implement** (append to `src/voice.py`)

```python
# Used when a row predates the situation column.
LEAD_PATH_SITUATION = {"order": "lead_order", "event": "lead_order",
                       "mentoring": "tech_answer", "professional": "tech_answer"}
BOT_SITUATIONS = {"lead_order", "lead_workshop", "tech_answer", "where_to_buy",
                  "move_to_dm", "no_answer"}
RECENT_PER_GROUP = 10


def audience_for(group_url: str) -> str:
    """All monitored groups are taboon/pizza groups. Neighborhood and celiac
    audiences only exist in the Claude Code skill."""
    return "taboon_group"


def learned_examples(rows: list, known_urls: set) -> list:
    """Every Gilad reply in the Sheet that is not yet an example. Idempotent:
    if last run's push failed, the row is simply learned again."""
    new = []
    seen = set(known_urls)
    for r in rows:
        text = (r.get("my_answer") or "").strip()
        url = r.get("post_url") or ""
        if not text or not url or url in seen:
            continue
        seen.add(url)
        situation = r.get("situation")
        if situation not in BOT_SITUATIONS:
            situation = LEAD_PATH_SITUATION.get(r.get("lead_path"), "tech_answer")
        new.append({"id": f"tg-{url}", "situation": situation,
                    "audience": audience_for(r.get("group_url", "")),
                    "context": (r.get("post_text") or "")[:1000], "text": text,
                    "source": "telegram",
                    "date": r.get("posted_date") or r.get("date_fetched") or "",
                    "post_url": url, "bot_use": True})
    return new


def append_examples(path: Path, examples: list) -> None:
    with open(path, "a", encoding="utf-8") as f:
        for e in examples:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def recent_group_replies(rows: list, group_url: str, n: int = RECENT_PER_GROUP) -> list:
    """Newest last in the Sheet, so walk backwards. Gilad's own text wins over
    the bot draft for the same post."""
    out = []
    for r in reversed(rows):
        if r.get("group_url") != group_url:
            continue
        text = (r.get("my_answer") or "").strip() or (r.get("answer") or "").strip()
        if text:
            out.append(text)
        if len(out) >= n:
            break
    return out
```

Note: `test_recent_group_replies_prefers_gilads_text_and_limits` appends the `mine` row last, so walking backwards it is first.

- [ ] **Step 5: Run all tests**

Run: `.venv/bin/python -m pytest -v`
Expected: all pass (59 existing + 22 new). If `tests/test_sheet_rows.py` asserts the header count, update that assertion to the new length.

- [ ] **Step 6: Commit**

```bash
git add src/voice.py src/sheet_rows.py tests/test_voice.py tests/test_sheet_rows.py
git commit -m "voice: learn examples from Gilad's Sheet replies"
```

---

### Task 6: Seed `voice/examples.jsonl`

**Files:**
- Create: `tools/seed_voice.py`
- Create (generated): `voice/examples.jsonl`

- [ ] **Step 1: Write the seed script**

```python
"""One-time: build voice/examples.jsonl from the reviewed corpus in
~/Projects/just-bake-content/voice/ (review done with Gilad, 30/09/2026).

Usage: .venv/bin/python -m tools.seed_voice [SEED_DIR]
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SEED = Path(sys.argv[1] if len(sys.argv) > 1 else Path.home() / "Projects/just-bake-content/voice")

AUDIENCE_BY_BATCH = {1: "taboon_group", 2: "neighborhood", 3: "celiac_group"}

# sheet_pairs.jsonl rows, in file order (1-based), with the verdict from review.
# 'ignored' rows stay in the file so sync_learned_examples never re-adds them.
SHEET_PAIRS = {
    1: {"ignored": True, "note": "not an answer ('התגובה של פשוט לאפות זה אני')"},
    2: {"situation": "tech_answer"},
    3: {"situation": "tech_answer"},
    4: {"situation": "lead_order"},
    5: {"ignored": True, "note": "same text as pair 3"},
    6: {"ignored": True, "note": "canned: recipe_48h"},
    7: {"ignored": True, "note": "canned: recipe_48h"},
    8: {"situation": "tech_answer"},
    9: {"situation": "tech_answer", "text_from_rewrites": 0},
    10: {"situation": "no_answer", "text": None},
    11: {"situation": "where_to_buy", "text_from_rewrites": 2},
}


def fb_examples() -> list:
    comments = {c["id"]: c for c in json.loads((SEED / "corpus_fb_comments.json").read_text())}
    decisions = {}
    for line in (SEED / "review_decisions.jsonl").read_text().splitlines():
        d = json.loads(line)
        decisions[d["id"]] = d  # later lines win
    out = []
    for cid, d in sorted(decisions.items()):
        if d["decision"] != "keep":
            continue
        situation = d["situation"]
        if situation == "recipe_alt":
            continue  # lives in canned.md as recipe_24h_bread_flour
        c = comments[cid]
        out.append({"id": f"fb-{cid}", "situation": situation,
                    "audience": AUDIENCE_BY_BATCH.get(d.get("batch"), d.get("audience")),
                    "context": "", "text": c["text"].strip(), "source": "fb_comment",
                    "date": c["date"], "bot_use": d.get("bot_use", True)})
    return out


def sheet_examples() -> list:
    rewrites = [json.loads(l) for l in
                (SEED / "rewrites/2026-09-30_bot_replies.jsonl").read_text().splitlines() if l.strip()]
    rows = [json.loads(l) for l in (SEED / "sheet_pairs.jsonl").read_text().splitlines() if l.strip()]
    out = []
    for i, row in enumerate(rows, start=1):
        verdict = SHEET_PAIRS[i]
        base = {"id": f"tg-{row['post_url']}", "post_url": row["post_url"],
                "audience": "taboon_group", "context": row["post_text"][:1000],
                "source": "sheet_my_answer", "date": row["date_fetched"], "bot_use": True}
        if verdict.get("ignored"):
            out.append({**base, "ignored": True, "note": verdict["note"], "text": None,
                        "situation": "ignored"})
            continue
        if "text_from_rewrites" in verdict:
            text = rewrites[verdict["text_from_rewrites"]]["gilad"]
        elif "text" in verdict:
            text = verdict["text"]
        else:
            text = row["my_answer"].strip()
        out.append({**base, "situation": verdict["situation"], "text": text})
    return out


def rewrite_example() -> dict:
    record = (SEED / "rewrites/2026-09-30_em_hamoshavot_simchat_torah.md").read_text()
    final = record.split("## Final (approved by Gilad)\n", 1)[1].strip()
    return {"id": "rw-2026-09-30-simchat-torah", "situation": "neighborhood_post",
            "audience": "neighborhood", "context": "פוסט בקבוצת אם המושבות החדשה, שמחת תורה, מחירי החג נגמרים",
            "text": final, "source": "rewrite", "date": "2026-09-30", "bot_use": False}


def main():
    examples = fb_examples() + sheet_examples() + [rewrite_example()]
    target = REPO / "voice/examples.jsonl"
    target.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in examples),
                      encoding="utf-8")
    usable = [e for e in examples if not e.get("ignored") and e.get("bot_use")]
    print(f"{len(examples)} rows, {len(usable)} usable by the bot -> {target}")


if __name__ == "__main__":
    main()
```

Check before running: `rewrites/2026-09-30_bot_replies.jsonl` line 0 is the Kotza 17 post and line 2 is the semolina post (`python3 -c` to print `post[:30]` of each line). If the order differs, fix the two `text_from_rewrites` indexes.

- [ ] **Step 2: Create `tools/__init__.py` if missing and run**

```bash
test -f tools/__init__.py || touch tools/__init__.py
.venv/bin/python -m tools.seed_voice
```

Expected: `83 rows, 50 usable by the bot -> .../voice/examples.jsonl` (71 FB keeps after moving the bread-flour recipe to canned.md, 11 Sheet rows, 1 rewrite. Usable: 44 FB rows with bot_use plus 6 Sheet rows with text.) If the numbers differ, find out why before committing.

- [ ] **Step 3: Sanity check it loads**

```bash
.venv/bin/python -c "
from src.voice import load_voice, select_examples
v = load_voice()
from collections import Counter
print(Counter(e['situation'] for e in v.examples if not e.get('ignored')))
for e in select_examples(v.examples, 'lead_order', 'taboon_group', 'x'): print('-', e['text'][:60])"
```

Expected: counts per situation, then 4 different "who sells" lines.

- [ ] **Step 4: Commit**

```bash
git add tools/__init__.py tools/seed_voice.py voice/examples.jsonl
git commit -m "voice: seed examples from the reviewed corpus"
```

---

### Task 7: Scoring without the answer

**Files:**
- Modify: `src/community_monitor.py:373-596` (parse + `score_and_answer`)
- Test: `tests/test_scoring.py`

- [ ] **Step 1: Write the failing tests** (append to `tests/test_scoring.py`)

```python
def test_parses_situation_and_canned():
    raw = ('{"lead_score": 2, "lead_path": "professional", "score": 9,'
           ' "situation": "tech_answer", "canned": "recipe_48h"}')
    out = parse_score_response(raw)
    assert out["situation"] == "tech_answer"
    assert out["canned"] == "recipe_48h"


def test_unknown_situation_falls_back_by_lead_path():
    out = parse_score_response('{"lead_score": 9, "lead_path": "order", "situation": "weird"}')
    assert out["situation"] == "lead_order"


def test_missing_canned_is_none():
    out = parse_score_response('{"lead_score": 0, "lead_path": "none"}')
    assert out["canned"] is None
    assert out["situation"] == "no_answer"
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_scoring.py -v`
Expected: FAIL with `KeyError: 'situation'`

- [ ] **Step 3: Extend `parse_score_response`**

Add at the top of `src/community_monitor.py` imports: `from src import voice as voice_mod`.

In `parse_score_response`, before `return`, compute:

```python
    situation = data.get("situation")
    if situation not in voice_mod.BOT_SITUATIONS:
        situation = voice_mod.LEAD_PATH_SITUATION.get(
            path if path in VALID_LEAD_PATHS else "none", "no_answer")
```

and add to the returned dict:

```python
        "situation": situation,
        "canned": data.get("canned") or None,
```

Keep `"answer": data.get("answer") or None,` so old tests still pass; the new prompt no longer asks for it.

- [ ] **Step 4: Replace `score_and_answer` with `score_post`**

Rename the function to `score_post(post, claude, canned_names, quiet_examples)`. Build the prompt from these pieces, deleting the old sections `## מילון מונחי אפייה`, `## כלל מפתח`, `## סגנון התגובה`, `## כללי ניסוח לתשובה`, the `answer` JSON field, and `## דוגמאות אמיתיות` (all voice now lives in `voice/`). Keep the post/comments/image block and the `## שני ציונים נפרדים`, `### score`, `### lead_score`, and `## lead_path` sections exactly as they are.

New JSON block (replaces the old one):

```python
    canned_list = "\n".join(f"- {name}: {when}" for name, when in canned_names.items()) or "- אין"
    quiet_list = "\n".join(f"- {q[:200]}" for q in quiet_examples) or "- אין"
```

```
ענה בJSON בלבד (ללא markdown):
{{
  "image_description": "<תיאור קצר של התמונה, או null>",
  "post_type": "<question|showcase|ad|sale|welcome|other>",
  "lead_score": <0-10>,
  "lead_path": "<order|mentoring|professional|event|none>",
  "lead_reason": "<משפט אחד למה הציון הזה>",
  "score": <0-10>,
  "score_reason": "<משפט קצר>",
  "situation": "<lead_order|lead_workshop|tech_answer|where_to_buy|move_to_dm|no_answer>",
  "canned": "<שם תשובה קבועה מהרשימה, או null>",
  "tags": ["<נושא>"],
  "question_type": "<where_to_buy|recipe_help|technique|equipment|ingredient|general_pizza|not_relevant>"
}}

## situation - איזה סוג תשובה גלעד היה כותב
lead_order: מחפש לקנות בצק, ערכה, רוטב או גבינה
lead_workshop: מתעניין בסדנה, או מחפש ללמוד מגלעד
tech_answer: שאלה ספציפית על בצק, התפחה, קמח או אפייה
where_to_buy: שואל איפה קונים משהו (קמח, ציוד)
move_to_dm: צריך להמשיך בפרטי
no_answer: אין מה לענות, או בקשה כללית בלי בעיה ספציפית

פוסטים שגלעד לא היה עונה עליהם (situation=no_answer):
{quiet_list}

## canned - תשובות קבועות
אם הפוסט מבקש בדיוק את אחת מאלה, החזר את השם שלה. אחרת null.
{canned_list}
```

Also delete the `guidance` parameter; Facts now go to the writer (Task 8). Update the docstring-less function signature and both call sites in Task 8.

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/python -m pytest -v`
Expected: all pass. Fix any test that imported `score_and_answer` by renaming to `score_post` (check with `grep -rn score_and_answer tests src`).

- [ ] **Step 6: Commit**

```bash
git add src/community_monitor.py tests/test_scoring.py
git commit -m "monitor: scoring returns situation and canned, no draft"
```

---

### Task 8: Wire the writer and learning into the run

**Files:**
- Modify: `src/community_monitor.py` (`run_monitor`, around lines 630-720)
- Modify: `src/telegram_notify.py:54-69` (`format_alert`)
- Test: `tests/test_telegram_notify.py`

- [ ] **Step 1: Failing test for the alert warning** (append to `tests/test_telegram_notify.py`)

```python
def test_draft_warning_is_shown():
    text = format_alert(
        post={"text": "x", "url": "u"},
        result={"lead_score": 9, "lead_path": "order", "score": 4, "answer": None,
                "draft_warning": "⚠️ בלי קול, אין טיוטה"},
        group_name="g")
    assert "⚠️ בלי קול, אין טיוטה" in text
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_telegram_notify.py -v`
Expected: FAIL on the new test.

- [ ] **Step 3: Implement in `format_alert`**, after the `if answer:` block:

```python
    warning = result.get("draft_warning")
    if warning:
        lines += ["", html.escape(warning)]
```

- [ ] **Step 4: Wire `run_monitor`**

Replace the `guidance = answer_templates.render_guidance(...)` statement with:

```python
    facts = answer_templates.load_facts(spreadsheet)
    voice = voice_mod.load_voice()
    sheet_rows = [row_to_dict(r) for r in ws.get_all_values()[1:]]
    if voice is not None:
        known_urls = {e.get("post_url") for e in voice.examples if e.get("post_url")}
        learned = voice_mod.learned_examples(sheet_rows, known_urls)
        if learned:
            voice_mod.append_examples(voice_mod.VOICE_DIR / "examples.jsonl", learned)
            voice.examples.extend(learned)
            log.info(f"Learned {len(learned)} examples from Telegram replies")
    canned_names = {k: v["when"] for k, v in (voice.canned if voice else {}).items()}
    quiet = [e.get("context") or "" for e in (voice.examples if voice else [])
             if e.get("situation") == "no_answer" and e.get("context")]
```

Note: `apply_replies` runs before this, so a reply given since the last run is already in `sheet_rows`.

For a **new post**, replace `result = score_and_answer(post, claude, guidance)` and the `maybe_alert` line with:

```python
            result = score_post(post, claude, canned_names, quiet)
            result["answer"] = None
            if telegram_notify.should_notify(result["lead_score"], result["score"], ""):
                group_url = post.get("facebookUrl", "")
                result["answer"], result["draft_warning"] = voice_mod.write_reply(
                    post.get("text") or "", result["situation"],
                    voice_mod.audience_for(group_url), result["canned"], voice, claude,
                    seed=url, recent=voice_mod.recent_group_replies(sheet_rows, group_url),
                    facts=facts)
            notified_at, tg_message_id = maybe_alert(post, result, cfg)
```

and add `"situation": result["situation"],` to the `build_row({...})` dict.

For a **known post with new comments**, replace `result = score_and_answer(post, claude, guidance)` with `result = score_post(post, claude, canned_names, quiet)` and change the update so the existing draft is not wiped:

```python
                ws.update(f"G{row}", [[comments_flat[:800]]])
                ws.update(f"I{row}:J{row}", [[result.get("score", 0), result.get("score_reason", "")]])
```

- [ ] **Step 5: Run all tests**

Run: `.venv/bin/python -m pytest -v`
Expected: all pass.

- [ ] **Step 6: Local dry run against one real post** (no Sheet writes, no Telegram)

```bash
set -a; . ./.env; set +a
.venv/bin/python -c "
import anthropic, os
from src.community_monitor import score_post
from src import voice as V
v = V.load_voice(); c = anthropic.Anthropic()
post = {'url':'u','facebookUrl':'https://www.facebook.com/groups/1061644604326919','text':'יש לי טאבון של קוצה 17 הדגם הקלאסי. צריך להדליק על עוצמה הכי גבוהה ואז להוריד? או להשאיר על הכי חזקה?','user':{'name':'x'},'time':'2026-09-30','topComments':[]}
r = score_post(post, c, {k:x['when'] for k,x in v.canned.items()}, [])
print(r['situation'], r['lead_score'], r['canned'])
print(V.write_reply(post['text'], r['situation'], 'taboon_group', r['canned'], v, c, 'u'))"
```

Expected: `tech_answer`, a draft in plain Hebrew with no JSON and no "תוצאה מבאסת".

- [ ] **Step 7: Commit**

```bash
git add src/community_monitor.py src/telegram_notify.py tests/test_telegram_notify.py
git commit -m "monitor: draft with voice for alerting posts, learn from replies"
```

---

### Task 9: Workflow commits learned examples

**Files:**
- Modify: `.github/workflows/community-monitor.yml`

- [ ] **Step 1: Add permissions** under `jobs: monitor:` (same indent as `runs-on`):

```yaml
    permissions:
      contents: write
```

- [ ] **Step 2: Add a step** after `Run community monitor` and before `Alert on failure`:

```yaml
      - name: Commit learned voice examples
        if: success()
        run: |
          if git diff --quiet -- voice/examples.jsonl; then
            echo "No new examples"
            exit 0
          fi
          n=$(git diff --numstat -- voice/examples.jsonl | awk '{print $1}')
          git config user.name "just-bake-bot"
          git config user.email "just-bake-bot@users.noreply.github.com"
          git add voice/examples.jsonl
          git commit -m "voice: learn ${n} examples"
          git pull --rebase origin "${GITHUB_REF_NAME}"
          git push origin "HEAD:${GITHUB_REF_NAME}"
```

A failed push fails this step only after the run's alerts went out; the next run re-learns from the Sheet (spec §5.2).

- [ ] **Step 3: Validate YAML**

Run: `.venv/bin/python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/community-monitor.yml')); print('ok')"`
Expected: `ok` (if `yaml` is missing: `.venv/bin/pip install pyyaml` first; do not add it to requirements).

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/community-monitor.yml
git commit -m "ci: commit voice examples learned from Telegram replies"
```

---

### Task 10: Voice eval (success measure)

**Files:**
- Create: `tools/voice_eval.py`

- [ ] **Step 1: Write the script**

```python
"""Side by side: old bot draft / new draft / Gilad, on the reviewed Sheet pairs.
Gilad judges. Usage: .venv/bin/python -m tools.voice_eval > voice_eval.md"""

import json
from pathlib import Path

import anthropic

from src import voice as V
from src.community_monitor import score_post

SEED = Path.home() / "Projects/just-bake-content/voice"


def main():
    v = V.load_voice()
    claude = anthropic.Anthropic()
    canned = {k: x["when"] for k, x in v.canned.items()}
    rows = [json.loads(l) for l in (SEED / "sheet_pairs.jsonl").read_text().splitlines() if l.strip()]
    gilad_by_url = {e["post_url"]: e for e in v.examples if e.get("post_url")}
    # Leave-one-out: never show the model Gilad's answer to the post it is answering.
    for i, row in enumerate(rows, start=1):
        target = gilad_by_url.get(row["post_url"], {})
        if target.get("ignored") and "canned" not in (target.get("note") or ""):
            continue
        v_eval = V.Voice(v.rules, [e for e in v.examples if e.get("post_url") != row["post_url"]], v.canned)
        post = {"url": row["post_url"], "facebookUrl": row["group_url"], "text": row["post_text"],
                "user": {"name": ""}, "time": "", "topComments": []}
        r = score_post(post, claude, canned, [])
        draft, warning = V.write_reply(row["post_text"], r["situation"], "taboon_group",
                                       r["canned"], v_eval, claude, row["post_url"])
        gilad = target.get("text") if target else row["my_answer"]
        print(f"## {i}. {row['post_text'][:120]}\n")
        print(f"**situation:** {r['situation']}  **canned:** {r['canned']}  {warning or ''}\n")
        print(f"**Old bot:**\n\n{row['answer'] or '(none)'}\n")
        print(f"**New:**\n\n{draft or '(no answer)'}\n")
        print(f"**Gilad:**\n\n{gilad or row['my_answer'] or '(no reply)'}\n\n---\n")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it**

```bash
set -a; . ./.env; set +a
.venv/bin/python -m tools.voice_eval > voice_eval.md
```

Expected: 9-10 sections. Check by eye before showing Gilad: no `—`, no "תוצאה מבאסת", no JSON, the tips-for-first-time post shows `(no answer)`, recipe posts show the canned recipe.

- [ ] **Step 3: Show `voice_eval.md` to Gilad.** He marks each new draft: would post as-is / small edit / not me. Do not commit `voice_eval.md`.

- [ ] **Step 4: Commit the script**

```bash
git add tools/voice_eval.py
git commit -m "tools: side-by-side voice eval"
```

---

### Task 11: Claude Code skill and brand.json pointer

**Files (outside the repo):**
- Create: `~/.claude/skills/just-bake-voice/SKILL.md`
- Modify: `~/.claude/brand-kits/just-bake/brand.json`

- [ ] **Step 1: Create the skill**

```markdown
---
name: just-bake-voice
description: Write posts and replies for Gilad's pizza-dough business "פשוט לאפות" in his real voice, from the single voice folder shared with the community bot. Use whenever writing or fixing a Facebook post, group reply, WhatsApp message or any customer-facing Hebrew text for just-bake / פשוט לאפות, and whenever Gilad rewrites a draft (to learn from it).
---

# just-bake voice

The voice lives in ONE place: `~/Projects/just-bake/voice/`. The community bot reads the
same folder. Never keep voice rules anywhere else.

## Before writing

1. `git -C ~/Projects/just-bake pull --rebase` (the bot commits new examples).
2. Read `voice/voice.md` fully. Read `voice/canned.md` if the request is a technical reply.
3. Load `voice/examples.jsonl`. Use only rows without `"ignored": true`.

## A post

1. Angle first. Ask Gilad: did something happen this week at home or with the family that
   is related to pizza or the holiday? If not, offer 3 angles, one line each, no drafts.
   `voice/hooks.md` lists occasions he posts about and openings that are his.
2. Look at what he recently posted in the same group, so the opening and signature phrases
   are not reused. Variety is a hard requirement: people in the group see every post.
3. Draft from `neighborhood_post` examples and the neighborhood rules in `voice.md`.
   One product line, first person, then prices, pickup, phone. Prices only from what Gilad
   gives you or the current price list, never from an example.

## A reply to a group post

Pick 3-4 examples with the same `situation` at random (same `audience` first). If a
`canned.md` entry fits exactly, paste it verbatim. If the post is a vague request with no
specific problem, say Gilad would probably not answer.

## When Gilad rewrites a draft (the important part)

1. Save `voice/rewrites/<date>_<topic>.md`: draft, each of his corrections with his words,
   final.
2. Append the final text to `voice/examples.jsonl`
   (`"source": "rewrite"`, right `situation` and `audience`).
3. If a correction is a new general rule, add one line to `voice.md` with its source:
   `(גלעד, DD/MM/YYYY: "his words")`. Keep `voice.md` short; merge rather than append when a
   rule already covers it.
4. Show the `git diff`, and commit and push only after Gilad approves.
```

- [ ] **Step 2: Shrink brand.json voice** (keep a backup)

```bash
cd ~/.claude/brand-kits/just-bake
cp brand.json brand.json.pre-voice-folder
python3 - <<'EOF'
import json
p = "brand.json"
b = json.load(open(p))
b["voice"] = {
    "tone": "דוגרי, עברית מדוברת, חם ומשפחתי",
    "rules": [],
    "source": "~/Projects/just-bake/voice (use the just-bake-voice skill)",
}
json.dump(b, open(p, "w"), ensure_ascii=False, indent=2)
EOF
node ~/.claude/skills/brand-kit/cli.mjs show 2>&1 | head -20
```

Expected: brand-kit prints the profile with no schema error (it requires only `voice.tone`
string and `voice.rules` array).

- [ ] **Step 3: Check nothing was lost.** Every item from the old `voice.rules`,
`ai_tells_to_avoid`, `hook_pattern` and `examples` in `brand.json.pre-voice-folder` must be in
`voice.md`, `hooks.md` or `examples.jsonl`. Diff by eye; add anything missing to `voice.md`
and commit it in the repo.

- [ ] **Step 4: Push the repo** (after Gilad approves the eval in Task 10)

```bash
cd ~/Projects/just-bake && git push
```

The next scheduled Community Monitor run uses the new voice. Watch its Telegram alerts and
the first `voice: learn N examples` commit.

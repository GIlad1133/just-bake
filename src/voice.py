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

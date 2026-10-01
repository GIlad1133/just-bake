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

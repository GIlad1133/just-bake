"""One-time: build voice/examples.jsonl from the reviewed corpus in
~/Projects/just-bake-content/voice/ (review done with Gilad, 30/09/2026).

Usage: .venv/bin/python -m scripts.seed_voice [SEED_DIR]
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SEED = Path(sys.argv[1] if len(sys.argv) > 1 else Path.home() / "Projects/just-bake-content/voice")

AUDIENCE_BY_BATCH = {1: "taboon_group", 2: "neighborhood", 3: "celiac_group"}

# Facebook's automatic tag of the person replied to, which lands as the comment's
# first line (e.g. "Eyal Keren \nמצרף את המחירון המלא..."). The bot drafts top-level
# comments, not replies, so it must never learn to open with a name: drop the tag line.
# Checked: for every id below, corpus_fb_comments.json's first line is only a person's
# name. (fb-82 "היי גיא," is kept as-is: greeting the person who asked by name is
# Gilad's own style, not a Facebook-inserted tag.) id 40 was excluded: its first line
# is "Osher Avital שולח הודעה בפרטי", not just a name, so it needs human judgment.
REPLY_TAG_IDS = {3, 8, 25, 35, 36, 37, 41, 59, 83, 92}

# Refers to another commenter's answer ("התשובה של קובי"); not usable as a standalone
# bot reply even though it's a good example of Gilad's voice.
NOT_FOR_BOT_IDS = {17}

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
        text = c["text"]
        if cid in REPLY_TAG_IDS:
            text = text.split("\n", 1)[1]
        text = text.strip()
        bot_use = False if cid in NOT_FOR_BOT_IDS else d.get("bot_use", True)
        out.append({"id": f"fb-{cid}", "situation": situation,
                    "audience": AUDIENCE_BY_BATCH.get(d.get("batch"), d.get("audience")),
                    "context": "", "text": text, "source": "fb_comment",
                    "date": c["date"], "bot_use": bot_use})
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


def live_examples() -> list:
    # Gilad's approved Sukkot post, copied verbatim from
    # ~/.claude/brand-kits/just-bake/brand.json.pre-voice-folder -> voice.examples[0].text
    text = ("סוכות כבר מעבר לפינה ולקראת החג יצאתי במחירי מבצע לחגים!\n"
            "בצק לפיצה נפוליטנית בהתפחה של 48 שעות, מתאים לאפייה בתנור ביתי ולטאבון.\n\n"
            "ניתן להזמין מארזים הכוללים 5 כדורי בצק, גבינה, רוטב וקמח לפתיחה. "
            "האיסוף ממש כאן באם המושבות.\n\n"
            "מארז 120 ₪\n2 מארזים 230 ₪\n10 כדורי בצק 100 ₪\n"
            "יש גם בצקים ללא גלוטן ומקמח כוסמין (מחיר מופיע במחירון)\n\n"
            "מחירון מלא מצורף.\n\n"
            "המלאי מוגבל, מהרו להזמין.\n"
            "איסוף: נס ציונה 10, אם המושבות הותיקה\n"
            "הזמנות: 0525800797 גלעד")
    return [{"id": "live-2026-09-17-sukkot", "situation": "neighborhood_post",
             "audience": "neighborhood",
             "context": "פוסט בקבוצת אם המושבות החדשה לקראת סוכות, מחירי מבצע לחגים",
             "text": text, "source": "live_post", "date": "2026-09-17", "bot_use": False}]


def main():
    examples = fb_examples() + sheet_examples() + [rewrite_example()] + live_examples()
    target = REPO / "voice/examples.jsonl"
    target.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in examples),
                      encoding="utf-8")
    usable = [e for e in examples
              if not e.get("ignored") and e.get("bot_use") and (e.get("text") or "").strip()]
    print(f"{len(examples)} rows, {len(usable)} usable by the bot -> {target}")


if __name__ == "__main__":
    main()

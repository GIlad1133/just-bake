# just-bake voice — Design

**Date:** 2026-09-30
**Status:** Design agreed in discussion 30/09/2026. Spec pending Gilad's review.

## 1. Problem

The community bot drafts replies that don't sound like Gilad. Posts written with Claude Code
don't either. Gilad: "it answers in a way that isn't close to my tone in any way".

Gilad's voice currently lives in three places that don't talk to each other:

| Where | Used by |
|---|---|
| `~/.claude/brand-kits/just-bake/brand.json` → `voice` | Claude Code (brand-kit and skills that read it) |
| Hardcoded prompt in `src/community_monitor.py:422` + Sheet `Templates` / `Facts` | The bot only |
| `~/Projects/just-bake-content/voice/` (corpus collected 30/09) | Nobody yet |

A rule fixed in one place stays broken in the others.

Goal: **one voice folder in this repo**, read by the bot in GitHub Actions and by a Claude Code
skill locally, that learns automatically from Gilad's own replies.

## 2. Findings

1. **The bot copies its examples, not its rules.** The prompt has two hardcoded examples. One says
   "30 דקות, 350 מעלות, תוצאה מבאסת", and that tip appears in unrelated replies: a sukkah
   pizza-night question, and two replies on 27/09 that are near-identical.
2. **Several prompt rules contradict how Gilad writes.** From 123 of his Facebook comments:

   | Prompt rule | Gilad |
   |---|---|
   | No closing line / invitation | Most common pattern: `מוזמן להגיע אליי לפתח תקווה` |
   | Never end with a question | Sometimes replies only with a question |
   | No emoji except `:)` | `🍕🍕`, `🙏🏼`, `🤣🤣`, usually doubled |
   | 2-4 lines, always a number | Often one line, sometimes one word (`תקין.`) |

3. **Voice is written inside JSON.** Scoring, classification and the reply share one call and
   the reply is a JSON field. The model writes like an analyst.
4. **Knowledge gaps look like voice gaps.** The bot said "stone around 350°". Gilad: 350-450,
   lower the flame while the pizza bakes, raise it between pizzas. (Facts sheet fixed 30/09.)
5. **Most "approved" text is not Gilad's.** He has used AI for posts for about two years.
   `posts/approved/` and his Facebook posts are a mix. Only his comments and his Telegram
   replies are reliably his own. Research agrees: real samples beat style descriptions
   (arXiv 2509.24930: <7% zero-shot vs ~95% one-shot), and informal short text needs more
   samples (arXiv 2509.14543).
6. **Variety is a hard requirement.** Gilad: "תשובה או פוסט רק בניסוח אחד לא יעבדו כי אנשים
   בסוף יבינו שזה לא אני". Group members see every reply, so repeated phrasing gives it away.
7. **The bot only reads Facebook and only writes to Gilad's Telegram.** Nothing is posted
   automatically. A bad draft costs Gilad a rewrite, not a customer.

## 3. Decisions

| # | Decision | Why |
|---|---|---|
| D1 | Voice lives in `voice/` in this repo | Readable by Actions and locally; every change is a commit |
| D2 | Gilad's Telegram text replies become examples automatically, no review | They are the only guaranteed-clean source |
| D3 | Examples chosen by situation + audience, plus a short rules file (no generated "voice profile") | Samples beat descriptions; generated profiles reintroduce AI phrasing |
| D4 | No separate critic pass for now | Add later only if drafts still slip |
| D5 | Posts are never full-body style examples | They are AI-mixed; only hooks and angles are used |
| D6 | Facts stay in the Sheet | They are knowledge, not voice, and `/fact` already edits them from the phone |

## 4. The `voice/` folder

```
voice/
  voice.md          # rules, each with its source
  examples.jsonl    # Gilad's real texts, one JSON object per line
  canned.md         # answers pasted verbatim
  hooks.md          # post openings and angles that are his
```

### 4.1 `voice.md`

At most 15 rules, plain Hebrew, no markdown headings inside the rules. Each rule states its
source. Only rules that came from Gilad's own corrections or are directly visible in his
comments. Seed content:

- From brand.json `voice.rules` and `ai_tells_to_avoid` that still hold.
- From 30/09: no telegraphic spec line in neighborhood posts; one product line, not stacked
  reassurances; point to the reader's next step (`לכם נשאר רק להזמין ולאפות`); when information
  is missing, split the answer ("אם עבר X זמן אז ככה, אחרת ככה") instead of only asking; never
  copy a price from an example; technical answers in impersonal plural (`מדליקים`, `בודקים`),
  not second-person imperatives (`תדליק`).
- Audience rule: `48 שעות התפחה` is for bakers. Neighbors hear time saved, fun, fresh.

Rules that contradict Gilad (§2.2) are not carried over.

### 4.2 `examples.jsonl`

```json
{"id": "fb-7", "situation": "tech_answer", "audience": "taboon_group",
 "context": "<the post he answered, or empty if unknown>",
 "text": "נשמע כמו בצק שהגיע לטמפרטורה גבוהה מידי...",
 "source": "fb_comment", "date": "2025-10-11", "bot_use": true}
```

- `situation`: `lead_order`, `lead_workshop`, `tech_answer`, `where_to_buy`, `move_to_dm`,
  `no_answer`, `own_post_reply`, `own_post_thanks`, `neighborhood_post`.
- `audience`: `taboon_group`, `neighborhood`, `celiac_group`.
- `text: null` means "Gilad would not answer this" (`situation: no_answer`).
- `source`: `telegram`, `fb_comment`, `rewrite`, `sheet_my_answer`.
- `bot_use: false` for situations the bot never writes (`own_post_*`, `neighborhood_post`).
- Near-duplicate variants of the same move are kept on purpose (D-variety).

### 4.3 `canned.md`

Two recipes, pasted verbatim when a post asks for one: the 48-hour Neapolitan recipe
(1000 קמח / 660 מים / 28 מלח / 2 שמרים) and the 24-hour bread-flour recipe (comment fb-1).
Each entry has a one-line "when to use".

### 4.4 `hooks.md`

Openings from the 7 posts Gilad marked as mostly his (#9, 10, 11, 13, 38, 64, 70), the
Simchat Torah rewrite, and the hook pattern from brand.json. Used only by the Claude Code
skill when writing posts. The other 61 business posts are an index of occasions he posts
about, not style.

## 5. Bot changes (`src/community_monitor.py`)

### 5.1 Split scoring from writing

- **Scoring call** (existing, trimmed): returns the current JSON minus `answer`, plus
  `situation` from the §4.2 list. The hardcoded examples and the voice section are removed.
  `no_answer` examples from `examples.jsonl` are shown here as posts to classify, so the
  scorer learns when Gilad stays quiet (e.g. vague "tips for my first time").
- **Writing call** (new `src/voice.py`), only for posts that pass `should_notify`:
  1. If the post matches a `canned.md` entry, return it verbatim.
  2. If `situation == no_answer`, no draft.
  3. Otherwise pick up to 4 examples with the same situation and audience, falling back to
     same situation any audience. Picked **at random**, seeded by the post URL so tests are
     reproducible.
  4. Messages: `voice.md` + Facts as the system prompt; each example as a user turn (its
     `context`, or the situation name when context is empty) and an assistant turn (`text`);
     then the real post. Output is plain text.
  5. **Per-group memory:** the last 10 drafts and `my_answer`s for the same group (from the
     Sheet, no new storage) are listed as "already said in this group, don't reuse their
     openings or signature phrases".

Posts that don't alert no longer get a draft. The `answer` column stays empty for them.

### 5.2 Learning loop

A new `sync_learned_examples(ws)` runs after `apply_replies`: every Sheet row with a
`my_answer` whose `post_url` is not yet in `examples.jsonl` is appended (`source: telegram`,
`context: post_text`, situation from the row, audience from the group). Idempotent: if a push
fails, the next run re-adds it from the Sheet. Nothing is lost.

A new workflow step after the run: if `voice/examples.jsonl` changed, commit
`voice: learn N examples`, `git pull --rebase`, push. The job needs `permissions:
contents: write`. The existing `concurrency` group prevents two runs pushing at once.

### 5.3 Failure handling

| Failure | Behaviour |
|---|---|
| `voice/` missing or unparseable | Alert still sent, with `⚠️ בלי קול, הטיוטה ניחוש` and no draft |
| Situation has fewer than 2 examples | Draft from `voice.md` alone, alert marked `⚠️ אין דוגמאות למצב הזה` |
| Push fails | Logged; the Sheet still holds `my_answer`, next run retries (§5.2) |
| Writing call errors | Alert sent without a draft, as today on Claude errors |

## 6. Claude Code skill: `just-bake-voice`

`~/.claude/skills/just-bake-voice/SKILL.md`, reading `~/Projects/just-bake/voice/`.

- Runs `git pull` in `~/Projects/just-bake` first.
- For a post: angle first (ask about a family moment, else 3 one-line angles). Then a draft
  using hooks, neighborhood examples and `voice.md`. Checks what was recently posted in the
  same group so openings don't repeat.
- For a reply: same selection as the bot (§5.1).
- When Gilad rewrites a draft: append the final text to `examples.jsonl` (`source: rewrite`),
  save the draft→final record to `voice/rewrites/`, add any new rule to `voice.md` with its
  source. Show the diff and commit/push only after Gilad approves.

`brand.json` `voice` shrinks to a one-line `tone`, empty `rules`, and
`"source": "~/Projects/just-bake/voice"`. brand-kit's schema only requires those two fields.

## 7. Seeding (one time)

From `~/Projects/just-bake-content/voice/` (review done with Gilad on 30/09):

| Source | Goes to |
|---|---|
| `review_decisions.jsonl` keep rows + `corpus_fb_comments.json` | `examples.jsonl` (72 rows, 45 `bot_use`) |
| 7 Sheet `my_answer` pairs + `rewrites/2026-09-30_bot_replies.jsonl` | `examples.jsonl` with post context |
| `rewrites/2026-09-30_em_hamoshavot_simchat_torah.md` | `examples.jsonl` (`neighborhood_post`) + `voice/rewrites/` |
| `pending_rules.md`, `design_notes.md`, brand.json voice | `voice.md` |
| fb-1 + the canned recipe | `canned.md` |
| `corpus_fb_posts.json` hook sources | `hooks.md` |

Personal comments, thanks duplicates and non-business posts stay out. The raw Facebook ZIP
is not committed.

## 8. Testing

- Unit tests (`tests/test_voice.py`, same style as `tests/test_telegram_notify.py`):
  example selection (situation, audience, fallback, deterministic seed), canned matching,
  `no_answer`, per-group memory text, `sync_learned_examples` idempotency.
- **Voice eval on real data:** the 10 posts that have both a bot draft and Gilad's verdict (9 replies, 1 "wouldn't answer").
  Run the new writer and show old bot / new bot / Gilad side by side. Gilad judges.
  That is the success measure: new drafts he would post with small edits or none.

## 9. Out of scope

Messenger and Instagram exports; the critic pass (D4); drafting replies to comments on
Gilad's own posts; posting anything to Facebook automatically.

## 10. Open

- Workshop prices (350 per person, 600 per couple, groups in private) stay out of Facts
  until Gilad decides.

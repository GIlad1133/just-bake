# Facebook Lead Alerts — Design

**Date:** 2026-09-16
**Status:** Design agreed in discussion 16/09/2026. Spec pending Gilad's review.
Two content deliverables outstanding (§5, §6).

## 1. Problem

The Community Monitor scrapes 7 Facebook groups once a day and writes scored posts to
a Google Sheet. Gilad reads the dashboard when he remembers to. By then a post asking
"who sells 50-60 dough balls for an event" is hours or days old and someone else answered it.

Goal: when a post appears that is worth money or worth answering, get it to Gilad's phone
within a few hours, with a ready-to-paste reply. See §8 for why the target is 3-4 hours
rather than 30 minutes, and §8.3 for the explicitly accepted coverage tradeoff.

## 2. What already exists

| Component | File | State |
|---|---|---|
| Apify scrape of 7 groups | `src/community_monitor.py:89` | Working |
| Noise pre-filter (no API cost) | `src/community_monitor.py:120` | Working, one bug (§6) |
| Claude scoring + answer drafting | `src/community_monitor.py:140` | Working, wrong rubric (§4) |
| Sheet storage (`Community` tab, 18 cols) | — | Working |
| Streamlit dashboard | `streamlit_app/pages/4_Community.py` | Working |
| Daily schedule | `.github/workflows/community-monitor.yml` | Working since 09/09/2026 |

This design changes scoring, adds Telegram, adds monitoring. It does not rebuild the pipeline.

## 3. Findings from 1,226 scored posts (86 days)

1. **The existing score penalises buyers.** The rubric at `community_monitor.py:207` lists
   `מכירה` (sale) in the 1-4 band, so people wanting to *buy* dough land there alongside
   people *selling* tabuns. Evidence:

   | Post | Score |
   |---|---|
   | "מחפש מישהו שמוכר 50-60 כדורי פיצה לטאבון 300g" | 3 |
   | "מכירים מקום מומלץ שאפשר לקנות כדורי בצק... קפואים" | 4 |
   | "לחם מחמצת. מה הסיפור? מה זה בכלל מחמצת?" | 8 |

   All 42 `where_to_buy` posts score 9 or below, with a long tail at 2-4.

2. **Score distribution:** 9→17, 8→84, 7→86, 6→162, 5→85, ≤4→792.

3. **Apparent new-post volume:** median 11/run, mean 14.3. **This figure is an artifact** —
   `resultsLimit: 10` truncates the scrape, so it measures the cap, not the groups. Real output
   is ~190 posts/day (measured 16/09, §8.2). Every estimate derived from 11/day was too low.

4. **Lead-class volume** (keyword estimate, undercounts): new tabun owners 14/86 days,
   explicit buyers 23/86 days, 37 unique → **0.43/day**.

5. **Silent 16-day outage.** No rows between 23/08 and 09/09; GitHub Actions failed every
   scheduled run 01/09–08/09. Nobody noticed. See §9.

6. **The model invents numbers.** On a post scoring 9 it drafted:
   *"פיצה ללא גלוטן... עם W-ערך גבוה מספיק (משהו כמו 300+)"*.
   W measures gluten strength; gluten-free flour has no W value. This was drafted for
   Gilad to post under his own name in a group of bakers.

## 4. Scoring: two axes, not one

A post is scored on two independent axes in the same Claude call.

| Field | Question | Drives |
|---|---|---|
| `expertise_score` (existing `score`) | How well can Gilad answer this? | Dashboard, content ideas |
| `lead_score` (new) | How close is this person to buying? | **Telegram alert** |

They are often inverted: a 60-ball order is a perfect lead and a non-question; "what is
sourdough" is a perfect question and a non-lead. No single threshold catches both.

### 4.1 Lead score — three gates

A post must pass **all three** to score above 0:

1. **Direction** — they are buying, not selling.
2. **Product** — it is something Gilad sells: dough, kits, sauce, flour, cheese, workshops.
   Not mixers, not tabuns, not shamot stones, not spice bags.
3. **Scale** — personal/home use. Not wholesale, not pizzeria, not B2B supply.

Gate 3 is independent of geography: a home baker in the north asking where to buy flour
is a lead; a pizzeria in the north looking for a cheese supplier is not.

### 4.2 Lead scale

| Score | Meaning | Path |
|---|---|---|
| 10 | Passes all three gates — personal buyer wanting dough/kit/sauce/flour/cheese, any quantity — **or** a new tabun owner with no knowledge *who is oriented toward pizza/dough* | Product / Mentoring |
| 7-9 | Personal event supplier search, workshop interest, specific product question | Both |
| 4-6 | Experienced home baker who makes their own | Product, distant |
| 1-3 | Learning theory, or equipment Gilad does not know (mixers, tabun models) | None |
| 0 | Selling, photo with no question, ad, or any B2B/pizzeria/wholesale inquiry | None |

New tabun owners sit at 10 because they convert on the **mentoring path**: accompany them
now, they become a workshop customer, then a recurring dough customer.

**Gate 2 applies to the mentoring branch as well.** A new tabun owner only qualifies if the
post is oriented toward pizza or dough. Someone asking what to *cook* in a taboon — vegetables,
meat, general first-use tips — has no dough problem and is not a lead. Rejected example,
supplied 16/09/2026:

> רכשנו טאבון גז cozzi עם צלחת מסתובבת. ממה מתחילים? ירקות? אשמח לטיפים עבור מתחילים

Gilad's verdict: *"אין לי מה להגיב, הוא לא מחפש לקנות בצק... ולדחוף לו ככה הצעה זה לא אופי הקבוצה."*
Correct score: low. Replying at all reads as marketing to that group.

### 4.3 Hard excludes (score 0, no answer drafted)

- Photo/showcase posts with no question
- Anyone selling anything
- Mixer and dough-mixer questions (outside Gilad's expertise)
- B2B / pizzeria / wholesale

### 4.4 Alert rule

```
notify if lead_score >= 7 OR expertise_score >= 9
```

Projected ~1 alert/day.

### 4.5 New Claude response fields

```json
{
  "lead_score": 0-10,
  "lead_path": "order|mentoring|professional|event|none",
  "lead_reason": "one sentence",
  "score": 1-10,            // existing expertise score, unchanged
  "answer": "...",          // now rendered through a template (§7)
  ...                       // existing fields unchanged
}
```

## 5. Answer templates

`lead_path` selects a template. Templates control **shape and tone**.

| Template | Trigger | Must contain | Must never contain |
|---|---|---|---|
| **Order** | `lead_path=order` | A soft check that Gilad can help (geography), then bare product facts | **A price**, a link, a CTA |
| **Mentoring** | `lead_path=mentoring` | One tip, with a number, and the consequence of getting it wrong | A price, a workshop pitch, a closing line |
| **Professional** | `lead_path=professional` | Full answer, pure value | Anything promotional |
| **Event** | `lead_path=event` | Quantities, timeline, pickup | A final price before quantity is known |

`lead_path` alone selects the template; the score decides *whether* to alert (§4.4), not
which template to use.

### 5.1 Voice rules, derived from Gilad's own replies

Supplied 16/09/2026 after rejecting two generated drafts. These are the reference answers.

**Mentoring — new tabun owner:**

> איזה כיף זה טאבון חדש!
> טיפ הכי טוב שאוכל לתת לך זה לתת לטאבון להתחמם 30 דקות לפני שאתה מתחיל לעבוד איתו (בכל הפעלה)
> חום אבן הטאבון כשאתה מכין פיצות צריך להיות סביבות 350 מעלות אחרת תקבל תוצאה מבאסת.

**Order — the 60-ball event request:**

> היי מאיר, אם איזור פתח תקווה בכיוון שלך אשמח לעזור :)
> בצקים שעברו התפחה של 48 שעות, יש אפשרות לטרי או קפוא. כל בצק שוקל כ-300 גרם

Rules extracted:

1. **Open with a short human line.** "איזה כיף זה טאבון חדש!" / "היי מאיר".
2. **One tip, not two.** Never explain back to them something they already own or said.
3. **Always a number.** 30 דקות, 350 מעלות, 48 שעות, 300 גרם. A tip without a number is filler.
4. **State the consequence plainly.** "אחרת תקבל תוצאה מבאסת."
5. **No closing line.** No CTA, no "message me", no "ask me anything", no link. End on a fact
   and stop. Any sentence that inserts Gilad into the conversation makes the reply read as
   marketing.
6. **No price in the first message — including in the Order template.** Check whether you can
   help them at all (geography), then say what the product *is*. Price comes after they reply.
7. **No emoji.** `:)` is acceptable; `🔥`/`🍕` are not.
8. **Two to four lines.** Both reference answers are three.

Existing voice constraints still apply: spoken Hebrew, no slogans, no em dashes, no
over-polishing, correct baking terminology.

Rationale: for a new tabun owner a price in the first message kills the lead; for someone
wanting 60 balls, the *absence* of a price kills it.

**Storage:** a new `Templates` tab in the existing spreadsheet, one row per template.
Gilad edits wording from his phone with no deploy. Read lazily — only when a post crosses
the alert threshold (~1/day), so it is not a per-run cost.

Existing voice constraints in memory still apply: spoken Hebrew, no slogans, no em dashes,
no over-polishing.

## 6. Facts table

Templates control shape. They do **not** stop the model inventing numbers (§3.6).
A second `Facts` tab holds numbers Gilad will stake his name on. Anything not in the table
is answered generally, without numbers. Gluten-free is a candidate for explicit refusal.

### 6.1 Seed content (supplied 16/09/2026)

**Base dough recipe, per 1000g flour — 48 hour version:**

| Ingredient | Amount | Baker's % |
|---|---|---|
| Pizza flour | 1000 g | 100% |
| Water | 660 g | 66% |
| Salt | 28 g | 2.8% |
| Fresh yeast | 2 g | 0.2% |

**Method:**
1. Mix flour + water only until combined (1 min in mixer)
2. Rest in fridge 30-60 min
3. Add yeast, knead 5 min
4. Add salt, knead a further 5-10 min until smooth
5. Room temperature ~2 h (1 h in summer)
6. Fridge, 48 h
7. Divide into 250 g balls, shape, proof at room temperature until doubled
   (up to 5 h in winter, 1.5-2 h in summer)

**Yeast scaling — the only variable that changes with proofing time**, per kg flour:

| Cold proof | Fresh yeast |
|---|---|
| 24 h | 3 g |
| 48 h | 2 g |
| 72 h | 1 g |

### 6.2 Open items for §6

- Dry yeast conversion. The table is fresh yeast; most home bakers have dry. Either add a
  conversion or have the model ask which they have.
- Which specific flour(s) "קמח פיצה" means, by brand/name.
- ~~Ball weight~~ **Resolved 16/09/2026:** 250 g is the *recipe's* division; the *product* Gilad
  sells is ~300 g per ball, 48 h proofed, available fresh or frozen.
- Hydration deviations: when to move off 66%.
- Topics to refuse rather than guess.

## 7. Telegram

New module `src/telegram_notify.py`. Bot API, no server, no polling.

Message per alert:

```
🔥 ליד 10 · מסלול: הזמנה · <group name>
"<post excerpt>"

<suggested answer in a <code> block>

[📄 לפוסט]  [📊 לדשבורד]
```

- Answer goes in a `<code>` block — Telegram makes these **tap-to-copy on mobile**.
- `lead_path` shown in the header so the play is known before reading.
- Inline keyboard uses URL buttons only (no callbacks, so no listener process needed).

**Dedup:** new `notified_at` column. Only rows with an empty value are eligible.

**Failure behaviour:** a Telegram error is logged and the run continues. The sheet row is
written either way and `notified_at` stays empty, so the next run (30 min later) retries.
Telegram being down can never break the scraper or lose a lead.

## 8. Cadence and Apify cost

Measured 16/09/2026 against the live account (FREE plan, $2.46 of $5.00 consumed at test time).
Total cost of the verification: $0.084.

### 8.1 Measured billing model

The actor charges two event types, confirmed by controlled runs:

| Event | Cost |
|---|---|
| `actor-start` | **$0.008 per run**, regardless of results |
| `post` (+ `filter-applied`) | **~$0.006 per post examined** |

Verification, single quiet group, `resultsLimit: 5`:

| Run | Input | Posts back | Charged events | Cost |
|---|---|---|---|---|
| A — control | no date filter | 5 | `post:3, actor-start:1` | $0.0260 |
| B — treatment | `onlyPostsNewerThan` = now-10min | 0 | `post:0, actor-start:1` | $0.0080 |

**`onlyPostsNewerThan` filters before billing — confirmed.** Run B scanned the group and was
charged for zero posts.

Full production input (7 groups, `resultsLimit: 10`, 35-minute window): 7 posts, **$0.0500**.

### 8.2 Correction to the earlier plan

The first version of this section promised 30-minute cadence for under $1/month. That was wrong,
for a reason worth recording:

- The "~14 new posts/day" figure was **an artifact of `resultsLimit: 10` truncating the daily
  scrape**, not the groups' real output. The daily job has never seen a full day of posts.
- Real output is roughly **190 posts/day** across the 7 groups.
- Full coverage therefore costs **~$34/month at any cadence** — cost tracks posts examined,
  not frequency.
- 33 runs/day adds **$7.90/month in `actor-start` alone**, exceeding the whole free tier before
  a single post is charged.

Group-trimming does not rescue it. Dropping the busiest group saves ~$1.90/month and loses a
third of the score-8+ posts; the total available saving is 30-40%, not the 10× required.

### 8.3 Decision

**Every 4 hours during waking hours (4-5 runs/day), with `resultsLimit` kept low.**

| | |
|---|---|
| Latency | 3-4 hours — a 6× improvement on today |
| Estimated cost | $1.50-2.50/month, *less* than the current $4.92 |
| Coverage | Deliberately partial |

**Accepted tradeoff, confirmed by Gilad 16/09/2026:** *"we will learn as we go the frequency and
it's ok if we miss a few posts and not answer first."* Coverage is intentionally incomplete in
exchange for staying inside the free tier. Sub-hour latency is achievable but costs ~$49/month,
and is a business decision to revisit with real lead data rather than estimates.

**Cadence is to be tuned from a week of real operating data, not fixed now.**

### 8.4 Implementation

```python
"onlyPostsNewerThan": (datetime.utcnow() - timedelta(hours=5)).isoformat()
```

An exact ISO timestamp, not a relative string like `"5 hours"` — Apify documents relative values
only in days/months/years but explicitly supports ISO timestamps. A 5-hour window against a
4-hour cadence leaves overlap, so a delayed run loses nothing.

Cron: `0 4,8,12,16,20 * * *` UTC = 07:00 / 11:00 / 15:00 / 19:00 / 23:00 Israel (summer).

GitHub Actions is free — the repo is public.

**Known latency limit:** GitHub scheduled workflows are routinely delayed 5-20 minutes. Immaterial
at a 4-hour cadence.

> **Dependency:** the healthchecks.io schedule in §9 must match this cron exactly
> (`0 4,8,12,16,20 * * *`, UTC). It is currently set to `*/30 4-20 * * *` from the earlier plan
> and will raise false alarms until updated.

## 9. Monitoring

A 16-day silent outage already happened. Once this is an alerting system, silence is
indistinguishable from "no good posts," so three layers, all free:

| Layer | Catches | Mechanism |
|---|---|---|
| Crash alert | Run started and failed | `if: failure()` step in the workflow curls Telegram. Runs *because* the job failed, so it does not depend on our Python |
| Daily summary | Volume sanity check | One message at 21:00 from the last run of the day: runs, new posts, alerts sent. Derived from rows already in memory — no extra API calls |
| Dead-man's switch | Run never started at all | `healthchecks.io` free tier. Run pings a URL on success; no ping within the grace window and it alerts |

Layer 3 exists because layers 1 and 2 both run on the infrastructure being watched — a
monitor cannot report its own absence. It also covers GitHub automatically disabling
scheduled workflows in public repos after 60 days without a commit.

## 10. Schema changes

`Community` tab gains three columns:

| Column | Purpose |
|---|---|
| `lead_score` | 0-10 per §4.2 |
| `lead_path` | `order` / `mentoring` / `professional` / `event` / `none` |
| `notified_at` | Telegram dedup timestamp; empty = eligible |

Two new tabs: `Templates` (§5), `Facts` (§6).

## 11. Bug fix

`src/community_monitor.py:290` — the noise-row append writes 17 values but places
`"noise"` at index 11 (`question_type`) instead of index 12 (`status`), contradicting its
own comment. Result: 200 rows have `question_type="noise"` and an empty `status`.
The Telegram filter reads `status`, so this must be correct before it is trusted.

## 12. Testing

- Unit: Claude JSON parse, including malformed and fenced responses
- Unit: Telegram message formatting against fixtures, HTML escaping of post text
- Unit: alert rule — a matrix of `lead_score` × `expertise_score` × `notified_at`
- Unit: the three gates, using the real mis-scored posts from §3.1 as fixtures
- `--dry-run` flag: score and format but send nothing

## 13. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| `onlyPostsNewerThan` filters after billing | Cost 50× projection | Verify with one run before raising cron |
| Facebook blocks the datacenter proxy | No posts | Switch to residential proxy (costs more); heartbeat catches it |
| A group goes private | That group silently drops to zero | Per-group volume check in the daily summary |
| Model drafts a wrong fact not covered by §6 | Reputation damage | Facts table; answers are drafted, never auto-posted |
| Alert fatigue | Gilad mutes the bot | Threshold tuned to ~1/day; revisit after two weeks of real data |

**Answers are never auto-posted.** Every reply is drafted for Gilad to read, edit and send.

## 14. Deliverables from Gilad

| # | Item | Blocks |
|---|---|---|
| 1 | Telegram bot token + chat ID | All alerts |
| 2 | healthchecks.io ping URL | Layer 3 only |
| 3 | Three GitHub secrets added | All alerts |
| 4 | Apify plan / credit balance confirmed | Cost verification |
| 5 | Four template bodies (§5) | Answer quality |
| 6 | Facts table beyond the seed (§6.2) | Answer accuracy |

Items 5 and 6 are the ones only Gilad can write. Implementation proceeds without them;
they are filled into the Sheet tabs afterwards.

## 15. Reply channel (approved 16/09/2026)

Gilad replies to an alert in Telegram; the reply is ingested on the next scheduled run.
This is not a new capability so much as **the missing input device for the voice-training loop
already built in `f2313b1`** — which has sat at 2 saved answers out of a 10-answer threshold
since July, because feeding it required opening the dashboard.

### 15.1 No server required

Telegram queues incoming updates for **24 hours**. The scheduled run drains the queue at the
start of each execution:

```
1. GET getUpdates?offset=<last_update_id + 1>
2. Discard every update whose message.from.id != TELEGRAM_CHAT_ID
3. Act on the remainder
4. Persist the new last_update_id
5. Continue with the normal scrape
```

No webhook, no public endpoint, no always-on process. Latency to ingest a correction is one
cadence interval (up to 4 hours), which is appropriate for editing a template.

### 15.2 Supported replies

Each alert's `message_id` is stored (`tg_message_id`), so a Telegram reply maps back to its post
via `reply_to_message.message_id`.

| Input | Effect |
|---|---|
| Reply to an alert with free text | Saved to `my_answer` for that post; `status` → `posted` |
| Reply `/bad` or `/skip` | Marks the scoring as wrong; tuning data for the rubric |
| `/order <text>` (also `/mentoring`, `/event`, `/pro`) | Rewrites that row in the `Templates` tab |
| `/fact <line>` | Appends a line to the `Facts` tab |

`/fact` is how the four open items in §6.2 get answered without a sit-down writing session.

### 15.3 Risks and mitigations

| Risk | Mitigation |
|---|---|
| Overlapping runs double-process a reply | `concurrency` group in the workflow so runs queue rather than overlap |
| Offset mismanagement replays or drops commands | Persist `last_update_id` in a `Meta` tab; commands idempotent where possible |
| Silent loss after Telegram's 24h expiry | **The bot acknowledges every processed reply.** No ✅ means it was not saved. Without this the channel is untrustworthy |
| `/order` destroys wording via a typo | Previous value appended to a `Templates_history` tab before overwrite; the ack echoes what was stored |

Not risks, verified: `from.id` is set by Telegram's servers and cannot be spoofed by a sender;
a stolen token permits sending *as* the bot and reading its updates, but not forging a message
*from* Gilad — though it would let a thief drain the reply queue, so token hygiene still matters.

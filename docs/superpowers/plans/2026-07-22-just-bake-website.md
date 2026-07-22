# Just Bake One-Page Website Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one customer-facing Hebrew RTL single-file website for פשוט לאפות that funnels visitors to WhatsApp ordering, by running 3 parallel design-variant agents with Playwright screenshot verification and letting Gilad pick the winner.

**Architecture:** A shared content spec (`website/content-spec.md`) holds all facts; a Playwright "eyes" script (`tools/eyes.py`) gives every agent screenshots + console-error reports; three sub-agents each build one self-contained `website/variant_{a,b,c}.html` through 3 quality passes; the chosen winner replaces `website/index.html`. Real photos are curated from a 2.6 GB raw folder into optimized `website/assets/`.

**Tech Stack:** Plain HTML/CSS/JS (single file, no build step), Python 3 + Playwright (installed, Chromium present), Pillow 10.2 for image work. Spec: `docs/superpowers/specs/2026-07-22-just-bake-website-design.md`.

**Verified environment facts:** `python3 -c "import playwright"` works; Chromium at `~/.cache/ms-playwright/chromium-1208`; Pillow 10.2.0 installed; raw media at `JustBake-photo-videos/פשוט לאפות - תמונות וסרטונים/` (210 jpg/jpeg/png, 48 mov, 8 mp4, 5 heic — only jpg/jpeg/png are used).

---

### Task 1: Gitignore raw media and tooling output

**Files:**
- Modify: `.gitignore` (create if missing)

- [ ] **Step 1: Add ignore entries**

Append to `.gitignore` (create the file if it does not exist):

```gitignore
# Raw photo/video source (2.6 GB) — only optimized copies in website/assets/ are committed
JustBake-photo-videos/
# Website build tooling output (temp — deleted after site ships)
tools/
.playwright-mcp/
```

- [ ] **Step 2: Verify git no longer sees the folder**

Run: `git status --porcelain | grep -c JustBake`
Expected: `0`

- [ ] **Step 3: Commit**

```bash
git add .gitignore
git commit -m "Ignore raw media folder and website build tooling"
```

---

### Task 2: Photo curation into website/assets/

**Files:**
- Create: `tools/contact_sheets.py`, `tools/optimize.py`
- Create: `website/assets/*.jpg` (~12–16 optimized photos)

- [ ] **Step 1: Write the contact-sheet generator**

Create `tools/contact_sheets.py`:

```python
#!/usr/bin/env python3
"""Build indexed contact sheets (5x4 grid) from the raw photo folder so a
curator can review 210 photos in ~11 images instead of 210 Reads."""
from PIL import Image, ImageOps, ImageDraw
from pathlib import Path

SRC = Path("JustBake-photo-videos/פשוט לאפות - תמונות וסרטונים")
OUT = Path("tools/contact_sheets")
OUT.mkdir(parents=True, exist_ok=True)
COLS, ROWS, CELL = 5, 4, 320

imgs = sorted(p for p in SRC.iterdir()
              if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
with open(OUT / "manifest.txt", "w") as manifest:
    for start in range(0, len(imgs), COLS * ROWS):
        batch = imgs[start:start + COLS * ROWS]
        sheet = Image.new("RGB", (COLS * CELL, ROWS * CELL), "white")
        draw = ImageDraw.Draw(sheet)
        for i, p in enumerate(batch):
            idx = start + i
            try:
                im = ImageOps.exif_transpose(Image.open(p)).convert("RGB")
            except Exception as e:
                manifest.write(f"{idx}\t{p.name}\tUNREADABLE {e}\n")
                continue
            im.thumbnail((CELL - 10, CELL - 30))
            x, y = (i % COLS) * CELL, (i // COLS) * CELL
            sheet.paste(im, (x + 5, y + 25))
            draw.text((x + 5, y + 5), str(idx), fill="red")
            manifest.write(f"{idx}\t{p.name}\n")
        sheet.save(OUT / f"sheet_{start // (COLS * ROWS):02d}.jpg", quality=85)
print(f"{len(imgs)} photos -> {len(list(OUT.glob('sheet_*.jpg')))} sheets")
```

- [ ] **Step 2: Run it**

Run: `cd /home/gilad/Projects/just-bake && python3 tools/contact_sheets.py`
Expected: `210 photos -> 11 sheets` (count may differ by ±1; no traceback)

- [ ] **Step 3: Curate**

View every `tools/contact_sheets/sheet_*.jpg` with the Read tool. Using the red index numbers and `tools/contact_sheets/manifest.txt`, shortlist the best photo per slot below (sharp, well-lit, appetite-driven; verify finalists by Reading the original full-size file before deciding):

| Slot (output filename) | What to look for | Count |
|---|---|---|
| `hero-*.jpg` | The single most appetizing wide shot — finished pizza, fire/oven, or hands stretching dough | 1–2 |
| `kit-*.jpg` | The packed מארז: dough balls, cheese, sauce laid out | 2–3 |
| `dough-*.jpg` | Close-up of dough balls / open crumb | 1–2 |
| `calzone-*.jpg` | Chocolate calzone (repo also has `calzone_real_*.png` as fallback) | 1–2 |
| `gf-*.jpg` | Anything distinguishing the GF line, else a second product shot | 1 |
| `workshop-*.jpg` | People baking together, kids involved, action | 2–3 |
| `bake-*.jpg` | Oven/taboon action shots for section backgrounds | 2–3 |

- [ ] **Step 4: Write the optimizer with the chosen picks**

Create `tools/optimize.py`, filling `PICKS` with the curated selections (output name → source filename from manifest):

```python
#!/usr/bin/env python3
"""Resize + compress curated picks into website/assets/."""
from PIL import Image, ImageOps
from pathlib import Path

SRC = Path("JustBake-photo-videos/פשוט לאפות - תמונות וסרטונים")
DST = Path("website/assets")
DST.mkdir(parents=True, exist_ok=True)

PICKS = {
    # "hero-pizza.jpg": "026b2c51-....JPEG",   <- fill from curation, ~12-16 entries
}

for out, src in PICKS.items():
    im = ImageOps.exif_transpose(Image.open(SRC / src)).convert("RGB")
    im.thumbnail((1600, 1600))
    im.save(DST / out, "JPEG", quality=80, optimize=True)
    print(out, im.size, f"{(DST / out).stat().st_size // 1024}KB")
```

- [ ] **Step 5: Run and sanity-check**

Run: `python3 tools/optimize.py && du -sh website/assets/`
Expected: one line per pick, each ≤ ~400KB; total folder ≤ ~4MB. View 2–3 outputs with Read to confirm orientation is correct (EXIF rotation applied).

- [ ] **Step 6: Commit**

```bash
git add website/assets/
git commit -m "Website: curated, optimized real photos"
```

---

### Task 3: Content spec file for variant agents

**Files:**
- Create: `website/content-spec.md`

- [ ] **Step 1: Write the file**

Create `website/content-spec.md` with exactly this content (facts are binding for every variant; section order/design is free):

````markdown
# פשוט לאפות — Website Content Spec (binding facts)

Site language: Hebrew, `dir="rtl"`. One action: order via WhatsApp.
WhatsApp link everywhere: https://wa.me/972525800797?text=%D7%94%D7%99%D7%99%2C%20%D7%90%D7%A9%D7%9E%D7%97%20%D7%9C%D7%94%D7%96%D7%9E%D7%99%D7%9F%20%D7%9E%D7%90%D7%A8%D7%96
(prefill = "היי, אשמח להזמין מארז" — placeholder, may be swapped later)

## Copy rules (binding)
1. Kits are מארז or ערכה — never קונטיינרים/קופסאות/containers.
2. Spoken Hebrew (עברית מדוברת) — concrete, physical, sensory. No poetry, no speeches.
3. No slogans, no clunky CTAs. State the offer plainly and stop. Voice: דוגרי.
4. Dough is sold FROZEN and needs hours to thaw. NEVER imply minutes-from-freezer.
   Value prop: the hard work is done — לישה והתפחה של 48 שעות (regular dough only;
   do NOT claim 48h for the gluten-free version). אתם רק פותחים ואופים.

## Sections (order/design = your call; facts = fixed)

### Hero
פשוט לאפות — בצק נאפוליטני אמיתי, קפוא, מוכן לאפייה בבית. + WhatsApp CTA.

### מארזים
- ערכה נאפוליטנית — 5 בצקים + 5 גבינות + רוטב — 130 ₪
- ערכה כוסמין — 5 בצקים + 5 גבינות + רוטב — 150 ₪
- ערכה ללא גלוטן — 5 בצקים + 5 גבינות + רוטב + קמח פתיחה ללא גלוטן — 160 ₪ מחיר השקה (מחיר רגיל 180 ₪)
- מארז משודרג — מארז נאפוליטני + קלצונה שוקולד — 150 ₪
- שילוב בצקים — מחיר לפי התאמה
Calzone copy: narrative says "שוקולד נמס"; the word מילקה appears ONLY in the
price/detail line. Also sold separately: בצק + שוקולד מילקה — 25 ₪.

### הרכבה עצמית
כדור נאפוליטני 12 ₪ · כדור כוסמין 17 ₪ · כדור ללא גלוטן 22 ₪ (5 כדורים — 100 ₪) ·
כדור מוצרלה 12 ₪ · רוטב עגבניות 25 ₪ · רוטב לבן 50 ₪ · קמח לפתיחה 5 ₪

### ללא גלוטן
- Personal, first-person: לבן של גלעד יש צליאק — הבצק ללא גלוטן נולד בשבילו.
- Facts, plainly: הבצק ללא גלוטן מוכן בהפרדה מלאה — כלים, משטחים וזמנים נפרדים.
  FORBIDDEN: "בטוח לצליאקים" or any certification claim.
- שתי גרסאות: עם עמילן חיטה ובלי עמילן חיטה.
- הזמנה יומיים מראש (גם כוסמין).
- אפשר לשלב במארז בצקים רגילים לשאר המשפחה — נארזים בנפרד.

### סדנאות
Experience tone, real photos, own WhatsApp CTA. No dates/prices — "פרטים בוואטסאפ".

### איך זה עובד / לוגיסטיקה
- הזמנות בוואטסאפ בלבד — 052-5800797
- הבצקים מגיעים קפואים — מפשירים כמה שעות מראש, פותחים ואופים
- איסוף גמיש מרעננה (בית של גלעד); משלוח להזמנות מרוכזות בלבד (בניין/קבוצה)
- אין מינימום הזמנה
- ללא גלוטן וכוסמין — הזמנה יומיים מראש
- אין ביטול על בצק קפוא שהופשר

## Images
Use ONLY files from `assets/` (relative paths). Every <img> gets Hebrew alt text.
````

**Note on the pickup city:** the spec source says "Gilad's home" without a city. Before writing this file, confirm the city with `grep -rh "איסוף" posts/approved/ | head -5`; if the approved posts name a different city than רעננה, use that one, and if none is found write "איסוף עצמי — הכתובת נשלחת בוואטסאפ".

- [ ] **Step 2: Commit**

```bash
git add website/content-spec.md
git commit -m "Website: content spec for variant agents"
```

---

### Task 4: The "eyes" — Playwright screenshot + error script

**Files:**
- Create: `tools/eyes.py`

- [ ] **Step 1: Write the script**

Create `tools/eyes.py`:

```python
#!/usr/bin/env python3
"""Serve an HTML file locally, screenshot it (mobile + desktop, full page),
and report console errors / failed requests.

Usage: python3 tools/eyes.py website/variant_a.html
Output: tools/shots/<stem>/mobile.png, desktop.png; exit 1 on any error."""
import functools
import http.server
import socketserver
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

html = Path(sys.argv[1]).resolve()
outdir = Path(__file__).parent / "shots" / html.stem
outdir.mkdir(parents=True, exist_ok=True)

handler = functools.partial(
    http.server.SimpleHTTPRequestHandler, directory=str(html.parent))
socketserver.TCPServer.allow_reuse_address = True
server = socketserver.TCPServer(("127.0.0.1", 0), handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{server.server_address[1]}/{html.name}"

errors, failures = [], []
with sync_playwright() as p:
    browser = p.chromium.launch()
    for label, w, h in [("mobile", 390, 844), ("desktop", 1440, 900)]:
        page = browser.new_page(viewport={"width": w, "height": h})
        page.on("console",
                lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("requestfailed", lambda r: failures.append(r.url))
        page.goto(url, wait_until="networkidle")
        page.wait_for_timeout(1500)
        page.screenshot(path=str(outdir / f"{label}.png"), full_page=True)
        page.close()
    browser.close()
server.shutdown()

print(f"shots: {outdir}")
print(f"console errors: {len(errors)}")
for e in errors:
    print("  ERR", e[:200])
print(f"failed requests: {len(failures)}")
for f in failures:
    print("  FAIL", f[:200])
sys.exit(1 if errors or failures else 0)
```

- [ ] **Step 2: Verify it fails/passes correctly against the old draft**

Run: `python3 tools/eyes.py website/index.html && echo CLEAN || echo DIRTY`
Expected: prints `shots: .../tools/shots/index`, error/failure counts, then CLEAN or DIRTY — either is fine; what matters is two PNGs exist:
Run: `ls tools/shots/index/`
Expected: `desktop.png  mobile.png`

- [ ] **Step 3: Look at the screenshots**

Read `tools/shots/index/mobile.png` and `desktop.png` with the Read tool — confirm the page rendered (not blank), proving the loop works end-to-end. No commit (tools/ is gitignored).

---

### Task 5: Three design-variant agents (parallel)

**Files:**
- Create: `website/variant_a.html`, `website/variant_b.html`, `website/variant_c.html` (one per agent)

- [ ] **Step 1: Dispatch 3 agents IN PARALLEL** (single message, three Agent calls, `subagent_type: general-purpose`)

Use this prompt template, substituting `{X}` (a/b/c) and `{SEED}`:

````text
You are building ONE design variant of a real business website. Work from
/home/gilad/Projects/just-bake.

READ FIRST (binding): website/content-spec.md — all facts, prices, copy rules.
Also run `ls website/assets/` to see the real photos you must use.

BUILD: website/variant_{X}.html — a COMPLETE single-file Hebrew RTL one-page
site (inline CSS/JS; only external resource allowed: Google Fonts). Mobile-first.
Images: relative paths into assets/ only.

YOUR DESIGN SEED — total creative freedom within it: {SEED}

YOU HAVE EYES — USE THEM. After EVERY meaningful change:
1. Run: python3 tools/eyes.py website/variant_{X}.html
2. Read tools/shots/variant_{X}/mobile.png and desktop.png and actually look.
An agent that does not look at its screenshots will produce a bad site.

NOT DONE until three passes are complete:
- Pass 1 — works: exit code 0 from eyes.py (zero console errors, zero failed
  requests), correct RTL, all images load.
- Pass 2 — impressive: review your screenshots with a merciless art-director
  eye. Depth, hierarchy, atmosphere, microinteractions. If the mobile
  screenshot would not stop a scrolling Facebook user, keep working.
- Pass 3 — flawless: typography rhythm, palette cohesion, spacing consistency,
  WhatsApp CTA visible without scrolling AND sticky/floating throughout.

HARD CONSTRAINTS: every fact and price exactly as in content-spec.md; the four
copy rules are non-negotiable; wa.me link exactly as given there; no lorem
ipsum; no invented products, dates, or claims.

Do NOT touch any file except website/variant_{X}.html. Do not commit.

RETURN: 2-3 sentences — design direction taken, and the final eyes.py result.
````

Seeds:
- `{X}=a`, `{SEED}`: "Warm artisanal Napoli — flour textures, cream/terracotta palette, craft feel, generous serif-accented Hebrew type (e.g. Frank Ruhl Libre for headings, Heebo for body). The feeling: a small real bakery, fire and hands."
- `{X}=b`, `{SEED}`: "Bold appetite-driven dark — near-black background, food photography glowing out of it, hot orange/red accents, big confident type. The feeling: hunger. Make the photos the heroes."
- `{X}=c`, `{SEED}`: "Clean modern minimal — airy white, strong grid, price-forward cards, one accent color, type-led (Heebo only). The feeling: clarity — see product, see price, tap WhatsApp in 5 seconds."

- [ ] **Step 2: Verify all three variants pass eyes**

Run for each: `python3 tools/eyes.py website/variant_a.html; python3 tools/eyes.py website/variant_b.html; python3 tools/eyes.py website/variant_c.html`
Expected: exit 0, `console errors: 0`, `failed requests: 0` for all three. If a variant fails, send the failure output back to a fresh agent with the same seed prompt plus the error report.

- [ ] **Step 3: Spot-check facts in each variant**

Run: `for v in a b c; do echo "== $v"; grep -o "130 ₪\|150 ₪\|160 ₪\|180 ₪\|100 ₪\|wa.me/972525800797" website/variant_$v.html | sort | uniq -c; done`
Expected: every variant shows all five prices and ≥2 wa.me links. Also verify the forbidden claim is absent:
Run: `grep -l "בטוח לצליאקים" website/variant_*.html || echo SAFE`
Expected: `SAFE`

- [ ] **Step 4: Commit the variants** (so selection state is recoverable)

```bash
git add website/variant_a.html website/variant_b.html website/variant_c.html
git commit -m "Website: three design variants for selection"
```

---

### Task 6: Gilad picks the winner

- [ ] **Step 1: Present the variants**

Read all six final screenshots (`tools/shots/variant_{a,b,c}/{mobile,desktop}.png`) yourself, write a 1-2 sentence honest assessment of each variant, and give Gilad:
- the three assessments,
- file paths to open the variants in his browser (`file:///home/gilad/Projects/just-bake/website/variant_a.html` etc.),
- an AskUserQuestion: "Which variant wins?" with options A / B / C / "mix — tell me what to combine".

- [ ] **Step 2: Record the choice**

No file changes; the answer feeds Task 7. If "mix", capture exactly which sections/elements come from which variant.

---

### Task 7: Polish winner, finalize, clean up

**Files:**
- Modify: `website/index.html` (replaced by winner)
- Delete: `website/variant_*.html`, `tools/`

- [ ] **Step 1: Final flawless pass on the winner**

Dispatch one agent: same eyes-loop prompt as Task 5 but scoped to the winning file, with instructions: apply Gilad's mix/feedback if any, then run the full verification checklist from the spec — prices exact, wa.me links correct with URL-encoded prefill, RTL at 390px/1440px, zero console errors, copy rules pass.

- [ ] **Step 2: Promote winner to index.html**

```bash
cp website/variant_<winner>.html website/index.html
python3 tools/eyes.py website/index.html
```
Expected: exit 0. Read the two final screenshots one last time — confirm nothing broke in the copy.

- [ ] **Step 3: Clean up temp artifacts** (git hygiene: no temp scripts/variants remain)

```bash
git rm website/variant_a.html website/variant_b.html website/variant_c.html
rm -rf tools/
```

- [ ] **Step 4: Commit the final site**

```bash
git add website/index.html
git commit -m "Website: final one-page site — <winner seed name> design"
```

- [ ] **Step 5: Report to Gilad**

Show the final mobile screenshot inline, restate that hosting is deferred (file works on any static host), and remind him the WhatsApp prefill is still the placeholder — one-line swap when he sends his wording.

# Just Bake One-Page Website — Design Spec

Date: 2026-07-22
Status: Approved by Gilad (approach A: 3 parallel design variants)

## Goal

One customer-facing website for פשוט לאפות (Just Bake). Its single job: a visitor
arriving from a Facebook group post or WhatsApp bio link understands what's sold,
at what price, and taps a WhatsApp button to order. No cart, no checkout — the
site is a funnel into WhatsApp (052-5800797), which is the proven sales channel.

## Deliverable

- One self-contained static `index.html` — inline CSS/JS, no framework, no build
  step, no external dependencies except Google Fonts.
- Hebrew, `dir="rtl"`, mobile-first (most traffic comes from Facebook on phones).
- Final winner replaces `website/index.html`. Variant files and tooling are
  removed after the winner is chosen (git hygiene: no temp artifacts committed).
- Hosting: none for now — built and verified locally. File must work when
  deployed to any static host later (GitHub Pages / Netlify) with zero changes.

## Content spec (identical facts across all variants)

Order of sections is a design decision per variant; facts are not.

### Hero
- Brand: פשוט לאפות
- One plain-language line about the product (see copy rules). WhatsApp CTA button.

### Kits (מארזים / ערכות)
| Product | Price |
|---|---|
| ערכה נאפוליטנית — 5 בצקים + 5 גבינות + רוטב | 130 ₪ |
| ערכה כוסמין — 5 בצקים + 5 גבינות + רוטב | 150 ₪ |
| ערכה ללא גלוטן — 5 בצקים + 5 גבינות + רוטב + קמח פתיחה ללא גלוטן | 160 ₪ מחיר השקה (180 ₪ מחיר רגיל) |
| מארז משודרג — מארז נאפוליטני + קלצונה שוקולד | 150 ₪ |
| שילוב בצקים | מחיר לפי התאמה |

Chocolate calzone note: story copy says "שוקולד נמס"; "מילקה" appears only in
the price/detail line. Sold separately: בצק + שוקולד מילקה — 25 ₪.

### Individual items (הרכבה עצמית)
כדור נאפוליטני 12 ₪ · כדור כוסמין 17 ₪ · כדור ללא גלוטן 22 ₪ (5 כדורים — 100 ₪;
confirmed by Gilad 22/07/2026) · כדור מוצרלה 12 ₪ · רוטב עגבניות 25 ₪ ·
רוטב לבן 50 ₪ · קמח לפתיחה 5 ₪

### Gluten-free section
- Personal story: Gilad's son was diagnosed with celiac (approved for public use).
- Facts stated plainly: GF dough prepared in full separation — separate tools,
  surfaces, and times. NEVER claim "בטוח לצליאקים" or any certification.
- Two GF versions: with wheat starch and without — always mention both.
- GF and spelt require ordering 2 days ahead.
- A kit can mix regular dough balls for the rest of the family, packed separately.
- Do not mention 48h proofing for the GF version (unverified).

### Workshops
- Section with real photos and its own WhatsApp CTA. Experience-focused tone.
- No dates/pricing hardcoded (they change) — "פרטים בוואטסאפ".

### Logistics
- הזמנות בוואטסאפ בלבד — 052-5800797
- איסוף גמיש מהבית של גלעד; משלוח להזמנות מרוכזות בלבד (בניין/קבוצה)
- אין מינימום הזמנה
- ללא גלוטן וכוסמין — הזמנה יומיים מראש
- ביטולים: אין ביטול על קפוא שהופשר

### WhatsApp CTA
- Sticky/floating WhatsApp button on all viewports.
- Link format: `https://wa.me/972525800797?text=<URL-encoded Hebrew prefill>`
- Prefill message text: written by Gilad (his sales voice) — placeholder
  `היי, אשמח להזמין מארז` until he provides his own wording.

## Copy rules (binding for all variants)

1. **Terminology**: kits are מארז or ערכה — never קונטיינרים/קופסאות/containers.
2. **Spoken Hebrew** (עברית מדוברת): concrete, physical, sensory. If it sounds
   like a speech or poem, rewrite it.
3. **No slogans, no clunky CTAs**: state the offer plainly and stop. Brand voice
   is דוגרי and matter-of-fact. Short beats storytelling.
4. **Frozen dough truth**: dough is sold frozen and needs hours to thaw. Never
   imply "minutes from freezer to pizza". Value prop = the hard work is done
   (kneading, 48h proofing for regular dough) — you thaw, open, and bake.

## Process

1. **Content file**: `website/content-spec.md` distilled from this doc — the
   single source of facts handed to every variant agent.
2. **Eyes**: one shared Playwright script — serves a variant locally, captures
   mobile (390px) + desktop (1440px) + full-page scroll screenshots, reports
   console errors and failed requests. Agents must look at their screenshots
   after every change.
3. **3 parallel variant agents**, each with total creative freedom over a seed:
   - Seed A: warm artisanal Napoli (flour, fire, craft)
   - Seed B: bold dark appetite-driven (contrast, close-up food, heat)
   - Seed C: clean modern minimal (type-led, airy, price-forward)
   Output: `website/variant_a.html`, `variant_b.html`, `variant_c.html`.
4. **3 passes per variant** (no variant is done before all three):
   - Pass 1 — works: zero console errors, zero failed requests, RTL correct.
   - Pass 2 — impressive: merciless art-director review of own screenshots.
   - Pass 3 — flawless: typography rhythm, palette cohesion, mobile polish.
5. **Selection**: final screenshots of all variants presented to Gilad; he picks.
6. **Winner polish**: one final flawless pass, then winner becomes
   `website/index.html`; variants and temp tooling deleted.

## Photos

Source: `JustBake-photo-videos/פשוט לאפות - תמונות וסרטונים/` — 271 files,
2.6 GB, photos + videos with UUID names. Handling:

1. **Gitignore the source folder** — 2.6 GB of raw media never enters git.
2. **Curation pass** (before variants start): view the photos, shortlist the
   best per section — hero, kits/products, GF, chocolate calzone, workshops,
   baking-action shots. Prefer sharp, well-lit, appetite-driven shots.
3. **Optimize**: copy shortlisted photos to `website/assets/` with descriptive
   names (e.g. `hero-pizza-oven.jpg`), resized to max 1600px wide, JPEG ~80
   quality. Only these optimized copies are committed.
4. Variants reference only `website/assets/` images, relatively.
5. Videos are out of scope for v1 (a muted hero video loop is a possible later
   upgrade — noted, not built).

## Verification checklist (winner must pass)

- Zero console errors / failed requests in Playwright run.
- Correct RTL rendering at 390px and 1440px.
- All WhatsApp links: correct number (972525800797) and URL-encoded prefill.
- All prices match this spec exactly.
- Copy passes the 4 copy rules.
- All images load from `website/assets/`; raw media folder is gitignored.

## Out of scope

- Hosting/deployment, custom domain (deferred by Gilad).
- Online payment, cart, order forms — WhatsApp only.
- 3D/WebGL showcase elements from the original promptWeb.txt.
- Integration with Google Sheets / Streamlit (internal tools stay separate).

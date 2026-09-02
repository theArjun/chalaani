# चलानी · chalaani

A multi-tenant register for **delivery chalani** (चलानी / डेलिभरी चलान) — the paper
slips a supplier sends along with goods. Photograph the slip, let Claude read it,
have a clerk confirm the two things that matter (which supplier, which catalog
item), and the vendor-wise and item-wise totals fall out for free.

Built for how these slips actually look in Nepal: Bikram Sambat dates, Devanagari
digits and names, lakh/crore money, बोरा / थान / वर्ग फिट units, PAN numbers,
Shrawan–Ashad fiscal years.

## Stack

| Layer | Choice |
| --- | --- |
| Web | Django 6.1, one template per screen |
| Interactivity | HTMX 2 + Django's native `{% partialdef %}` (no build step, no SPA) |
| Styling | Tailwind 4 + daisyUI 5 (CDN while prototyping, standalone binary for prod) |
| Extraction | LangChain `ChatAnthropic(...).with_structured_output(ChalaniExtraction)` |
| Jobs | Django-Q2 on the ORM broker (no Redis) |
| Storage | SQLite + a `MEDIA_ROOT` outside the repo, served only through an org-checked view |
| Dates | `nepali-datetime`, wrapped in `nepal/dates.py` |
| Language | Django i18n — नेपाली (default) and English, switched from the navbar |

## Run it

```bash
uv sync
cp .env.example .env          # add ANTHROPIC_API_KEY to use the AI reading
uv run python manage.py migrate
uv run python manage.py seed_demo     # demo firm, 5 suppliers, 24 chalani
uv run python manage.py runserver
```

Log in as **demo / demo12345**, or create your own firm at `/accounts/signup/`.

For AI extraction, run the worker next to the web process:

```bash
uv run python manage.py qcluster
```

…or set `Q_SYNC=1` to read photos inline (blocks the upload request — demo only).
To read one chalani without a worker at all:

```bash
uv run python manage.py extract_chalani 12
```

## How a chalani moves

```
photo upload ──▶ extracting ──▶ draft ──▶ verified ──▶ billed
                    │             ▲          │
              Claude reads it     │      unique (org, vendor, chalani_no)
              (background)        └── clerk fixes the vendor/item links
```

* **`description` keeps what the paper said. `item` is the catalog link a clerk
  sets during verification.** That split is what makes vendor-wise reporting
  possible without falsifying the slip.
* Matching is deliberately conservative (PAN first, then exact name, then a
  0.86-cutoff fuzzy match across both Devanagari and romanised names). Anything
  below the bar stays unlinked and the verify screen asks a human — a wrong
  vendor link is far more expensive than an unlinked draft.
* The uniqueness constraint applies **only to verified/billed** chalani, and
  exempts blank numbers, so an AI draft with a misread number never blocks a
  save and several numberless drafts can coexist.
* Extraction failures always land on an editable draft with the error shown,
  never a 500.

## Language: नेपाली / English

The whole UI is translatable through Django's own i18n machinery — `LocaleMiddleware`,
`gettext_lazy` in Python, `{% translate %}` in templates, a catalog in
`locale/ne/LC_MESSAGES/`. English is the msgid language, Nepali the translation.
The navbar has a switcher that posts to `django.views.i18n.set_language`, so the
choice sticks in a cookie; a first-time visitor gets Nepali (`LANGUAGE_CODE=ne`),
or whatever `Accept-Language` asks for.

**Switching the UI to English does not switch the calendar.** Bikram Sambat stays
the headline date everywhere — only the script changes:

| | नेपाली | English |
| --- | --- | --- |
| Date | १७ भदौ २०८२ | 17 Bhadau 2082 |
| Long date | मंगलबार, १७ भदौ २०८२ | Mangalbar, 17 Bhadau 2082 |
| Money | रू. १२,३४,५६७.५० | Rs. 12,34,567.50 |
| In words | बाह्र लाख चौँतिस हजार … | twelve lakh thirty-four thousand … |
| Unit | बोरा | Bag / Sack |
| Relative | २४ दिन अघि | 24 days ago |

The Gregorian date is kept as a small annotation (and as the `title=` tooltip),
never as the primary reading. Every list and detail view also shows a relative
age — `24 days ago` / `२४ दिन अघि` — next to the absolute date, via the `|ago`
filter, which localises its own plurals.

After changing any user-facing string:

```bash
uv run python manage.py makemessages -l ne --ignore=.venv
# translate the new msgids in locale/ne/LC_MESSAGES/django.po
uv run python manage.py compilemessages -l ne --ignore=.venv
```

## Nepali support

`nepal/` is a self-contained app you could lift into another project:

| Module | What it does |
| --- | --- |
| `dates.py` | BS↔AD, `२०८२।०५।१७` parsing, `१७ भदौ २०८२` display, fiscal years (`2082/83`) and their AD bounds |
| `numbers.py` | `12,34,567.50` lakh/crore grouping, Devanagari digits, `एक हजार दुई सय पचास रुपैयाँ मात्र` |
| `units.py` | Canonical units with alias folding: `Bora`/`बोरा`/`bags`/`sack` → `bag` |
| `validators.py` | 9-digit PAN, Nepali mobile/landline, permissive vehicle plates |
| `forms.py` | `BikramSambatDateField` + an HTMX input that previews the AD date as you type |
| `templatetags/nepal.py` | Language-aware filters: `\|bs_date` `\|bs_date_long` `\|money` `\|num` `\|qty` `\|in_words` `\|unit_label` `\|fy` `\|ago` |

Dates are stored as an AD `DateField` (so ordering, ranges and reports are plain
SQL) with the BS string kept alongside exactly as written; `Chalani.sync_dates()`
keeps the two and the fiscal year consistent, and treats the BS string as
authoritative because that is what the paper says.

## Photos are not public

`MEDIA_ROOT` sits outside the repo (`~/.chalaani/media` by default) and
`MEDIA_URL` is deliberately `None`. Uploads are stored at
`chalani/<org_id>/<uuid>.<ext>` and served **only** by `chalani:photo`, which
resolves the chalani through the caller's organization first. Back up
`MEDIA_ROOT` together with the database — one is useless without the other.

## Extraction

`extraction/schema.py` is the whole contract; `extraction/prompts.py` carries the
Nepali-specific instructions (script fidelity, BS dates, Devanagari digits, unit
names, never compute a missing number). The call is:

```python
ChatAnthropic(model="claude-opus-5", ...).with_structured_output(
    ChalaniExtraction, method="json_schema"
).invoke([SystemMessage(...), HumanMessage(content=[image_block, text_block])])
```

Every field is optional on purpose: a `null` a clerk fills in beats a confident
guess that silently enters the books.

## Production notes

* Tailwind without Node — download the standalone binary, then
  `./tailwindcss -i static/css/app.css -o static/css/build.css --minify`, set
  `CHALAANI_TAILWIND_CDN=0`, and `collectstatic`.
* Run `manage.py qcluster` under the same supervisor as the web process.
* Set `DJANGO_DEBUG=0`, a real `DJANGO_SECRET_KEY`, and `DJANGO_ALLOWED_HOSTS`.
* SQLite is in WAL mode and is fine for a single server; the models carry no
  Postgres-specific features if you outgrow it.

## Tests

```bash
uv run python manage.py test
```

Covers BS/AD conversion and fiscal-year edges, lakh/crore formatting, unit
folding, tenancy isolation (including photo access), the partial-unique
constraint, extraction application and its failure path, the HTMX fragments, the
verify/role rules, and localisation — including the rule that an English UI still
renders Bikram Sambat dates.

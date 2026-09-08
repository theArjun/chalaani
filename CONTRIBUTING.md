# Contributing to चलानी · chalaani

Thanks for taking the time. Issues, bug reports, translation fixes and pull
requests are all welcome. Everyone taking part is expected to follow the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Getting set up

You need Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/theArjun/chalaani.git
cd chalaani

uv sync
cp .env.example .env
uv run python manage.py migrate
uv run python manage.py seed_demo     # demo firm, 5 suppliers, 24 chalani
uv run python manage.py runserver
```

Log in as `demo` / `demo12345`.

An `ANTHROPIC_API_KEY` is optional. Without one, AI reading of photos is off and
you enter slips by hand — plenty for most changes. If you are working on
extraction, set the key and either run `manage.py qcluster` alongside the server
or set `Q_SYNC=1` to read photos inline.

## Before you open a pull request

Run the test suite:

```bash
uv run python manage.py test
```

It must pass. The same command runs in CI on every push and pull request.

If you touched anything user-facing, also:

- **Add a test.** Tenancy, dates, numbers, and the MCP surface are all covered
  today; keep it that way.
- **Update the translations.** Every string a user can read goes through
  `gettext_lazy` in Python or `{% translate %}` in templates. English is the
  msgid language, Nepali the translation:

  ```bash
  uv run python manage.py makemessages -l ne --ignore=.venv
  # translate the new msgids in locale/ne/LC_MESSAGES/django.po
  uv run python manage.py compilemessages -l ne --ignore=.venv
  ```

  Commit both the `.po` and the compiled `.mo`.

- **Check both languages and both themes.** Switch the UI to English and confirm
  dates still render as Bikram Sambat, then toggle light and dark.

## House rules

A few decisions in this codebase are deliberate. If a change works against one of
them, say why in the pull request:

- **Bikram Sambat is the headline date**, in both languages. The Gregorian date is
  an annotation, never the primary reading.
- **`description` keeps what the paper said; `item` is the catalog link a clerk
  sets.** Do not overwrite one with the other.
- **Vendor matching stays conservative.** An unlinked draft that asks a human is
  cheaper than a wrong vendor link.
- **Extraction never raises to the user.** A failure lands on an editable draft
  with the error shown.
- **Tenancy is enforced at the query, not the template.** Anything that reads
  organization data goes through the org-scoped managers and mixins, and that
  includes photo access.
- **No build step.** HTMX and Django partials, not an SPA. Please do not add a
  Node toolchain to the request path.

## Commits and pull requests

- Keep commits focused and write messages in the imperative mood
  (`add fiscal-year filter to vendor report`).
- Describe *why* in the pull request body, not just what. Screenshots help for UI
  changes; a before/after helps more.
- Small pull requests get reviewed faster. If a change is large or changes one of
  the house rules above, open an issue first so we can agree on the shape.

## Reporting bugs

Use the issue templates. For anything security-related, do **not** open a public
issue — see [SECURITY.md](SECURITY.md).

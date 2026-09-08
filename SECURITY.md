# Security policy

## Supported versions

This project is pre-1.0. Only the `main` branch receives security fixes.

## Reporting a vulnerability

**Please do not open a public issue for a security problem.**

Report it privately through GitHub:
[open a private security advisory](https://github.com/theArjun/chalaani/security/advisories/new).
That page is only visible to the maintainers.

Include what you need to make it reproducible: affected version or commit, the
steps, and what an attacker gets out of it. You should get a first response
within a week. Please give us a reasonable window to ship a fix before disclosing
publicly.

## What is in scope

The parts of this codebase that carry the most weight:

- **Tenancy isolation.** Any path that returns one organization's data to a
  member of another organization — including chalani photos, which are served
  only by an org-checked view.
- **Photo access.** `MEDIA_URL` is deliberately unset and uploads live outside the
  repo. Any way to read a file under `MEDIA_ROOT` without going through
  `chalani:photo` is a vulnerability.
- **Role enforcement.** Verification and other manager-only actions being reachable
  by a staff account.
- **The MCP server.** The organization is pinned at startup and bound into every
  tool, so it never reaches a tool schema. Any way for a caller to reach another
  firm's data, or to write while the server was started without `--allow-writes`,
  is a vulnerability.
- **Authentication, session handling, CSRF, and file upload handling.**

## What is not in scope

- Findings that require a misconfigured deployment: `DJANGO_DEBUG=1` in
  production, a default `DJANGO_SECRET_KEY`, or `DJANGO_ALLOWED_HOSTS=*` on a
  public host. The README's production notes cover these; running against them is
  an operator error, not a code defect.
- The demo data seeded by `manage.py seed_demo`, including its published
  `demo` / `demo12345` credentials. Never run that command on a production
  install.
- Denial of service through sheer volume of uploads.
- Vulnerabilities in dependencies, unless this project's use of them is what makes
  the problem exploitable. Report those upstream.

## Operator notes

If you self-host chalaani, two things carry real data:

- Back up `MEDIA_ROOT` together with the database. One is useless without the
  other.
- The MCP server is read-only unless you pass `--allow-writes`. Do not pass it
  unless you intend an assistant to be able to change the register.

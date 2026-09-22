# Curiosity Games — App Context for Claude

This app was bootstrapped from `cg-app-template` on the Curiosity Games
internal platform. Below is context every Claude session on this repo
should keep in mind, plus how to pull live platform docs on demand.

## Staying current with the platform template

This app is a point-in-time copy of `TheEscapeKeys/cg-app-template`. The
platform template keeps improving (user management, local preview,
broker helpers, security fixes). The app owner + collaborators were
granted **read access** to the template at bootstrap, so you can compare
and pull updates:

```bash
gh repo clone TheEscapeKeys/cg-app-template /tmp/cg-app-template   # read-only reference
# then diff areas of interest, e.g. the access/auth layer:
diff -ru /tmp/cg-app-template/app app/ | less
```

When the user asks "are we up to date?" or you're about to build
something the template may already solve (per-app user management,
local preview, broker calls), check the template first and offer to
port the relevant improvements in. Don't blindly overwrite their app —
review the diff, bring over what's useful, keep their custom code.

## Where context lives (two sources, both useful)

Your team has knowledge spread across two systems. Use both:

### 1. Anthropic Skills (org-wide, auto-triggered)

Skills like `teg-brand-guide`, `gbgs-brand-guide`, `cosmo-brand-guide`,
`chip-brand-guide`, `adventure-mining-brand-guide` are installed at the
Anthropic-org level. **You don't need to do anything to use these** —
Claude loads them automatically when the conversation calls for them
(e.g., creating designed content for a brand).

Treat these as authoritative for cross-cutting brand + product knowledge.

### 2. Service-app docs + Drive skills (this app, locally cached)

Operational and app-relevant docs that aren't broad enough to be
Anthropic Skills live as local files in this repo, pulled at build time
from the service app:

- **`./platform-docs/*.md`** — long-form platform reference (security
  policy, snowflake infrastructure schema reference, etc.). Run
  `./scripts/fetch-platform-docs.sh` to refresh.
- **`./skills/<slug>/<slug>.md`** + `./skills/<slug>/assets/` — Drive-
  sourced skills the team is actively editing in Google Docs. Run
  `./scripts/fetch-skills.sh` to refresh.

Both refresh on every Railway deploy. Run the fetch scripts manually
when you want updated content mid-development.

**Decision rule — which source for what:**

| If you're... | Look here |
|---|---|
| Building/changing anything (how to work well) | **`./skills/working-habits/working-habits.md`** (house skill, always included — clarify → plan → small steps → verify → review; the habits that prevent wrong-thing-built + half-finished UIs) |
| Building/changing ANY UI — pages, nav, tables, forms, search, layout | **`./skills/app-design-patterns/app-design-patterns.md`** (house skill, always included — UX playbook; read it before building UI) |
| Picking brand colors / fonts / mascots | `./platform-docs/design-system.md` + Anthropic brand skills (auto) |
| Writing copy that mentions Cosmo/Chip/etc. | Anthropic Skill (auto) |
| Querying Snowflake or doing data work | `./platform-docs/snowflake-*.md` |
| Reviewing for launch readiness | `./platform-docs/security-audit.md` |
| Implementing a feature with org-specific procedures | `./skills/<slug>/<slug>.md` |
| Querying upstream data (Snowflake, Capex, Fulcrum) | `./broker_queries.json` — catalog of broker queries this app is allowed to call (slug, params, limits, endpoints). Don't connect to upstream DBs directly. |
| Unsure | List both: `curl -sS -H "Authorization: Bearer $SERVICE_APP_PERMISSIONS_KEY" https://sso.cgdata.app/api/skills/` |

## Standing rules for this codebase

- **SSO is sacred — never remove it.** This app signs in through Curiosity
  Games SSO (`sso.cgdata.app`) — the organization-approved, centrally-managed,
  audited identity system. Never add a parallel/local login, hardcoded
  password, or alternate auth. If a feature seems to need its own login,
  use the SSO identity that's already present.
- **Merging another app into this one?** Our SSO *supersedes* theirs. Rip out
  the other app's auth/login entirely and route everything through Curiosity
  Games SSO. Bring the other app's *features* over; never its auth. Its users
  simply sign in with their `@theescapegame.com` Google account — there's no
  password migration, ever. User access is managed centrally at
  `/admin/people/` on the service app.
- **Run the `security-audit` skill often** — after any feature touching user
  data, input handling, the broker, or auth/permissions, and before any
  significant push. Treat high-severity findings as blocking.
- **Use the org skills, especially brand guides.** Any UI, user-facing copy,
  color/font/layout decision → read + apply the brand skills and
  `./platform-docs/design-system.md`. Don't invent styling; match the brand.
  Check `./skills/` before building anything that likely has an org convention.
- New env vars: add to `.env.example` first.
- Don't paste secrets in chat. Use Railway variables.
- Run `ruff check` and `pytest` before committing.
- **To see UI changes, run the local preview — don't trust the raw file view.**
  The in-editor preview opens `.html` templates as static files (literal
  `{% ... %}` Jinja tags), which is useless. Instead run `bash scripts/dev.sh`:
  it serves the real app on `http://localhost:8000` (real SSO, local SQLite,
  your dev key for data) with auto-reload, and the preview pane is configured
  (`.claude/launch.json`) to point there. See `.env.local.example` for the
  two values you fill in. This is the ONLY supported local run — never
  hand-roll uvicorn/pip/venv/local-Postgres. To verify the *deployed* result,
  open the live Railway URL.

## Things to do first when starting a new task

If the task touches:
- **UI/visual design** — read `./skills/app-design-patterns/app-design-patterns.md` (house UX playbook skill: layout, nav, tables, forms, search, states, responsive) FIRST, then `./platform-docs/design-system.md` for brand colors/fonts. Anthropic brand skills auto-load too. (House skills are pulled by `./scripts/fetch-skills.sh`; they're always included regardless of subscription.)
- **Anything that queries Snowflake** — read `./platform-docs/snowflake-infrastructure.md` before writing queries.
- **Auth / sensitive data / launch readiness** — read `./platform-docs/security-audit.md` before merging.
- **An org-specific procedure that has a Drive skill** — check `./skills/` directory and read the relevant `<slug>.md`.

- **Pulling upstream data via the broker** — read `./broker_queries.json` first to see what your app is allowed to call. Use `POST /api/data/<slug>` (buffered) or `POST /api/data/<slug>/stream` (NDJSON) with your `SERVICE_APP_PERMISSIONS_KEY` as the bearer.

If the local docs / skills / broker catalog feel stale, run `./scripts/fetch-platform-docs.sh && ./scripts/fetch-skills.sh && ./scripts/fetch-broker-queries.sh` to pull current content.

---

## This app: GBGS Custom Content Submission Form

Two halves in one FastAPI app, and the split is the whole design:

- **`/` is public.** No sign-in. External clients submit custom trivia here.
  Treat every request to `/api/submissions` and `/api/stores` as hostile
  input — it is the only part of any Curiosity Games app reachable without SSO.
- **`/review` is behind SSO**, deny-by-default, same as everywhere else.
  `require_reviewer` / `require_editor` / `require_admin` in
  `app/routes_review.py` are the only gate. There is no passcode and there
  must never be one.

**The rules that are easy to break by accident:**

- Never move a `/api/review/*` route out from behind its dependency, and
  never add a new public route without re-reading `app/routes_public.py`
  first — size cap, rate limit, honeypot, timing check, server-side
  validation, in that order.
- `app/games.py` is the single source of truth for what content is valid.
  The browser has its own copy of the limits for live feedback; it is a
  courtesy, not a control. Any change to a field, a limit or a game's shape
  happens in `games.py` first, then in `app/frontend/index.html`.
- `app/csv_export.py` matches real exports out of the trivia database,
  column for column, including the columns this form doesn't collect
  (`flags`, `difficulty`, the Ready, Bet, Go! explanation columns). Those go
  out empty rather than being dropped. Don't "tidy" them away — the import
  on the other end expects the shape.
- The Grid produces **two** files, categories and the Wisdom Wager. They are
  separate imports downstream.

**Where things live:**

| | |
|---|---|
| Game shapes, limits, validation | `app/games.py` |
| CSV formats | `app/csv_export.py` |
| Submission + store tables | `app/content_models.py` |
| Public routes and spam controls | `app/routes_public.py` |
| Producer routes, CSV, spellcheck proxy | `app/routes_review.py` |
| The page itself (one file, both modes) | `app/frontend/index.html` |
| Game screenshots + wordmark | `app/static/img/` |

The front end is plain ES5-ish JavaScript in one file with no build step —
edit it directly. `window.__APP__`, injected by `app/frontend.py`, tells it
which mode to render; it is a UI hint, never the access decision.

Run `security-audit` after anything touching the public endpoints.

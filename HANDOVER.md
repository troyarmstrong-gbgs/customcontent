# GBGS Custom Content Submission Form — going live

The guest form and the producer view, as one Curiosity Games platform app.
This file is the checklist for getting it running; `CLAUDE.md` has the
standing context for anyone (or any Claude session) working on it after.

---

## What this app is

| | |
|---|---|
| `/` | The submission form. **Public — no sign-in.** This is the half external clients use. |
| `/review` | The producer view. **Behind Curiosity Games SSO**, deny-by-default like every other app. |
| `/healthz` | Railway's health check. |

Both halves are the same HTML document; the server decides which one runs
and, more importantly, which API calls it will answer. A guest who pokes
at the page's JavaScript gets 401s, not data.

---

## Bootstrap checklist

1. **Request the app** at `sso.cgdata.app` → `/request-app`, slug
   `gbgs-custom-content`. Bootstrap creates the GitHub repo, the Railway
   project, Postgres, the SSO registration and the public domain.
2. **Push this code** into the repo bootstrap created. It was built from
   `cg-app-template` conventions, so the auth, access and admin layers are
   the standard ones — only `app/games.py`, `app/csv_export.py`,
   `app/content_models.py`, `app/routes_public.py`, `app/routes_review.py`,
   `app/frontend.py`, `app/frontend/` and `app/static/img/` are new, plus
   small edits to `app/config.py`, `app/db.py` and `app/main.py`.
3. **Set the Railway variables.** Bootstrap sets everything in the first
   block of `.env.example`. Add:
   - `PUBLIC_FORM_ENABLED=true`
   - `ANTHROPIC_API_KEY=` — only if you want the spelling/grammar check.
     Leave blank and the button reports it isn't configured.
4. **Grant your team access.** The app owner is admin automatically. Everyone
   else is `pending` until granted at `/admin/users` on this app. Roles:
   - `viewer` — read submissions, download CSVs
   - `editor` — also edit details, run spellcheck, manage stores
   - `admin` — also delete submissions
5. **Point a real domain at it.** Guests shouldn't see
   `gbgs-custom-content-production.up.railway.app`. Add a custom domain in
   Railway and set `PUBLIC_URL` to match — SSO redirect URIs are built from
   it, so it must be right before anyone signs in.
6. **Check the store list** at `/review` → Manage stores. It seeds with 26
   names on first boot; correct them before the link goes out.

---

## Running it locally

`bash scripts/dev.sh` — the template's one supported local run. It uses
SQLite, real SSO and `http://localhost:8000`. Copy `.env.local.example`
to `.env.local` first.

To exercise the public half without signing in at all, just open `/`.

---

## What I verified before handing this over

Run against SQLite locally, all passing:

- Public form and `/api/stores` answer while signed out.
- `/api/review/*` and the CSV routes return **401** while signed out.
- A full five-game submission stores and returns a reference.
- Server-side validation rejects duplicate answer options, a correct
  answer that matches no option, and an over-length question — each with
  a message naming the game and the row.
- The honeypot field and the minimum fill time both reject.
- A store that isn't on the list is refused.
- Rate limiting trips after 5 submissions from one IP in an hour.
- All six CSV exports match the headers, column counts and quoting of the
  real exports from the database, with `specialEventId` filled from the
  reviewer's field.

---

## Things worth knowing

**Rate limiting is per process.** The counters live in memory in
`app/routes_public.py`. Railway runs this as a single service, so that's
one process and the limits are real. If this app is ever scaled to more
than one replica, the limits multiply by the replica count — move them to
Postgres at that point. The constants are at the top of the file.

**The character limits exist twice, on purpose.** The browser copy in
`app/frontend/index.html` gives live feedback; `app/games.py` is the rule.
If you change a limit, change both — `games.py` is what actually holds.

**`content_json` is a JSON blob, not columns.** Five games with different
shapes would otherwise be five tables and a lot of joins for data nobody
queries analytically. If this content ever needs to reach Snowflake,
that's the point to normalise it — not before.

**Stores are retired, never deleted.** Removing a store sets
`active = False`, so a submission that already named it still reads
correctly.

**No email goes out.** You asked for none — people check the queue. If that
changes, the hook is the end of `api_submit` in `app/routes_public.py`.

**Spam protection is deliberately quiet.** A honeypot field and a minimum
fill time, both invisible to a real person, plus the rate limits. No
CAPTCHA — if bots get through anyway, Cloudflare Turnstile is the next
step and it's a small change to that one endpoint.

---

## What still needs a decision

- **The domain.** Nothing else blocks go-live.
- **Retention.** The form collects names and email addresses from members
  of the public. Nothing currently deletes old submissions. Worth agreeing
  a window and adding a scheduled purge before this has been live long.
- **Privacy wording.** A public form collecting contact details usually
  wants a line about what you do with it, and a link to whatever policy
  The Escape Game already publishes.

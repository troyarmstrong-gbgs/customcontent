#!/usr/bin/env bash
# Local preview server — see your edits before pushing.
#
# Runs the app on http://localhost:8000 with auto-reload, using:
#   - real Curiosity Games SSO (you sign in via Google as yourself)
#   - a local SQLite file for this app's own tables (no Postgres needed)
#   - your 7-day Claude DEV KEY for broker data (never the prod key)
#
# Nothing here works in production — it's localhost only. Secrets come
# from .env.local (gitignored); copy .env.local.example to start.
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v uv >/dev/null 2>&1; then
  echo "❌ 'uv' isn't installed. Install it once with:"
  echo "     curl -LsSf https://astral.sh/uv/install.sh | sh"
  echo "   then re-run this script."
  exit 1
fi

# Load local-only config if present.
if [ -f .env.local ]; then
  set -a; . ./.env.local; set +a
fi

# Safe local defaults (only used if .env.local didn't set them).
export DATABASE_URL="${DATABASE_URL:-sqlite+aiosqlite:///./dev.db}"
export PUBLIC_URL="${PUBLIC_URL:-http://localhost:8000}"
export SESSION_SECRET="${SESSION_SECRET:-local-dev-only-not-a-real-secret}"
export PORT="${PORT:-8000}"

if [ -z "${SSO_CLIENT_ID:-}" ]; then
  echo "⚠️  SSO_CLIENT_ID isn't set — sign-in will fail. Put it in .env.local."
  echo "   (It's the app's public client id; pull it with: railway variables --service <slug>)"
fi

echo "▶  Local preview on http://localhost:${PORT}  (real SSO · SQLite · dev-key data)"
# uv reads pyproject.toml and installs deps automatically (incl. the dev
# extra with aiosqlite). No pip, no venv juggling.
exec uv run --extra dev uvicorn app.main:app --reload --port "${PORT}"

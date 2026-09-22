#!/usr/bin/env bash
# Pull the latest platform docs (security policy, design system,
# infrastructure references, etc.) into ./platform-docs/. Run before
# starting a Claude Code session if you want the freshest context.
#
# Requires SERVICE_APP_PERMISSIONS_KEY in env. Set automatically on apps
# bootstrapped by the platform; for local dev, copy from your Railway
# variables.
set -euo pipefail

SERVICE_APP_URL="${SERVICE_APP_URL:-https://sso.cgdata.app}"

if [[ -z "${SERVICE_APP_PERMISSIONS_KEY:-}" ]]; then
  echo "SERVICE_APP_PERMISSIONS_KEY is not set; can't fetch platform docs." >&2
  echo "Set it in your env (copy from Railway) and re-run." >&2
  exit 1
fi

mkdir -p platform-docs

# List all docs.
LIST=$(curl -sS \
  -H "Authorization: Bearer $SERVICE_APP_PERMISSIONS_KEY" \
  "$SERVICE_APP_URL/api/docs/")

# Extract slugs and download each as markdown.
echo "$LIST" | python3 -c "
import json, sys
data = json.load(sys.stdin)
for d in data.get('docs', []):
    print(d['slug'])
" | while read -r slug; do
  echo "  fetching $slug.md"
  curl -sS \
    -H "Authorization: Bearer $SERVICE_APP_PERMISSIONS_KEY" \
    -o "platform-docs/$slug.md" \
    "$SERVICE_APP_URL/api/docs/$slug.md"
done

echo "Done. Docs in ./platform-docs/"

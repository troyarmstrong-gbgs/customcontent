#!/usr/bin/env bash
# Pull the catalog of broker queries this app is allowed to call,
# write to ./broker_queries.json for the app to read at runtime.
#
# Runs at deploy time via railway.json's start command. Same pattern as
# fetch-platform-docs.sh and fetch-skills.sh — pull-on-deploy, no live
# dependency at request time.
#
# What the JSON contains, per query:
#   slug, name, description, database_slug, params_schema,
#   row_limit_default, max_limit, result_mode_hint, endpoints
#
# Apps can use this to introspect what data they have access to without
# bothering the platform admin for an updated list.

set -euo pipefail

SERVICE_APP_URL="${SERVICE_APP_URL:-https://sso.cgdata.app}"

if [[ -z "${SERVICE_APP_PERMISSIONS_KEY:-}" ]]; then
  echo "SERVICE_APP_PERMISSIONS_KEY is not set; can't fetch broker queries." >&2
  echo "Set it in your env (copy from Railway) and re-run." >&2
  exit 0  # don't fail the build; just no catalog locally
fi

OUT_FILE="${1:-broker_queries.json}"

curl -sS \
  -H "Authorization: Bearer $SERVICE_APP_PERMISSIONS_KEY" \
  -o "$OUT_FILE" \
  -w "Broker queries catalog: HTTP %{http_code}, %{size_download} bytes -> $OUT_FILE\n" \
  "$SERVICE_APP_URL/api/data/"

# Quick summary so the build log shows what landed.
if command -v python3 >/dev/null 2>&1; then
  python3 -c "
import json, sys
try:
  d = json.load(open('$OUT_FILE'))
  if 'detail' in d:
    print(f\"  warning: {d['detail']}\")
    sys.exit(0)
  qs = d.get('queries', [])
  print(f\"  {len(qs)} queries available to this app:\")
  for q in qs:
    print(f\"    - {q['slug']:<35} ({q['database_slug']}) — {q['name']}\")
except Exception as e:
  print(f\"  (could not parse $OUT_FILE: {e})\")
"
fi

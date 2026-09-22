#!/usr/bin/env bash
# Pull Drive-sourced skills from the service app into ./skills/<slug>/.
# Each skill becomes a folder with the markdown content + any assets the
# team put in the Drive folder's assets/ subdirectory.
#
# Runs at deploy time via railway.json's build phase. Run manually too
# (`./scripts/fetch-skills.sh`) when you want a fresh copy mid-development.
set -euo pipefail

SERVICE_APP_URL="${SERVICE_APP_URL:-https://sso.cgdata.app}"

if [[ -z "${SERVICE_APP_PERMISSIONS_KEY:-}" ]]; then
  echo "SERVICE_APP_PERMISSIONS_KEY is not set; can't fetch skills." >&2
  echo "Set it in your env (copy from Railway) and re-run." >&2
  exit 0  # don't fail the build; just no skills locally
fi

mkdir -p skills

LIST=$(curl -sS \
  -H "Authorization: Bearer $SERVICE_APP_PERMISSIONS_KEY" \
  "$SERVICE_APP_URL/api/skills/")

# Pull each skill's markdown + every asset under it.
echo "$LIST" | python3 -c "
import json, sys
data = json.load(sys.stdin)
for s in data.get('skills', []):
    print(s['slug'])
" | while read -r slug; do
  echo "  fetching skill: $slug"
  mkdir -p "skills/$slug"
  # Markdown content
  curl -sS \
    -H "Authorization: Bearer $SERVICE_APP_PERMISSIONS_KEY" \
    -o "skills/$slug/$slug.md" \
    "$SERVICE_APP_URL/api/skills/$slug.md"

  # Assets listing -> download each
  ASSETS=$(curl -sS \
    -H "Authorization: Bearer $SERVICE_APP_PERMISSIONS_KEY" \
    "$SERVICE_APP_URL/api/skills/$slug/assets")
  echo "$ASSETS" | python3 -c "
import json, sys
data = json.load(sys.stdin)
for a in data.get('assets', []):
    print(a['filename'])
" | while read -r filename; do
    [[ -z "$filename" ]] && continue
    target="skills/$slug/assets/$filename"
    mkdir -p "$(dirname "$target")"
    # Filename can contain a path (e.g. fonts/x.ttf). URL-encode the slashes carefully.
    encoded=$(python3 -c "import urllib.parse, sys; print(urllib.parse.quote(sys.argv[1], safe='/'))" "$filename")
    curl -sS \
      -H "Authorization: Bearer $SERVICE_APP_PERMISSIONS_KEY" \
      -o "$target" \
      "$SERVICE_APP_URL/api/skills/$slug/assets/$encoded"
  done
done

echo "Done. Skills in ./skills/"

#!/usr/bin/env bash
###############################################################################
# prune-merge-tags.sh
# Delete (or list) every tag that matches the pattern 1###/merge
#
# USAGE
#   ./prune-merge-tags.sh          # dry-run – prints tags that would go
#   ./prune-merge-tags.sh --delete # deletes them locally + on origin
#
# NOTES
#   • Pattern is ^[0-9]{4}/merge$  (adjust TAG_REGEX below if needed).
#   • Fetches first, so remote & local tags are in sync.
###############################################################################
set -euo pipefail

TAG_REGEX='^[0-9]{4}/merge$'
DO_DELETE=0 && [[ "${1:-}" == "--delete" ]] && DO_DELETE=1

echo "⏳  Fetching tags from origin…" >&2
git fetch --tags --prune >/dev/null

mapfile -t TARGETS < <(git tag -l | grep -E "$TAG_REGEX" || true)

if ((${#TARGETS[@]} == 0)); then
  echo "✅  No tags match $TAG_REGEX"
  exit 0
fi

echo "🏷️  Tags matching $TAG_REGEX:"
printf '  %s\n' "${TARGETS[@]}"

if ((DO_DELETE)); then
  echo -e "\n🚨  Deleting the above tags locally and on origin…"
  git tag -d "${TARGETS[@]}"               # local
  git push origin --delete "${TARGETS[@]}" # remote
  echo "🗑️  Done."
else
  echo -e "\n🔎  Dry-run only. Re-run with '--delete' to actually remove them."
fi


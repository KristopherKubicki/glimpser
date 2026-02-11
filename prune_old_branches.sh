#!/usr/bin/env bash
###############################################################################
# prune-old-branches.sh
# Delete (or list) every remote branch whose HEAD commit is an ancestor of
# a given tag – e.g. anything older than v0.2.7 when the repo is at v0.2.9.
#
# USAGE
#   ./prune-old-branches.sh v0.2.7          # dry-run – show what would go
#   ./prune-old-branches.sh v0.2.7 --delete # actually delete them
#
# NOTES
#   • Works on *remote* branches (origin/…) so you don’t need to pull first.
#   • Protects main/common branch names; extend PROTECT_REGEX to taste.
###############################################################################
set -euo pipefail

CUTOFF_TAG="${1:-}"
[[ -z "$CUTOFF_TAG" ]] && {
  echo "Usage: $0 <cutoff-tag> [--delete]" >&2
  exit 1
}
DO_DELETE=0 && [[ "${2:-}" == "--delete" ]] && DO_DELETE=1

PROTECT_REGEX='^(main|master|dev|production|staging)$'

echo "⏳  Fetching all refs & tags…" >&2
git fetch --all --prune --tags >/dev/null

# Find every origin/<branch> whose tip is contained in the cutoff tag
mapfile -t CANDIDATES < <(
  git for-each-ref --format='%(refname)' refs/remotes/origin |
  while read -r fullref; do
    br="${fullref#refs/remotes/origin/}"
    [[ $br =~ $PROTECT_REGEX || $br == "HEAD" ]] && continue
    if git merge-base --is-ancestor "$fullref" "$CUTOFF_TAG"; then
      echo "$br"
    fi
  done
)

if ((${#CANDIDATES[@]} == 0)); then
  echo "✅  No branches are fully merged before $CUTOFF_TAG"
  exit 0
fi

echo "✂️  Branches whose tip commit is an ancestor of $CUTOFF_TAG:"
printf '  %s\n' "${CANDIDATES[@]}"

if ((DO_DELETE)); then
  echo -e "\n🚨  Deleting the above branches from origin…"
  for br in "${CANDIDATES[@]}"; do
    git push origin --delete "$br"
  done
  echo "🗑️  Done."
else
  echo -e "\n🔎  Dry-run only. Re-run with '--delete' to actually remove them."
fi


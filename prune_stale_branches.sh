#!/usr/bin/env bash
###############################################################################
# prune-stale-branches.sh
# List (or delete) origin/<branch> refs that haven't seen a commit in N days.
#
# USAGE
#   ./prune-stale-branches.sh           # dry-run, N=180 days
#   ./prune-stale-branches.sh 120       # dry-run, N=120 days
#   ./prune-stale-branches.sh 120 --delete   # actually delete
#
# HOW IT WORKS
#   • fetches all remote refs so dates are correct
#   • skips protected names (edit PROTECT_REGEX)
#   • compares branch committer date to NOW-N-days
###############################################################################
set -euo pipefail

AGE_DAYS="${1:-180}"           # default “stale” threshold
DO_DELETE=0 && [[ "${2:-}" == "--delete" ]] && DO_DELETE=1
PROTECT_REGEX='^(main|master|dev|production|staging)$'

echo "⏳  Fetching…"; git fetch --all --prune >/dev/null

CUTOFF_TS=$(date -d "$AGE_DAYS days ago" +%s)
mapfile -t CANDIDATES < <(
  git for-each-ref --format='%(refname) %(committerdate:unix)' refs/remotes/origin |
  while read -r fullref ts; do
    br="${fullref#refs/remotes/origin/}"
    [[ $br =~ $PROTECT_REGEX || $br == "HEAD" ]] && continue
    (( ts < CUTOFF_TS )) && echo "$br"
  done
)

if ((${#CANDIDATES[@]} == 0)); then
  echo "✅  No branches older than $AGE_DAYS days."
  exit 0
fi

echo "📜  Branches inactive > $AGE_DAYS days:"
printf '  %s\n' "${CANDIDATES[@]}"

if ((DO_DELETE)); then
  echo -e "\n🚨  Deleting from origin…"
  for br in "${CANDIDATES[@]}"; do
    git push origin --delete "$br"
  done
  echo "🗑️  Done."
else
  echo -e "\n🔎  Dry-run only.  Re-run with '--delete' to remove."
fi


# list all local branches that are strictly behind the tag
git for-each-ref --format='%(refname:short)' refs/heads \
| while read br; do
  if git merge-base --is-ancestor "$br" v0.2.7; then   # fully reachable from tag
     echo "$br";                                       # candidate – print it
  fi
done | grep -vE '^(main|master|dev)$' \                # keep protected names
     xargs -r -I {} git push origin --delete {}

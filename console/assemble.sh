#!/usr/bin/env bash
# Assemble the forge operating console from versioned blocks, stamped with the assembly SHA.
# Dogfoods the console-as-code island. Run from anywhere; resolves the repo root itself.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."   # repo root; console/ is a child of it

# Refuse outside a git repo — there is nothing to stamp against.
git rev-parse --is-inside-work-tree >/dev/null 2>&1 \
  || { echo "refusing to assemble: not a git repository" >&2; exit 1; }
# Refuse to stamp a dirty tree: a commit id that does not contain these exact blocks would be
# a lying stamp — a reader who checks it out and re-assembles gets a different SHA. Fail closed.
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "refusing to assemble: uncommitted changes — commit the blocks first" >&2
  exit 1
fi
# Refuse on case-folded block-name collisions (case-insensitive FS collapses them to one inode).
# Ask git, not the working tree: git's index stays case-sensitive even where the checkout collapsed.
dupes=$(git ls-files 'console/blocks/*.md' | xargs -n1 basename | \
  tr '[:upper:]' '[:lower:]' | sort | uniq -d)
[ -z "$dupes" ] \
  || { echo "refusing to assemble: case-folded block name collision — $dupes" >&2; exit 1; }
# Refuse on an UNTRACKED block: the `cat blocks/*.md` glob would bake it into the lock and
# stamp it at a HEAD that does not contain it — a lying stamp. git diff misses untracked files,
# so this is a separate enforced gate. Commit the block first.
untracked=$(git ls-files --others --exclude-standard -- 'console/blocks/')
[ -z "$untracked" ] \
  || { echo "refusing to assemble: untracked block(s) not committed — $untracked" >&2; exit 1; }

# Concatenate blocks in filename order, stamp the result.
cat console/blocks/*.md > console/console.assembled
SHA=$(shasum -a 256 console/console.assembled | cut -d' ' -f1)
GIT=$(git rev-parse --short HEAD)
{ echo "<!-- console.lock — assembled from $GIT — sha256:$SHA -->"; echo; cat console/console.assembled; } \
  > console/console.lock
rm console/console.assembled
echo "assembled console: sha256:$SHA @ $GIT"

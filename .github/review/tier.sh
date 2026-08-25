#!/usr/bin/env bash
# Deterministic review-tier classifier. No model call — this decides HOW MUCH
# the AI reviewer should look at, never WHAT it should say about the code.
#
# Usage:
#   tier.sh <base-sha> <head-sha>     # prints one of: skip | lite | full
#   tier.sh --selftest                # runs the built-in checks, prints PASS/FAIL
#
# Tiers:
#   full  - diff touches agents/, commands/, skills/, or config/ (the shipped
#           prompt/schema surface), OR changed lines exceed the threshold.
#           Gets the two-pass find+verify review.
#   lite  - everything else that isn't skip. Single-pass review.
#   skip  - every changed file is a plain doc (not one of the four dirs above)
#           and the diff is small enough to plausibly be a typo/wording fix.
#
# The skip heuristic is intentionally conservative: it only fires on doc-only,
# small diffs. Anything touching the actual product surface always gets at
# least "lite". A false "lite" (reviewing a real typo) costs a cheap pass; a
# false "skip" (missing a real doc-drift issue) costs nothing else catches it,
# so the size cap is deliberately tight.
set -euo pipefail

FULL_TIER_DIR_RE='^(agents|commands|skills|config)/'
LINE_THRESHOLD=400
# ponytail: "typo-sized" heuristic — a doc-only diff this small or smaller is
# treated as skip-eligible. Widen if calibration runs (see dry-run mode) show
# real doc-drift findings getting skipped; narrow if skip lets typos through
# that were actually meaningful rewrites.
DOC_SKIP_LINE_THRESHOLD=20

classify() {
  local base="$1" head="$2"
  local changed_files changed_lines f all_md touches_core

  changed_files=$(git diff --name-only "$base" "$head")

  if [ -z "$changed_files" ]; then
    echo "skip"
    return
  fi

  touches_core=false
  while IFS= read -r f; do
    [ -z "$f" ] && continue
    if [[ "$f" =~ $FULL_TIER_DIR_RE ]]; then
      touches_core=true
      break
    fi
  done <<< "$changed_files"

  changed_lines=$(git diff --shortstat "$base" "$head" \
    | grep -oE '[0-9]+ (insertion|deletion)' \
    | grep -oE '[0-9]+' \
    | awk '{s+=$1} END {print s+0}')

  if $touches_core || [ "$changed_lines" -gt "$LINE_THRESHOLD" ]; then
    echo "full"
    return
  fi

  all_md=true
  while IFS= read -r f; do
    [ -z "$f" ] && continue
    case "$f" in
      *.md) ;;
      *) all_md=false; break ;;
    esac
  done <<< "$changed_files"

  if $all_md && [ "$changed_lines" -le "$DOC_SKIP_LINE_THRESHOLD" ]; then
    echo "skip"
    return
  fi

  echo "lite"
}

selftest() {
  # not `local` — the EXIT trap below fires after this function returns, and
  # `set -u` would otherwise choke on a local that already went out of scope.
  tmp=$(mktemp -d)
  trap 'rm -rf "$tmp"' EXIT
  git -C "$tmp" init -q -b main
  git -C "$tmp" config user.email test@example.com
  git -C "$tmp" config user.name test

  mkdir -p "$tmp/agents" "$tmp/docs"
  echo "base" > "$tmp/README.md"
  echo "base" > "$tmp/agents/x.md"
  git -C "$tmp" add -A && git -C "$tmp" commit -q -m base
  local base_sha
  base_sha=$(git -C "$tmp" rev-parse HEAD)

  local fail=0

  # Case 1: touches agents/ -> full, even though it's a 1-line change
  echo "changed" >> "$tmp/agents/x.md"
  git -C "$tmp" commit -aqm "agent tweak"
  got=$(cd "$tmp" && classify "$base_sha" HEAD)
  [ "$got" = full ] || { echo "FAIL: agents/ touch expected full, got $got"; fail=1; }
  git -C "$tmp" reset -q --hard "$base_sha"

  # Case 2: large non-core diff -> full
  for i in $(seq 1 450); do echo "line $i" >> "$tmp/docs/big.md"; done
  git -C "$tmp" add -A && git -C "$tmp" commit -q -m "big doc dump"
  got=$(cd "$tmp" && classify "$base_sha" HEAD)
  [ "$got" = full ] || { echo "FAIL: >400 lines expected full, got $got"; fail=1; }
  git -C "$tmp" reset -q --hard "$base_sha"

  # Case 3: small doc-only tweak -> skip
  echo "typo fix" >> "$tmp/README.md"
  git -C "$tmp" commit -aqm "fix typo"
  got=$(cd "$tmp" && classify "$base_sha" HEAD)
  [ "$got" = skip ] || { echo "FAIL: small doc tweak expected skip, got $got"; fail=1; }
  git -C "$tmp" reset -q --hard "$base_sha"

  # Case 4: non-core, non-doc, modest size -> lite
  mkdir -p "$tmp/eval"
  echo "print(1)" > "$tmp/eval/scratch.py"
  git -C "$tmp" add -A && git -C "$tmp" commit -q -m "eval scratch script"
  got=$(cd "$tmp" && classify "$base_sha" HEAD)
  [ "$got" = lite ] || { echo "FAIL: modest non-doc change expected lite, got $got"; fail=1; }
  git -C "$tmp" reset -q --hard "$base_sha"

  if [ "$fail" -eq 0 ]; then
    echo "PASS: all tier.sh selftest cases"
  else
    exit 1
  fi
}

if [ "${1:-}" = "--selftest" ]; then
  selftest
else
  base="${1:?usage: tier.sh <base-sha> <head-sha> | tier.sh --selftest}"
  head="${2:?usage: tier.sh <base-sha> <head-sha> | tier.sh --selftest}"
  classify "$base" "$head"
fi

#!/usr/bin/env bash
# setup.sh — install career-ops-dk into a career-ops checkout.
#
#   ./setup.sh                      install overlay/ into ../career-ops
#   ./setup.sh --repo PATH          install into a specific checkout
#   ./setup.sh --clone PATH         clone career-ops from canonical, then install
#   ./setup.sh --check              report drift between overlay/ and the checkout
#   ./setup.sh --pull               copy the checkout's overlay files BACK into overlay/
#   ./setup.sh --seed-userdata      ONE-TIME: copy userdata/ into a FRESH checkout
#   ./setup.sh --backup-userdata    copy the LIVE checkout's state back into userdata/
#
# TWO LAYERS, TWO LIFECYCLES — this is the thing to understand:
#
#   overlay/   code. Installed by the default command, as often as you like.
#   userdata/  cv.md, profile, tracker, reports. A SEED, not a sync.
#
# OWNERSHIP: exactly one machine runs the pipeline. Each layer has one writer,
# so the flow is unidirectional and nothing ever merges:
#
#   overlay/   written on the DEV machine  -> push -> pull -> ./setup.sh
#   userdata/  written on the LIVE machine -> ./setup.sh --backup-userdata -> push
#
# The default install NEVER touches userdata/, so pulling a code change can
# never disturb a live tracker. --seed-userdata REFUSES a checkout that already
# has a cv.md: restoring the seed over live state would roll the tracker and
# reports back to the snapshot. Keep --backup-userdata current — it is what makes
# a restore onto a replacement machine safe.
#
# WHY COPIES AND NOT SYMLINKS (learned the hard way, 2026-09-13):
# Both halves break under a symlink, and both break SILENTLY.
#   - providers/jobindex.mjs imports ./_html-entities.mjs. Node resolves a
#     symlinked module's imports against its REALPATH, so the import looked for
#     _html-entities.mjs inside overlay/providers/ and the provider failed to
#     load — scan.mjs just carried on with 87 providers instead of 88.
#   - automation/*.mjs compute ROOT as dirname(import.meta.url)/.. which, via a
#     symlink, is overlay/ rather than the career-ops checkout. pipeline-to-batch
#     reported "0 pending" against a data/pipeline.md holding real URLs.
# Neither raised an error. Copies keep every file's realpath inside the checkout.

set -euo pipefail

CANONICAL="https://github.com/career-ops-hq/career-ops.git"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OVERLAY="$HERE/overlay"
USERDATA="$HERE/userdata"
REPO="$(cd "$HERE/.." && pwd)/career-ops"
MODE=install
FORCE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)           REPO="$2"; shift 2 ;;
    --clone)          REPO="$2"; MODE=clone; shift 2 ;;
    --check)          MODE=check; shift ;;
    --pull)           MODE=pull; shift ;;
    --seed-userdata)  MODE=seed; shift ;;
    --backup-userdata) MODE=backup; shift ;;
    --force)          FORCE=1; shift ;;
    -h|--help)        sed -n '2,30p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown flag: $1" >&2; exit 2 ;;
  esac
done

# Files the overlay owns, discovered from overlay/ rather than hardcoded — a
# list maintained by hand is one that eventually forgets a new file, and a
# forgotten file is one that never reaches the live machine.
mapfile -t FILES < <(cd "$OVERLAY" && find . -type f ! -name '*:Zone.Identifier' \
                     -printf '%P\n' | sort)
[[ ${#FILES[@]} -gt 0 ]] || { echo "overlay/ is empty" >&2; exit 1; }

if [[ "$MODE" == clone ]]; then
  [[ -e "$REPO" ]] && { echo "refusing to clone over an existing path: $REPO" >&2; exit 1; }
  echo "cloning career-ops -> $REPO"
  git clone "$CANONICAL" "$REPO"
  MODE=install
fi

[[ -d "$REPO" ]] || { echo "no career-ops checkout at $REPO (use --repo PATH or --clone PATH)" >&2; exit 1; }
# update-system.mjs refuses to run unless the checkout owns its own .git.
[[ -d "$REPO/.git" ]] || echo "warning: $REPO has no .git of its own — career-ops updates will refuse to run there" >&2

case "$MODE" in
  check)
    drift=0
    for f in "${FILES[@]}"; do
      if [[ ! -e "$REPO/$f" ]]; then echo "MISSING   $f"; drift=1
      elif ! cmp -s "$OVERLAY/$f" "$REPO/$f"; then echo "DRIFTED   $f"; drift=1
      else echo "ok        $f"; fi
    done
    [[ $drift -eq 0 ]] && echo "overlay and $REPO agree" \
                       || echo "run ./setup.sh (overlay wins) or ./setup.sh --pull (checkout wins)"
    exit $drift
    ;;

  pull)
    for f in "${FILES[@]}"; do
      [[ -e "$REPO/$f" ]] || { echo "skip (absent) $f"; continue; }
      mkdir -p "$(dirname "$OVERLAY/$f")"
      cp -p "$REPO/$f" "$OVERLAY/$f"
      echo "pulled    $f"
    done
    ;;

  seed)
    [[ -d "$USERDATA" ]] || { echo "no userdata/ in this repo" >&2; exit 1; }
    if [[ -e "$REPO/cv.md" && $FORCE -eq 0 ]]; then
      echo "refusing: $REPO already has cv.md, so it owns live state." >&2
      echo "The seed would roll its tracker and reports back to this snapshot." >&2
      echo "Use --force only if you really mean to overwrite." >&2
      exit 1
    fi
    ( cd "$USERDATA" && find . -type f -print0 ) | while IFS= read -r -d '' f; do
      mkdir -p "$(dirname "$REPO/${f#./}")"
      cp -p "$USERDATA/${f#./}" "$REPO/${f#./}"
    done
    echo "seeded $(find "$USERDATA" -type f | wc -l) user-layer files into $REPO"
    echo "That machine now owns its own state — do not re-seed it."
    ;;

  backup)
    [[ -e "$REPO/cv.md" ]] || { echo "no cv.md at $REPO — nothing to back up" >&2; exit 1; }
    PATHS=(cv.md voice-dna.md article-digest.md portals.yml config/profile.yml
           modes/_profile.md modes/_custom.md modes/_brief.md)
    DIRS=(data reports output interview-prep)
    n=0
    for f in "${PATHS[@]}"; do
      [[ -e "$REPO/$f" ]] || continue
      mkdir -p "$(dirname "$USERDATA/$f")"; cp -p "$REPO/$f" "$USERDATA/$f"; n=$((n+1))
    done
    for d in "${DIRS[@]}"; do
      [[ -d "$REPO/$d" ]] || continue
      ( cd "$REPO/$d" && find . -type f \
          ! -name '*:Zone.Identifier' ! -name '*.bak' ! -name '.hired-share-state.json' \
          ! -path './cache/*' ! -path './parser-output/*' ! -path './survey/*.log' -print0 ) \
      | while IFS= read -r -d '' f; do
          mkdir -p "$(dirname "$USERDATA/$d/${f#./}")"
          cp -p "$REPO/$d/${f#./}" "$USERDATA/$d/${f#./}"
        done
      n=$((n+1))
    done
    echo "backed up $REPO -> userdata/"
    echo "review with: git status && git diff --stat, then commit."
    ;;

  install)
    for f in "${FILES[@]}"; do
      mkdir -p "$(dirname "$REPO/$f")"
      cp -p "$OVERLAY/$f" "$REPO/$f"
      echo "installed $f"
    done
    chmod +x "$REPO"/automation/*.sh 2>/dev/null || true

    # automation/ is fork-local: declare it so update-system.mjs never writes there.
    # providers/jobindex.mjs is deliberately NOT declared — config/local-paths.txt
    # refuses a path the system layer ships, and providers/ is a SYSTEM_PATHS entry.
    # It needs no declaration: apply()'s checkout cannot touch a file absent upstream.
    LP="$REPO/config/local-paths.txt"
    if [[ ! -f "$LP" ]]; then
      printf '# Fork-local paths — see DATA_CONTRACT.md\nautomation/\n' > "$LP"
      echo "created   config/local-paths.txt"
    elif ! grep -qx 'automation/' "$LP"; then
      printf 'automation/\n' >> "$LP"
      echo "declared  automation/ in config/local-paths.txt"
    fi
    echo
    echo "installed into $REPO"
    [[ -e "$REPO/cv.md" ]] || echo "note: no cv.md there yet — run ./setup.sh --seed-userdata"
    ;;
esac

#!/usr/bin/env bash
# nightly.sh — unattended career-ops chain (fork-local; see config/local-paths.txt)
#
# TIER 1 (zero-token, always runs):  scan -> liveness -> bridge -> health
# TIER 2 (one cheap prompt, opt-in): triage the queue -> data/shortlist.md
# TIER 3 (expensive, opt-in):        full A-G evaluation of the shortlist
#
# Tier 3 is OFF by default and deliberately so: it spends real tokens and it
# is the step whose output a human should read. Enable per-run with flags.
#
# Usage:
#   ./automation/nightly.sh                 # tier 1 only (free)
#   ./automation/nightly.sh --triage        # tier 1 + 2
#   ./automation/nightly.sh --triage --eval # full chain (spends tokens)
#   ./automation/nightly.sh --eval --limit 3
#
# Cron example (weekdays 08:00, tier 1+2):
#   0 8 * * 1-5 $HOME/job-searcher/career-ops/automation/nightly.sh --triage >> $HOME/job-searcher/career-ops/data/automation.log 2>&1

set -uo pipefail   # NOT -e: a failing stage must not abort the whole chain

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR" || exit 1

# Cron runs with a minimal environment — resolve node explicitly.
source "$PROJECT_DIR/automation/_env.sh"
if [[ -z "$NODE" ]]; then
  echo "FATAL: node not found on PATH" >&2
  exit 1
fi

DO_TRIAGE=false
DO_EVAL=false
EVAL_LIMIT=5
PARALLEL=2

while [[ $# -gt 0 ]]; do
  case "$1" in
    --triage)   DO_TRIAGE=true; shift ;;
    --eval)     DO_EVAL=true; shift ;;
    --limit)    EVAL_LIMIT="${2:-5}"; shift 2 ;;
    --parallel) PARALLEL="${2:-2}"; shift 2 ;;
    *) echo "unknown flag: $1" >&2; exit 1 ;;
  esac
done

stage() { echo; echo "=== $* === [$(date '+%Y-%m-%d %H:%M:%S')]"; }

stage "career-ops nightly (triage=$DO_TRIAGE eval=$DO_EVAL)"

# ── Tier 1: zero-token ──────────────────────────────────────────────────────
stage "1/5 scan"
"$NODE" scan.mjs || echo "WARN: scan failed; continuing with existing queue"

stage "2/5 liveness sweep"
if [[ -f data/pipeline.md ]]; then
  "$NODE" check-liveness.mjs --file data/pipeline.md || echo "WARN: liveness sweep failed (non-fatal)"
fi

stage "3/5 bridge pipeline -> batch input"
"$NODE" automation/pipeline-to-batch.mjs || echo "WARN: bridge failed"

# ── Tier 2: cheap triage (one small prompt, no web, no subagents) ───────────
if [[ "$DO_TRIAGE" == true ]]; then
  stage "4/5 triage -> data/shortlist.md"
  if command -v claude >/dev/null 2>&1; then
    # Scoped tools instead of --dangerously-skip-permissions: this prompt only
    # needs to read two local files and write one.
    claude -p \
      --allowedTools "Read,Write" \
      "$(cat automation/triage-prompt.txt)" \
      || echo "WARN: triage failed (non-fatal)"
  else
    echo "SKIP: claude CLI not on PATH"
  fi
else
  stage "4/5 triage — skipped (pass --triage to enable)"
fi

# ── Tier 3: full evaluation (spends tokens) ────────────────────────────────
if [[ "$DO_EVAL" == true ]]; then
  stage "5/5 batch evaluation (limit=$EVAL_LIMIT parallel=$PARALLEL)"
  ./batch/batch-runner.sh --limit "$EVAL_LIMIT" --parallel "$PARALLEL" \
    || echo "WARN: batch runner exited non-zero"
  # batch-runner.sh already runs merge + reconcile + verify at the end.
else
  stage "5/5 evaluation — skipped (pass --eval to enable)"
  "$NODE" verify-pipeline.mjs || echo "WARN: pipeline health check reported issues"
fi

stage "done"

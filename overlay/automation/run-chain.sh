#!/usr/bin/env bash
# run-chain.sh — the whole career-ops chain in one command. Fork-local
# (declared in config/local-paths.txt); the updater will never touch it.
#
#   ./automation/run-chain.sh              # full chain, evaluates up to 5 roles
#   ./automation/run-chain.sh --limit 3    # cap how many get evaluated
#   ./automation/run-chain.sh --dry-run    # everything except paid evaluation
#   ./automation/run-chain.sh --no-scan    # skip discovery, work the existing queue
#   ./automation/run-chain.sh --parallel 3
#
# STAGES
#   0 cooldowns     refresh re_apply_windows      -> config/profile.yml
#   1 scan          zero-token discovery          -> data/pipeline.md
#   2 liveness      drop dead postings            (Chromium installed ✓)
#   3 bridge        pipeline -> batch-input.tsv
#   4 triage        one cheap prompt              -> data/shortlist.md
#   5 evaluate      parallel A-G workers          -> reports/ + PDFs + tracker TSVs
#   6 merge         TSVs                          -> data/applications.md
#   7 reconcile     close out pipeline entries
#   8 verify        integrity gate
#
# STAGE 5 USES THE SHIPPED batch/batch-runner.sh (user's explicit choice).
# Note it invokes its workers with --dangerously-skip-permissions, which bypasses
# every permission check for those headless workers — full shell, filesystem and
# network, not confined to this repo. That is how it runs unattended. Since the
# workers ingest job postings (attacker-influenceable text), keep the repo's
# "Untrusted External Content" doctrine in mind before widening what a run touches.
# ~/.claude/rules/hooks.md line 14 says never to use the flag; using this runner
# is a deliberate exception to that rule, made 2026-09-06.
#
# Chromium IS installed (2026-09-08) and the full
# build-cv-html -> verify-cv-facts -> generate-pdf chain is verified working, so
# --skip-pdf was dropped: each evaluated role now gets a tailored CV PDF.
#
# batch-runner.sh runs merge-tracker -> reconcile-pipeline -> verify-pipeline
# itself at the end of a run, so stages 6-8 below only fire when it did not run.

set -uo pipefail   # NOT -e: one bad stage must not kill the run

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR" || exit 1

source "$PROJECT_DIR/automation/_env.sh"
[[ -z "$NODE" ]] && { echo "FATAL: node not on PATH" >&2; exit 1; }

LIMIT=5
PARALLEL=2
DRY_RUN=false
DO_SCAN=true

while [[ $# -gt 0 ]]; do
  case "$1" in
    --limit)    LIMIT="${2:-5}"; shift 2 ;;
    --parallel) PARALLEL="${2:-2}"; shift 2 ;;
    --dry-run)  DRY_RUN=true; shift ;;
    --no-scan)  DO_SCAN=false; shift ;;
    -h|--help)  sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown flag: $1" >&2; exit 1 ;;
  esac
done

LOG_DIR="batch/logs"
mkdir -p "$LOG_DIR" batch/tracker-additions

stage() { echo; echo "━━━ $* ━━━ [$(date '+%H:%M:%S')]"; }
warn()  { echo "⚠️  $*"; }

stage "career-ops full chain (limit=$LIMIT parallel=$PARALLEL dry_run=$DRY_RUN)"

# ── 0. re-apply cooldowns ───────────────────────────────────────────────────
# Refresh BEFORE the scan so companies already applied to are filtered out of
# this run rather than the next one.
stage "0/8 sync re-apply cooldowns"
"$NODE" automation/sync-reapply-windows.mjs \
  || warn "cooldown sync failed — scan may re-surface applied roles"

# ── 1. scan ─────────────────────────────────────────────────────────────────
if [[ "$DO_SCAN" == true ]]; then
  stage "1/8 scan"
  "$NODE" scan.mjs || warn "scan failed; continuing with the existing queue"
else
  stage "1/8 scan — skipped (--no-scan)"
fi

# ── 2. liveness ─────────────────────────────────────────────────────────────
stage "2/8 liveness sweep"
# check-liveness.mjs --file expects ONE BARE URL PER LINE. Handing it
# pipeline.md directly made it read whole markdown rows as URLs, so every
# entry came back "invalid URL" and the sweep reported 0 active / N uncertain
# on every run since this chain was written (found 2026-09-09). Extract the
# URLs first. Only unchecked "- [ ]" rows matter — processed rows are done.
if [[ -f data/pipeline.md ]]; then
  LIVENESS_URLS="$(mktemp)"
  grep -E '^- \[ \]' data/pipeline.md \
    | grep -oE 'https?://[^ |)]+' \
    | sort -u > "$LIVENESS_URLS" || true
  if [[ -s "$LIVENESS_URLS" ]]; then
    "$NODE" check-liveness.mjs --file "$LIVENESS_URLS" \
      || warn "liveness sweep failed — dead postings may reach evaluation"
  else
    echo "no pending URLs to check"
  fi
  rm -f "$LIVENESS_URLS"
fi

# ── 3. bridge ───────────────────────────────────────────────────────────────
stage "3/8 bridge pipeline -> batch input"
"$NODE" automation/pipeline-to-batch.mjs || warn "bridge failed"

# ── 4. triage ───────────────────────────────────────────────────────────────
stage "4/8 triage -> data/shortlist.md"
if command -v claude >/dev/null 2>&1; then
  # Prompt goes in on STDIN: --allowedTools is variadic (<tools...>), so a
  # positional prompt after it gets swallowed as extra tool rules.
  claude -p --allowedTools "Read,Write" < automation/triage-prompt.txt \
    >"$LOG_DIR/triage.log" 2>&1 \
    && echo "shortlist written; see data/shortlist.md" \
    || warn "triage failed — see $LOG_DIR/triage.log"
else
  warn "claude CLI not on PATH — skipping triage"
fi

# ── 5. evaluate (shipped batch runner) ─────────────────────────────────────
RAN_BATCH=false
if [[ ! -f batch/batch-input.tsv ]]; then
  stage "5/8 evaluate — no batch-input.tsv, nothing to evaluate"
elif [[ "$DRY_RUN" == true ]]; then
  stage "5/8 evaluate — DRY RUN (batch-runner preview)"
  ./batch/batch-runner.sh --dry-run || warn "batch runner dry-run exited non-zero"
else
  stage "5/8 evaluate via batch/batch-runner.sh (limit=$LIMIT parallel=$PARALLEL)"
  # Resumable by design: rerun to continue, --retry-failed for failures,
  # --resume-paused after a usage limit, --status/--watch for progress.
  ./batch/batch-runner.sh \
    --limit "$LIMIT" \
    --parallel "$PARALLEL" \
    && RAN_BATCH=true \
    || warn "batch runner exited non-zero — check batch/logs/; state is resumable"
fi

# ── 6/7/8. merge, reconcile, verify ────────────────────────────────────────
# batch-runner.sh already ran all three when it completed a real batch.
if [[ "$RAN_BATCH" == true ]]; then
  stage "6-8/8 merge + reconcile + verify — already done by batch-runner"
else
  stage "6/8 merge tracker additions"
  "$NODE" merge-tracker.mjs || warn "merge failed"

  stage "7/8 reconcile pipeline"
  "$NODE" reconcile-pipeline.mjs || warn "reconcile failed"

  stage "8/8 verify"
  "$NODE" verify-pipeline.mjs || warn "pipeline health reported issues"
fi

stage "done"
echo
echo "Shortlist : data/shortlist.md"
echo "Tracker   : data/applications.md"
echo "Reports   : reports/"
echo "PDFs      : output/"
echo "Progress  : ./batch/batch-runner.sh --status"
echo "Web UI    : http://localhost:3000/pipeline"

#!/usr/bin/env bash
# Live view of the career-ops pipeline while an evaluation chain runs.
#
# The Go TUI in dashboard/ has no file watcher — reloadPipelineData() fires
# only on a keypress — so this exists to actually stream progress.
#
#   ./automation/watch-pipeline.sh [interval_seconds]
#
# Ctrl-C to stop. Read-only: it never writes to the tracker.
set -euo pipefail
cd "$(dirname "$0")/.."
NODE="${NODE:-$HOME/.nvm/versions/node/v24.17.0/bin/node}"
INTERVAL="${1:-5}"

while true; do
  clear
  printf '\033[1mcareer-ops — live\033[0m   %s   (refresh %ss, Ctrl-C to stop)\n\n' "$(date +%H:%M:%S)" "$INTERVAL"

  printf '\033[1mTracker\033[0m\n'
  awk -F'|' '/^\| *[0-9]+ *\|/ {
    gsub(/^ +| +$/,"",$2); gsub(/^ +| +$/,"",$4); gsub(/^ +| +$/,"",$5);
    gsub(/^ +| +$/,"",$6); gsub(/^ +| +$/,"",$7);
    printf "  %-3s %-26.26s %-38.38s %-7s %s\n", $2, $4, $5, $6, $7
  }' data/applications.md 2>/dev/null || echo "  (no tracker yet)"

  printf '\n\033[1mBatch\033[0m\n'
  if [[ -f batch/batch-state.tsv ]]; then
    awk -F'\t' 'NR>1 {printf "  #%-3s %-11s report %-5s score %s\n", $1, $3, ($6==""?"-":$6), ($7==""?"-":$7)}' batch/batch-state.tsv
  else
    echo "  (no batch state)"
  fi

  printf '\n\033[1mPipeline\033[0m  pending: %s   reports: %s\n' \
    "$(grep -c '^- \[ \]' data/pipeline.md 2>/dev/null || echo 0)" \
    "$(ls reports/*.md 2>/dev/null | grep -vc RESERVED || echo 0)"

  sleep "$INTERVAL"
done

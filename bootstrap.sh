#!/usr/bin/env bash
# bootstrap.sh — set this up on a fresh machine, from nothing.
#
#   ./bootstrap.sh            install everything
#   ./bootstrap.sh --check    verify an existing install, change nothing
#
# What it does, in order:
#   1. checks prerequisites and STOPS with instructions if any are missing
#   2. clones career-ops next to this repo (skipped if already there)
#   3. installs the overlay into it
#   4. installs npm deps and the Playwright browser
#   5. sets up the Python runner
#   6. creates apply-runner/.env from the example
#   7. verifies the lot and prints what to do next
#
# It never uses sudo and never touches your job-search data. Re-running it is
# safe: every step skips work already done.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)/career-ops"
CANONICAL="https://github.com/career-ops-hq/career-ops.git"
CHECK_ONLY=0
FAILED=0

[[ "${1:-}" == "--check" ]] && CHECK_ONLY=1
[[ "${1:-}" == "-h" || "${1:-}" == "--help" ]] && { sed -n '2,20p' "${BASH_SOURCE[0]}"; exit 0; }

say()  { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()   { printf '  ok    %s\n' "$*"; }
warn() { printf '  warn  %s\n' "$*"; }
bad()  { printf '  FAIL  %s\n' "$*"; FAILED=1; }

# ---------------------------------------------------------------- 1. prereqs

say "1/7  prerequisites"

need_cmd() {
  local cmd="$1" hint="$2"
  if command -v "$cmd" >/dev/null 2>&1; then ok "$cmd  ($(command -v "$cmd"))"; return 0; fi
  bad "$cmd is not installed — $hint"; return 1
}

need_cmd git "install git from your package manager" || true

if command -v node >/dev/null 2>&1; then
  NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)"
  if [[ "$NODE_MAJOR" -ge 18 ]]; then
    ok "node $(node -v)  (career-ops needs >=18)"
  else
    bad "node $(node -v) is too old; career-ops needs >=18"
  fi
else
  bad "node is not installed — https://nodejs.org or 'nvm install --lts'"
fi

# nvm installs node outside a login shell's PATH, which is the single most
# common reason a script here fails with 'node: not found' while node works
# fine in the terminal.
if ! command -v node >/dev/null 2>&1 && [[ -d "$HOME/.nvm/versions/node" ]]; then
  warn "nvm is present but node is not on PATH — run 'nvm use --lts' first"
fi

need_cmd uv "install it with: curl -LsSf https://astral.sh/uv/install.sh | sh" || true

if command -v claude >/dev/null 2>&1; then
  ok "claude CLI ($(command -v claude))"
else
  warn "no 'claude' CLI found. career-ops runs on any agent CLI (Claude Code,"
  warn "  Codex, Cursor, OpenCode, Antigravity...). You need one to use its modes."
fi

if [[ $FAILED -eq 1 ]]; then
  say "Stopped: install the FAIL items above, then run this again."
  exit 1
fi

# ---------------------------------------------------------------- 2. clone

say "2/7  career-ops checkout"
if [[ -d "$REPO/.git" ]]; then
  ok "already present at $REPO"
elif [[ -e "$REPO" ]]; then
  bad "$REPO exists but is not a git checkout — move it aside and re-run"
  exit 1
elif [[ $CHECK_ONLY -eq 1 ]]; then
  bad "no career-ops checkout at $REPO"
else
  echo "  cloning $CANONICAL"
  git clone --quiet "$CANONICAL" "$REPO" && ok "cloned to $REPO" || { bad "clone failed"; exit 1; }
fi

# ---------------------------------------------------------------- 3. overlay

say "3/7  overlay (Jobindex provider + automation)"
if [[ $CHECK_ONLY -eq 1 ]]; then
  "$HERE/setup.sh" --check >/dev/null 2>&1 && ok "overlay matches this repo" || bad "overlay missing or drifted — run ./setup.sh"
else
  "$HERE/setup.sh" --repo "$REPO" >/dev/null && ok "overlay installed" || bad "overlay install failed"
fi

# ---------------------------------------------------------------- 4. npm + browser

say "4/7  node dependencies and browser"
if [[ $CHECK_ONLY -eq 0 ]]; then
  if [[ -d "$REPO/node_modules" ]]; then
    ok "node_modules already present (skipping npm install)"
  else
    # --ignore-scripts ON PURPOSE. career-ops' postinstall is
    #   npx playwright install chromium --with-deps
    # and --with-deps shells out to sudo for OS libraries, which cannot succeed
    # in a non-interactive script. It fails the whole install for a step we do
    # ourselves on the next line, without --with-deps.
    echo "  npm install (scripts skipped — see comment in this file)"
    (cd "$REPO" && npm install --ignore-scripts --no-audit --no-fund >/dev/null 2>&1) \
      && ok "npm dependencies installed" || bad "npm install failed"
  fi
fi

if [[ -d "$HOME/.cache/ms-playwright" ]] && compgen -G "$HOME/.cache/ms-playwright/chromium-*" >/dev/null; then
  ok "Playwright Chromium already installed"
elif [[ $CHECK_ONLY -eq 1 ]]; then
  bad "Playwright Chromium missing — needed for PDFs and liveness checks"
else
  echo "  downloading Chromium (~150MB, one time)"
  (cd "$REPO" && npx --yes playwright install chromium >/dev/null 2>&1) \
    && ok "Chromium installed" \
    || warn "Chromium install failed. PDF generation and liveness checks will not work.
        Try manually:  cd $REPO && npx playwright install chromium
        If it complains about system libraries, that step needs sudo:
          sudo npx playwright install-deps chromium"
fi

# ---------------------------------------------------------------- 5. runner

say "5/7  python runner"
if [[ $CHECK_ONLY -eq 1 ]]; then
  [[ -d "$HERE/apply-runner/.venv" ]] && ok "venv present" || bad "no venv — run ./bootstrap.sh"
else
  # uv reads .python-version (3.12) and fetches that interpreter itself, so the
  # system python version does not matter.
  (cd "$HERE/apply-runner" && uv sync --quiet) && ok "runner dependencies installed" || bad "uv sync failed"
fi

# ---------------------------------------------------------------- 6. env

say "6/7  API key"
ENV_FILE="$HERE/apply-runner/.env"
if [[ -f "$ENV_FILE" ]]; then
  if grep -qE '^ANTHROPIC_API_KEY=.+' "$ENV_FILE"; then
    ok ".env has an ANTHROPIC_API_KEY"
  else
    warn ".env exists but ANTHROPIC_API_KEY is empty — the form filler will not run"
  fi
elif [[ $CHECK_ONLY -eq 1 ]]; then
  warn "no apply-runner/.env yet"
else
  cp "$HERE/apply-runner/.env.example" "$ENV_FILE"
  sed -i.bak "s|^CAREER_OPS_REPO=.*|CAREER_OPS_REPO=$REPO|" "$ENV_FILE" && rm -f "$ENV_FILE.bak"
  ok "created apply-runner/.env (pointing at $REPO)"
  warn "EDIT IT and add your ANTHROPIC_API_KEY before filling any form."
  warn "  Get one at https://console.anthropic.com — it bills per token,"
  warn "  separately from any Claude subscription. About \$0.26 per application."
fi

# ---------------------------------------------------------------- 7. verify

say "7/7  verify"
if [[ -f "$REPO/doctor.mjs" ]]; then
  DOC="$(cd "$REPO" && node doctor.mjs --json 2>/dev/null)"
  if [[ -n "$DOC" ]]; then
    if grep -q '"onboardingNeeded":true' <<<"$DOC"; then
      ok "career-ops runs; onboarding not done yet (expected on a fresh install)"
    else
      ok "career-ops runs and is already set up"
    fi
  else
    bad "doctor.mjs produced no output"
  fi
fi

if (cd "$REPO" && node tests/providers/jobindex.test.mjs >/dev/null 2>&1); then
  ok "Jobindex provider tests pass"
else
  bad "Jobindex provider tests failed"
fi
if (cd "$REPO" && node tests/automation/apply-queue.test.mjs >/dev/null 2>&1); then
  ok "apply-queue tests pass"
else
  bad "apply-queue tests failed"
fi
if [[ -d "$HERE/apply-runner/.venv" ]] && (cd "$HERE/apply-runner" && uv run python -m pytest -q >/dev/null 2>&1); then
  ok "runner tests pass"
else
  [[ $CHECK_ONLY -eq 1 ]] && bad "runner tests failed" || warn "runner tests did not pass"
fi

# ---------------------------------------------------------------- next steps

if [[ $FAILED -eq 1 ]]; then
  say "Finished with problems — see the FAIL lines above."
  exit 1
fi

if [[ $CHECK_ONLY -eq 1 ]]; then
  say "All good."
  exit 0
fi

cat <<NEXT

$(printf '\033[1m%s\033[0m' "Installed. Three things left, in this order:")

  1. Tell career-ops who you are.
     Open your agent CLI in the career-ops checkout and let it onboard you:

         cd $REPO
         claude

     Then say: "set me up". It will ask for your CV and details and write
     cv.md, config/profile.yml, modes/_profile.md and portals.yml.
     All of that stays on this machine — it is gitignored, and nothing in
     this repo ever collects it.

  2. Find roles.
     Ask it to "run career-ops scan", or run the whole chain:

         ./automation/run-chain.sh --limit 5

  3. Fill an application (nothing is ever submitted).

         node automation/apply-queue.mjs --min-score 4.0
         cd $HERE/apply-runner
         uv run python run.py ~/job-searcher/handoff --dry-run   # free, no browser
         uv run python run.py ~/job-searcher/handoff             # fills the forms

     Every form is left open in its own browser tab. You review it, answer
     anything it left blank, and click Submit yourself. The runner cannot
     submit — that is enforced in code, not just asked for in a prompt.

  Re-run './bootstrap.sh --check' any time to confirm things still work.

NEXT

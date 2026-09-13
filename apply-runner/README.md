# apply-runner

The hands half of the career-ops job search. career-ops scores roles and
writes the CV and cover letter; this fills the application form and stops
before Submit. A human submits, always.

Design and rationale: `../overlay/automation/BROWSER_USE_SCOPE.md`.

## Status (2026-09-13)

Verified filling a live form. Consumes handoff bundles written by career-ops'
`automation/apply-queue.mjs`.

- browser-use 0.13.10 in a Python 3.12 venv (`uv`)
- `bundle.py` — loads and verifies a handoff bundle (25 tests)
- `guards.py` — the safety core (28 tests)
- `run.py` — fills a batch, one tab per job, stopping before submit

## Setup

```bash
cp .env.example .env      # then fill in ANTHROPIC_API_KEY and CAREER_OPS_REPO
```

## Running

```bash
# in career-ops, export bundles for whatever clears the bar
node automation/apply-queue.mjs --min-score 3.5

# verify them without opening a browser or spending a token
uv run python run.py ~/job-searcher/handoff --dry-run

# fill for real — every form is left open in its own tab, nothing submitted
uv run python run.py ~/job-searcher/handoff
```

`--dry-run` validates checksums and cover letters and reports posting liveness.
Liveness is checked here rather than at export time: a bundle can sit for days,
and a browser run against a dead posting costs real money for nothing.

After a real submit, move the bundle to `handoff/done/` and run career-ops'
`set-status.mjs` at the same moment. `done/` is skipped on later runs — Greenhouse
accepts duplicate applications and Ashby merges them silently by email, so a
second fill would be invisible rather than rejected.

The key is a console.anthropic.com API key. It bills per token, separately
from a Claude Code subscription.

## How submit is prevented

There is no `submit` action in browser-use to remove — submitting is an
ordinary `click` on a button. So `guards.py` shadows the built-in `click`
(registering an action of the same name overrides it) and refuses when the
target element's text reads as a final submit, in English or Danish.

Three layers, weakest last:

1. `exclude_actions` drops `evaluate` (arbitrary JS) and the file actions.
   `upload_file` is kept — attaching the CV needs it.
2. The click guard refuses submit-like elements.
3. `allowed_domains` confines navigation to the posting's own hosts.
4. A human reviews the screenshot.

Layer 2 is text matching, not a proof: an oddly labelled button gets through.
Layer 4 is the real guarantee. A network-level block on the form POST would
be strictly stronger and is the next hardening step if this proves leaky.

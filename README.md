# career-ops-dk

The Denmark-specific half of a career-ops job search, plus the browser runner
that fills application forms. Two halves that career-ops upstream does not ship.

```
career-ops-dk/
  bootstrap.sh    START HERE — sets up everything on a fresh machine
  QUICKSTART.md   how to actually use it once installed
  AGENT-NOTES.md  what these additions are (read by agents, and by you)
  overlay/        code that installs INTO a career-ops checkout
  apply-runner/   the Python/browser-use form filler (standalone)
  setup.sh        installs the overlay into a checkout
```

## The three moving parts

| Part | Where it comes from | How it updates |
|------|--------------------|----------------|
| career-ops | `git clone https://github.com/career-ops-hq/career-ops.git` | `node update-system.mjs apply --confirm` |
| this overlay | this repo | `./setup.sh` |
| browser-use | a uv dependency of `apply-runner` | `uv sync` |

career-ops is cloned unmodified. Nothing here is a fork of it, so upstream
updates keep working: `update-system.mjs` fetches a **hardcoded** canonical URL,
not your `origin`, so this checkout's remote can point anywhere. The only hard
requirement is that the checkout owns its own `.git` — a ZIP copy is refused.

## What the overlay contains

- **`providers/jobindex.mjs`** — Jobindex.dk, Denmark's largest job board, via
  the public RSS feed. This is the single highest-value file here: one scan
  returned 13 DK product roles against 2 from all ten configured company boards,
  and it is the only thing that reaches the enterprise/public-sector tier
  (Danske Bank, Jyske Bank, Region Syddanmark, KOMBIT). Drop-in — the registry
  globs `providers/*.mjs`, so nothing needs registering.
- **`automation/`** — `run-chain.sh` (the whole chain in one command) and
  `pipeline-to-batch.mjs`, which closes a real upstream gap: nothing shipped
  converts `data/pipeline.md` into `batch/batch-input.tsv`.

## Setup on a new machine

```bash
git clone <this repo> career-ops-dk
cd career-ops-dk
./bootstrap.sh
```

That is the whole install. It checks what you are missing, clones career-ops,
installs the overlay, fetches the browser, sets up the Python runner, creates
your `.env`, runs the test suites, and prints the three things left to do. It
never uses sudo and re-running it is safe.

You need first: **git**, **Node 18+**, **uv** (`curl -LsSf https://astral.sh/uv/install.sh | sh`),
and an agent CLI such as Claude Code. bootstrap tells you which are missing and
how to get them, then stops rather than half-installing.

You also need an **Anthropic API key** from console.anthropic.com for the form
filler. It bills per token, separately from any Claude subscription — measured
at about **$0.26 per application**. career-ops itself runs on your agent CLI's
own subscription, not this key.

Check an existing install at any time:

```bash
./bootstrap.sh --check      # verifies everything, changes nothing
```

## Working on the overlay

`overlay/` is the source of truth. Edit there, then `./setup.sh` to install.

```bash
./setup.sh --check   # has the installed copy drifted from overlay/?
./setup.sh --pull    # rescue edits made directly in the checkout
```

### Why copies and not symlinks

Tried on 2026-09-13, reverted the same day. Both halves break under a symlink,
and both break *silently*:

- `providers/jobindex.mjs` imports `./_html-entities.mjs`. Node resolves a
  symlinked module's imports against its **realpath**, so the import looked
  inside `overlay/providers/` and the provider failed to load. `scan.mjs`
  carried on with 87 providers instead of 88 and reported no error.
- `automation/*.mjs` compute `ROOT` as `dirname(import.meta.url)/..`, which via
  a symlink is `overlay/`, not the checkout. `pipeline-to-batch.mjs` reported
  `0 pending` against a `data/pipeline.md` holding real URLs.

Copies keep every file's realpath inside the checkout. `--check` is what
replaces the guarantee symlinks would have given.

## Your data

**This repo contains no personal data, and nothing you generate should be added
to it.** Clone it, install the overlay, then run career-ops' own onboarding: it
creates `cv.md`, `config/profile.yml`, `modes/_profile.md` and `portals.yml` in
your career-ops checkout, all of which career-ops already gitignores.

Everything your search produces — the tracker, reports, generated CVs, scan
history, interview prep — stays in that checkout, on your machine. `userdata/`
and `handoff/` are gitignored here so a stray backup can never be committed.

The consequence worth knowing: there is no offsite copy. If the machine dies,
the search history goes with it. Back the career-ops checkout up however you
back up anything else you would not want to retype.

`apply-runner/.env` is gitignored too. The Anthropic key never travels; each
machine needs its own.

### Never commit these

- `apply-runner/.env` — the Anthropic API key.
- `cv.md`, `config/profile.yml`, `data/`, `reports/`, `output/` — your own
  job-search state. career-ops gitignores all of it; keep it that way.
- `data/contacts.tsv`, `data/Connections.csv` — recruiters and LinkedIn
  connections. That is *other people's* personal data, and it does not belong in
  a repo even a private one.

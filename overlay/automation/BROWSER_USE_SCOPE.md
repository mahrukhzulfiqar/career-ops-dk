# Scope — browser-use as the form-filling hands for career-ops

**Status:** scope, 2026-09-09. Fork-local (`automation/` is declared in
`config/local-paths.txt`, so `update-system.mjs` never touches it).

Supersedes the deleted `APPLY_CONTRACT.md` (2026-09-09), which specified a
per-form field-map handoff. That was wrong: it invented a career-ops feature
that does not exist and was never career-ops' job.

## Framing

career-ops already produces everything the handoff needs. Nothing is added
to it. browser-use consumes existing artifacts, opens the posting, studies
the form itself, and fills it.

```
career-ops (unchanged)                    |  browser-use (new)
------------------------------------------|--------------------------------
scan / triage / oferta  -> reports/NNN.md  |
pdf mode                -> output/*.pdf    |
cover mode              -> cover letter    |
tracker row: score, URL, report link       |
                                           |
    apply-queue.mjs -> handoff/NNN-slug/ -->  open the form
                                           |  fill from that dir only
                                           |  refuse submit, hold window open
                                           |
       human reviews the live tab <---------
       submits by hand                     |
       mv handoff/NNN -> handoff/done/     |
       set-status.mjs <n> Applied          |
```

The handoff is a **list of jobs**, not a description of any form:

| Source (already on disk) | Supplies |
|---|---|
| `data/applications.md` | company, role, score, status, report link, posting URL |
| `reports/NNN-*.md` -> `## Machine Summary` | score, final_decision, work_auth, advertised_comp |
| `output/*.pdf` | the tailored CV, copied into the handoff dir |
| `cover` mode output | the cover letter, copied in |
| `config/profile.yml` | mechanically derived into `facts.md` |

The runner never reads any of these directly — the export step copies what it
needs into the per-job directory. See the handoff section below.

## What gets built

Small. Two files plus a prompt.

1. **`career-ops/automation/apply-queue.mjs`** (Node) — reads the tracker and
   each row's report, keeps rows where score >= threshold, status is
   `Evaluated`, a URL is present and the CV PDF exists, and nothing for that
   report already sits under `handoff/done/`. **Exports one self-contained
   directory per job** (see below), rather than emitting a bare list. Reads
   career-ops, writes only to `~/job-searcher/handoff/`. No field maps, no
   per-ATS logic.

   It stays in career-ops so it can reuse `tracker-parse.mjs`'s
   `parseTrackerRow` / `resolveColumns` / `resolveScoreStatus` instead of
   reimplementing the tracker's edge cases (score sentinels, the score/status
   transposition, `via=` tags) in Python.

2. **`apply-runner/run.py`** (Python) — the browser-use driver. Takes one
   handoff directory, verifies its manifest, fills, refuses submit, holds the
   window open for review.

3. **The task prompt** — carries the rules below. This is the only part that
   survives from the deleted contract, and it is prose, not a schema.

### The handoff is an exported directory, one per job (revised 2026-09-09)

The runner must not reach into career-ops' internals — that would couple the
two and defeat the delegation. career-ops exports a self-contained directory
per job, and that directory is the entire interface. career-ops produces
personalized output per role — a score, a tailored CV, a cover letter — so the
unit of handoff is the role, never a shared pool of files.

**Location: `~/job-searcher/handoff/`, neutral ground.** Not inside either
project. career-ops writes it, the runner reads it, neither owns the other's
tree — and per-job generated artifacts stay out of an upstream-tracked repo
that gets re-synced constantly.

```
~/job-searcher/handoff/
├── 007-acme-product-manager/
│   ├── job.json          company, role, url, apply_host, report_number,
│   │                     score, and a sha256 for each file below
│   ├── cv.pdf            a copy, not a path into career-ops/output/
│   ├── cover-letter.md
│   └── facts.md          answers to form questions not on a CV
└── 011-novo-nordisk-product-owner/
    └── ...
```

The runner is pointed at one directory and has no idea career-ops exists.
The handoff is reviewable before any browser opens, and it records exactly
what was available at fill time.

**Filenames inside are generic on purpose.** `cv.pdf`, not
`cv-candidate-acme-2026-09.pdf`. Exactly one CV per directory means there is no
file to pick wrong: the runner does not search, match names, or choose. One
directory, one candidate per slot.

### Guarding against files crossing between applications

The failure that matters is not a corrupted file — it is one employer's cover letter
arriving in Novo Nordisk's form. That is visible, unrecoverable, and reads as
careless. A directory boundary alone does not catch it, because a faulty export
puts the wrong file in the right directory and everything downstream looks
correct.

Two checks, both cheap:

1. **`job.json` carries a sha256 per file.** Proves the directory was not
   half-rebuilt or hand-edited between export and run.
2. **The runner asserts the cover letter contains the company name from
   `job.json`** before uploading anything. A checksum proves a file is intact;
   only this proves it is the *right* file. On failure the run stops rather
   than applying.

### Lifecycle: nothing is applied to twice

A directory that stays put after submission is one that gets refilled on the
next run. Greenhouse accepts the duplicate; Ashby silently merges duplicates by
email, so the mistake may never surface.

```
~/job-searcher/handoff/007-acme-product-manager/        ready
~/job-searcher/handoff/done/007-acme-product-manager/   submitted
```

The move to `done/` happens by hand at review time — the same moment
`node set-status.mjs 007 Applied` runs. The queue step skips anything already
under `done/`, so a re-run cannot resurrect a submitted application.

### facts.md

`facts.md` MUST be mechanically derived — named keys copied verbatim out of
`config/profile.yml`, never an LLM summary of the CV. If a model writes that
file, fabrication has simply moved one step earlier in the chain.
`profile.yml` already answers the two that matter most:
`visa_status` (whatever the profile states)
and `needs_sponsorship: false`.

### Rules the prompt must carry

browser-use ships **no built-in approval, pause, or human-in-the-loop step**
(verified against its README, 2026-09-09). Every one of these is ours to
enforce in the task text and by not granting the submit action:

- Fill only from the provided facts. If a field's answer is not there, **stop
  and record the question verbatim** — do not guess. This directly overrides
  browser-use's own `apply_to_job.py` example, which instructs the model to
  "make your best guess" on forms containing legal declarations.
- Never guess work authorization, sponsorship, veteran status, disability
  status, or salary expectation.
- Never click Submit / Send / Apply as the final action. Fill, screenshot, end.
- Stop on captcha.
- Stay on the posting's own host.
- Select dropdown and radio options by their **exact visible text**, never by
  position. Workday varies Yes/No order; a positional click can silently
  answer "No" to work authorization.

## Known limits, accepted

- **browser-use is LLM-driven and non-deterministic.** Its own production
  write-up says agents are not reliable enough over long step counts. That is
  acceptable here only because a human reviews a screenshot before anything is
  submitted. It would not be acceptable unattended.
- **Lever raises hCaptcha** on programmatic checkbox and radio clicks;
  **Workday** ignores programmatically set values. Expect these to land as
  stops, not fills. Greenhouse and Ashby are the clean cases.

## Prerequisites

1. ~~**Python 3.11+.**~~ Done 2026-09-09 — `uv venv --python 3.12` at
   `~/job-searcher/apply-runner`; uv fetched CPython 3.12.13 itself, no system
   change. (System Python is 3.10.12, which browser-use does not support.)
2. **An LLM API key for browser-use.** Provider chosen: **Anthropic**, default
   model `claude-sonnet-5`. Key still missing — it is a console.anthropic.com
   key that bills per token, separate from the Claude Code subscription.
   browser-use runs its own agent loop, so this is a second meter. Cost is
   expected to be small (career-ops filters hard: a few roles per week) but is
   unmeasured until the smoke test runs.
3. **EEO answers are not recorded.** `config/profile.yml` covers work
   authorization and sponsorship but has no gender / ethnicity / veteran /
   disability entries. These questions are voluntary, so "prefer not to say"
   is an honest answer — but it has to be the user's recorded choice, written
   once into the profile, not decided by a runner at fill time.
4. **Score threshold for the queue.** Undecided. 4.5 was the figure in the
   original auto-apply brief.

## Blocking reality: the queue is empty

There are 4 reports on disk, scored 1.5, 1.5, 2.0 and 2.5 — all below any
sensible bar, and all four are test runs against a software-engineering CV,
not the Product Manager profile the system was personalized to on 2026-09-08.
No tailored CV PDFs exist beyond the baseline, and `cover` mode has never run.

So the pipeline has nothing to act on today. Build order:

1. **Smoke-test browser-use alone** (`apply-runner/smoke_test.py`, read-only)
   against a real posting. This is doable now and does not need a queue — it
   settles the numbers the rest is sized from: cost per form, steps per form,
   and which host the application actually lives on.
2. Run the chain against the corrected profile until genuine 4.5+ roles exist.
3. Confirm `pdf` and `cover` produce per-role artifacts for them.
4. Then `automation/apply-queue.mjs` (testable against a real queue).
5. Then `apply-runner/run.py`.

Building 4 and 5 before 1 is possible but untestable, and an untested
form-filler is worth nothing.

---

## Implementation notes — 2026-09-09

**Runner installed** at `~/job-searcher/apply-runner` (sibling of career-ops,
not inside it): browser-use **0.13.10**, Python 3.12 via `uv venv --python
3.12`. browser-use is a **package** (`uv add browser-use`), not a second
checkout — there is nothing to clone. Vendoring was considered and rejected:
the "make your best guess" text that prompted the concern lives in the repo's
`examples/use-cases/apply_to_job.py`, not in the library, so it never reaches
code we run.

`ANONYMIZED_TELEMETRY=false` is set — browser-use ships telemetry on by
default and this handles a real person's applications.

### Correction: there is no submit action to exclude

The earlier plan said `exclude_actions` could structurally remove submit.
It cannot. The registry (verified on 0.13.10) is: click, close, done,
dropdown_options, evaluate, extract, find_elements, find_text, go_back, input,
navigate, read_file, replace_file, save_as_pdf, screenshot, scroll, search,
search_page, select_dropdown, send_keys, switch, upload_file, wait, write_file.
**Submitting is an ordinary `click` on a button** — the one action form-filling
cannot do without.

What was built instead, in `apply-runner/guards.py`:

1. `exclude_actions` still drops `evaluate` (arbitrary JS — turns hostile page
   text into code execution) plus the file actions. `upload_file` is kept;
   attaching the CV needs it.
2. **The `click` action is shadowed.** Registering an action named `click`
   overrides the built-in (verified). The replacement resolves the element via
   `browser_session.get_dom_element_by_index()`, refuses if its text reads as a
   final submit in English or Danish, and otherwise delegates to the original.
   A failed element lookup refuses rather than allows.
3. `allowed_domains` on `BrowserProfile` confines navigation. Entries must be
   scheme-qualified or globbed — a malformed entry blocks every URL, including
   the intended ones (browser-use #3153).
4. A human reviews the screenshot.

**Honest limit:** layer 2 is text matching, not a proof — bare "Apply" and
"Ansøg" are deliberately allowed through because on most boards they open the
form rather than submit it, so an oddly labelled submit button can slip past.
Layer 4 remains the real guarantee. A network-level block on the form POST
would be strictly stronger and is the next hardening step if this proves leaky.

### Verified guardrail API (0.13.10)

`Agent(extend_system_message=, override_system_message=, tools=, max_failures=,
max_actions_per_step=, output_model_schema=, browser_profile=)`,
`agent.run(max_steps=)`, `Tools(exclude_actions=)`,
`BrowserProfile(allowed_domains=, headless=, downloads_path=)`.

### Still open

- `ANTHROPIC_API_KEY` — a console.anthropic.com key, billing separately from
  the Claude Code subscription. Model default `claude-sonnet-5`.
- EEO answers still absent from `config/profile.yml`.
- Score threshold for the queue still undecided.
- `automation/apply-queue.mjs` and `apply-runner/run.py` not written yet;
  both are sized off the smoke-test numbers.
- Do **not** name the runner's pointer at career-ops `CAREER_OPS_ROOT`;
  career-ops already uses that for its data directory. `CAREER_OPS_REPO`.

### What the run looks like (2026-09-09)

Not headless. WSLg is present on this machine (`DISPLAY=:0`, Wayland too), so
Chromium opens a real window on the Windows desktop and the fill is watched
live; `highlight_elements` is on by default, so it boxes each element it
touches, and every step is an LLM call, so it moves at a readable pace.

`headless=False` is the product here, not a debug setting: the filled form on
screen is the artifact the human reviews.

**`keep_alive=True` is required and was initially missed.** Without it
browser-use tears the window down when the agent finishes, discarding the
filled form at exactly the moment it is needed. The runner also blocks on a
prompt at the end — `keep_alive` stops browser-use closing the browser, and
blocking stops the Python process exiting and taking the child with it. That
pause is the review-and-submit step: the agent stops, says the tab is ready,
and the human submits by hand.

### allowed_domains must follow the board-to-ATS handoff

The Hub is a job board, not an ATS: its postings hand off to the employer's own
Greenhouse / Ashby / Teamtailor instance for the actual form. So the tracker's
posting URL host (`thehub.io`) is NOT the host the form lives on, and confining
navigation to it blocks the run before a form is ever reached.

Consequences:

- The read-only smoke pass runs with `allowed_domains=None` deliberately — its
  job is to discover where the form actually lives. `guards.build_profile`
  logs a warning whenever domains are unrestricted so this can never be
  silent. Acceptable only because that pass fills and submits nothing.
- The real runner restricts to **both** the board host and the ATS host, which
  means the handoff `job.json` needs an `apply_host` field the queue step
  cannot know in advance. Expect to learn it per employer on first contact and
  record it.

---

## Verified against a live posting — 2026-09-09

Target: The Hub / Embankment / Senior Product Manager (report 001). Two passes,
read-only then fill. **The fill pass succeeded end to end in 13 steps**: name,
email and phone entered from `config/profile.yml`, CV attached and confirmed
present in the form, every other field left empty, nothing submitted.

### What the board actually does

- The application is an **on-page modal on `thehub.io`** — no handoff to an
  external ATS. The redirect worry does not apply to this board (it may still
  apply to others; nothing about Greenhouse or Ashby has been tested).
- **The submit button is labelled `Apply`** — the same word as the button that
  opens the modal. See the guard section below.
- **reCAPTCHA sits on the submit path.** Harmless under the attended model, and
  independently fatal to any unattended one.
- Three of the required fields are 500-character essays specific to the posting
  ("Where do you see product management heading with AI?", "Are you living in
  Denmark?", "What is the most important quality of a product manager?").

### The no-fabrication rule held under pressure

Every essay question was left empty on a form that marks them required, with
the agent stating it had no answer. It also declined to answer "Are you living
in Denmark?" from the `city: Copenhagen, Denmark` fact it *had* been given,
reasoning that using it "would be inventing/interpreting an answer beyond the
literal fact."

**That is correct behaviour and a design finding.** Facts must reach the agent
in *answerable* form. A residency fact stated as a city does not answer a
residency question; `facts.md` needs the claim the form asks for, stated
plainly, or the field stays empty. This is the right failure mode — empty
beats guessed — but it means `facts.md` needs care, not just a key dump.

### Guard: the fix is sequence, not vocabulary

`Apply` is irreducibly ambiguous — no wordlist separates "open the form" from
"send the form". The sequence does: you never click Apply *after* filling
except to submit. So `guards.py` shadows `input`, `select_dropdown` and
`upload_file` purely to latch a `filling_started` flag, and promotes an
ambiguous tier (`apply`, `ansøg`, `send`, `continue`) from allowed to blocked
once it is set. Unambiguous labels (`submit`, `send ansøgning`) are blocked
throughout.

### Two bug classes in action-shadowing, both found on a live form

Both were mine, both the same root cause — a shadow that does not faithfully
mirror the built-in:

1. **No `param_model`.** The registry then infers the schema from the
   signature and defaults an unannotated parameter to `str`
   (`registry/service.py`, "Type 2"), so the original receives a string and
   fails with `'str' object has no attribute 'model_dump'`. Three failed
   clicks, then the session collapsed.
2. **An incomplete injected signature.** `upload_file` declares
   `available_file_paths: list[str]` and `file_system: FileSystem` on top of
   `params` and `browser_session`. A shadow omitting them calls the original
   without them: `Action upload_file requires available_file_paths but none
   provided`, five times, no CV attached.

Also: **do not use `from __future__ import annotations` in the guards module.**
It stringifies annotations, and the registry compares `browser_session`'s
annotation against the real class — a string never matches, and registration is
refused with "conflicts with special argument injected by tools".

`apply-runner/test_guards.py` pins all of this: 28 tests comparing each
shadow's `param_model` and full parameter set against the built-in, plus the
before/after label matrix. This class of bug now fails at test time rather than
on a live employer's form.

### Still unmeasured / unproven

- **Cost.** browser-use logs no token usage, so there is still no per-form
  number. Read-only was 7 steps, fill was 13.
- **The submit block has never fired in anger.** `submit clicks blocked: 0` on
  both fill runs — the agent obeyed the prompt and never reached for submit.
  The state-aware guard passes unit tests but has not been exercised by an
  agent actually trying to click Apply on a filled form. Worth a deliberate
  adversarial run before trusting it.
- **Teardown is noisy.** Both runs ended with CDP WebSocket reconnection errors
  and a pending-task warning *after* the result was produced. Cosmetic so far,
  but it means `keep_alive` is not cleanly holding the session at exit.

### Third pass: cv.md as answering context (2026-09-09)

`facts.py` now passes **cv.md whole and verbatim** (6.7KB, 83 lines — cheap),
plus three keys added to `config/profile.yml` that restate it:
`current_title`, `current_employer`, `resident_in_denmark`. All three are
sourced in comments; none is a new claim.

The earlier blanks had two different causes, worth keeping straight:

- **"Current or previous job title" was a payload gap, not caution.** The
  profile had no title field at all and `identity()` passed five facts, none of
  them a title. The agent could not answer what it was never given.
- **"Are you living in Denmark?" was genuine conservatism.** It held
  `city: Copenhagen, Denmark` and declined to use it, calling that
  "inventing/interpreting an answer beyond the literal fact." Over-cautious,
  but the right direction to be wrong in — and the fix is to state facts in
  the form the question asks, not to loosen the rule.

**Fields are now tiered in the task prompt**, because trust in the source was
never the issue — the issue is that answering is sometimes transcription and
sometimes composition, and only composition creates new text the candidate is
accountable for:

1. **Identity slots** — copy verbatim.
2. **Factual questions about experience** — answer from cv.md, explicitly
   forbidden from inflating scope, seniority, team size or numbers. This is
   the `story-bank.md` drift mechanism in AGENTS.md, one step earlier.
3. **Opinion / motivation / speculative questions** — left empty. No ground
   truth can answer "Where do you see product management heading with AI?";
   it is the candidate's own view and belongs to career-ops' `apply` mode plus
   her review.

Every type-2 answer must be **quoted verbatim in the agent's final report**, so
composed prose is reviewable as text and not only on screen.

**Result: 6 steps, down from 13.** Identity fields and job title filled, CV
attached, `"Are you living in Denmark?" -> "Yes, I currently live in
Copenhagen, Denmark."` composed and quoted back, both opinion questions left
empty, nothing submitted. Giving the agent the CV made it faster as well as
more complete — it stopped exploring the page for information it already had.

### Cover letters are an artifact, not an open question (2026-09-10)

career-ops ships `modes/cover.md` + `generate-cover-letter.mjs`, with its own
fabrication gate (`tests/cover-fact-gate.test.mjs`). So a cover letter is a
**reviewed artifact**, and pasting it into a cover-letter field is tier-1
transcription — not tier-3 composition. The letter is written in career-ops,
under its fact gate, where the user can read it before it reaches any form;
that is strictly safer than an agent improvising motivation text in a browser.

The field tiers are therefore:

1. Identity slot -> copy verbatim.
2. Factual question about her experience -> answer from cv.md, never inflating.
3. **Cover-letter / motivation-letter field WITH a supplied letter -> paste the
   file verbatim.** Never summarise, shorten, rewrite, or blend it with the job
   ad's wording.
4. **Bespoke opinion question that no artifact answers** ("where is product
   management heading with AI?") -> still empty. A cover letter does not answer
   these, and pasting one in is worse than leaving them blank.

Done in `apply-runner/run.py` (2026-09-10): the job list is now
`url<TAB>label<TAB>cv_path[<TAB>cover_letter_path]`, the letter is injected
verbatim into the task, and a named-but-missing file is a hard error rather
than a silent fallback — same rule as the CV.

**Two gaps this exposed, both still open:**

- **The chain generates no cover letters.** `run-chain.sh` is scan → liveness →
  bridge → triage → evaluate → merge → reconcile → verify. It produces reports,
  tailored CVs and tracker rows; `output/` holds zero letters. Nothing will
  reach tier 3 until that changes.
- **Generation belongs in the export step, not the runner.** A letter has to
  exist *before* a fill run, so `apply-queue.mjs` generates it per job while
  building the handoff directory. The runner must never request one on demand —
  that would put composition back inside the browser, at fill time, unreviewed.

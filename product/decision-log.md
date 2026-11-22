# Decision log

Short records of the decisions that shaped career-ops-dk: the context, what was chosen, and what was given up.

---

### D1. An overlay on career-ops, not a fork
**Context:** career-ops is an active open-source project. Changing it directly would give the Danish features, but every upstream update would then need merging by hand.
**Decision:** Clone career-ops unmodified and install the Danish additions into it from this repo with `setup.sh`.
**Why:** Upstream updates keep working with no merge work, and the additions stay in one small, reviewable repo.
**Trade-off:** Two repos to keep in step; `setup.sh --check` reports drift.

### D2. Install copies, not symlinks
**Context:** Symlinks were tried first so that edits would show up instantly. Both halves broke, and both broke silently: the Jobindex provider failed to load while the scan reported no error, and the pipeline bridge reported 0 pending roles against a file full of them.
**Decision:** Install real copies, reverted the same day.
**Why:** A silent failure in discovery means missing jobs without knowing it, which is worse than a crash.
**Trade-off:** Edits made in the installed copy are overwritten on the next install; `setup.sh --pull` rescues them.

### D3. Jobindex.dk through its public RSS feed
**Context:** The configured company boards found 2 Danish product roles in a scan. The public and enterprise tier was not reached at all.
**Decision:** Add a Jobindex provider using the public RSS feed.
**Why:** It returned 13 roles in the same scan and is the only source that reaches banks, regions and public bodies. RSS is a public, stable interface rather than scraped pages.
**Trade-off:** RSS gives title, company and link, not the full ad, so evaluation still fetches each posting.

### D4. Nothing in the system submits an application
**Context:** The obvious product is auto-apply. But an application cannot be recalled, and browser agents are not reliable over long sequences of steps.
**Decision:** The runner fills the form, leaves it open in a browser tab and stops. A human reviews and clicks Submit. This is enforced in code: the click action is replaced by a guarded one that refuses submit, send and apply buttons in English and Danish.
**Why:** The value is removing typing, not removing judgement. A rule in a prompt can be ignored by a model; a missing action cannot be used.
**Trade-off:** The candidate must still review every form. Text matching can miss an oddly labelled button, so the human review is the real guarantee.

### D5. A self-contained folder per role as the interface
**Context:** The first design was a contract of per-form field maps. It invented a feature career-ops does not have and coupled the two halves tightly.
**Decision:** career-ops exports one folder per role (`job.json`, `cv.pdf`, `cover-letter.md`, `facts.md`). The runner reads only that folder and does not know career-ops exists.
**Why:** Each half can change on its own, the bundle can be reviewed before any browser opens, and it records exactly what was available at fill time.
**Trade-off:** Files are copied rather than referenced, so a bundle can go stale if the CV changes after export.

### D6. Guard against a file reaching the wrong employer
**Context:** The worst failure is not a broken file but the right file type for the wrong company: a cover letter for one employer uploaded to another. A folder boundary alone does not catch a faulty export.
**Decision:** `job.json` carries a checksum for each file, and the runner checks that the cover letter contains the company name before uploading anything. On failure the run stops.
**Why:** It is visible to the employer, unrecoverable and reads as careless. Both checks are cheap.
**Trade-off:** A cover letter that never names the company fails the check and must be fixed by hand.

### D7. Facts are copied, never written by a model; unknowns stop the run
**Context:** Forms ask things a CV does not answer, such as work authorisation, notice period and salary. A common open-source example tells the agent to make its best guess, even on legal declarations.
**Decision:** `facts.md` is derived mechanically from named keys in the profile. If a field's answer is not there, the runner stops and records the question word for word. It never guesses authorisation, sponsorship, salary or diversity answers, and selects options by their visible text, not their position.
**Why:** If a model writes the facts file, fabrication has only moved one step earlier. Positional clicks can silently answer No to work authorisation, because Workday varies the order.
**Trade-off:** More runs stop early, and the profile needs filling in once.

### D8. The score bar is typed each run, not configured once
**Context:** Bundles are exported only for roles above a score. Lowering the bar fills forms for roles the evaluation calls a stretch.
**Decision:** The bar defaults to 4.0, career-ops' own advice-against line, and is a command-line flag rather than a setting.
**Why:** Widening the net should be a conscious choice each time, not a default forgotten in a config file.
**Trade-off:** One more argument to type.

### D9. A cheap triage before paid evaluation
**Context:** Full evaluation reads the ad, scores the fit and generates a tailored CV, which costs tokens and time for every role.
**Decision:** One cheap prompt sorts new roles into "worth a look", "maybe" and "skip" from title and location only, without opening any link. Roles that depend on an unknown fact go to "maybe" with the reason.
**Why:** Most scan results are clearly off-target, and judging them costs almost nothing.
**Trade-off:** A good role with an unusual title can be skipped.

### D10. Check the posting is live at fill time, not export time
**Context:** A bundle can sit for days before the candidate runs the filler, and a browser run against a closed posting costs money for nothing.
**Decision:** The runner's dry run checks liveness, checksums and cover letters without opening a browser or spending tokens.
**Why:** Problems are caught for free before the paid step.
**Trade-off:** A short delay at the start of each run.

### D11. A fixed CV is allowed, with no silent fallback
**Context:** Some candidates prefer to attach their own designed CV rather than the tailored one.
**Decision:** `cv.attach` chooses tailored or a fixed file. A configured file that does not exist is a hard error; the system never substitutes another file.
**Why:** Sending a different CV from the one the candidate chose is worse than not sending.
**Trade-off:** The agent notes once that a hand-made PDF usually parses worse in applicant tracking systems, then respects the choice.

### D12. No personal data in the repo, and no offsite copy
**Context:** A job search produces CVs, salary rules, recruiter contacts and LinkedIn connections, which include other people's data.
**Decision:** The repo contains no personal data. Everything the search produces stays in the candidate's own checkout, gitignored, on their machine.
**Why:** The repo can be shared publicly, and other people's contact data never ends up in version control.
**Trade-off:** There is no backup by default; if the machine is lost, the search history goes with it. The docs say this plainly.

### D13. Measure before building
**Context:** The form filler could be built before any real queue existed, but it could not be tested.
**Decision:** Smoke-test the browser agent alone against a real posting first, to settle cost per form, steps per form and which host the form lives on. Build the queue and runner after.
**Why:** An untested form filler is worth nothing, and the smoke test set the numbers the rest was sized from (about $0.26 per application).
**Trade-off:** The full flow was available later.

### D14. Accept the upstream batch runner's permission bypass, deliberately
**Context:** career-ops' batch evaluator runs headless workers with all permission checks skipped. Those workers read job postings, which are untrusted text.
**Decision:** Use it, as an explicit and documented exception, and treat every posting as untrusted data in every prompt.
**Why:** Unattended evaluation is what makes the pipeline run in one command.
**Trade-off:** A real risk is accepted rather than removed. Narrowing what the workers can touch is on the roadmap.

This checkout has additions upstream career-ops does not ship, installed from a
separate repo. **Read `{{NOTES_PATH}}` before answering anything about scanning,
applying, or editing `automation/`** — it covers the Jobindex scanner,
`run-chain.sh`, and the export-then-fill application workflow.

Two rules that apply even if you do not read it:

- **Nothing here submits an application.** `apply-runner` fills a form, leaves
  it open in a browser tab, and stops; the user reviews and clicks Submit. This
  is enforced in code, not just requested in a prompt. Never look for a way
  around it and never suggest one.
- **`automation/*` and `providers/jobindex.mjs` are installed copies.** Editing
  them here works until the next `./setup.sh` and then silently reverts. Change
  them in the source repo's `overlay/` instead. Everything else in this
  checkout — `portals.yml`, `config/profile.yml`, `modes/_profile.md`, `cv.md`,
  `data/`, `reports/` — is an ordinary user file, edited here as normal.

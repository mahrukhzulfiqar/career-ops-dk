# career-ops-dk: one-page product brief

**Status:** in use · **Owner:** Mahrukh · **Last updated:** November 2026

## Problem
Looking for a product job in Denmark with an AI agent has two gaps.

1. **Discovery misses most Danish roles.** The open-source career-ops system scans company job boards, but most Danish product roles, and almost all of the enterprise and public-sector tier (banks, regions, KOMBIT), are only on Jobindex.dk. In one scan, Jobindex returned 13 Danish product roles against 2 from all ten configured company boards.
2. **Applying is slow, and the tools that speed it up are unsafe.** Every application means filling the same fields again in Greenhouse, Ashby, Lever or Workday. Auto-apply tools solve this by submitting on the candidate's behalf and guessing answers they do not know, including work authorisation and salary. One wrong guess or one wrong cover letter sent to the wrong employer cannot be taken back.

## Target user
A job seeker in Denmark, targeting product roles, who runs their search with an AI agent (such as Claude Code) and is comfortable in a terminal. They want fewer hours on forms, not less control over what is sent.

## Job to be done
*When a role fits me, I want the application prepared and the form filled with my real details, so that I only review and click Submit, and never send something I would not have written myself.*

## Solution
- **Danish discovery:** a Jobindex.dk provider that plugs into career-ops with no configuration.
- **One-command pipeline:** scan, check the posting is live, cheap triage, full evaluation, tracker update and integrity check, in one run.
- **Application bundles:** one self-contained folder per role (tailored CV, cover letter, facts, checksums), exported only for roles that clear the score bar.
- **Form filler that stops before Submit:** a browser agent fills the form from the bundle only, refuses to click submit, and leaves the tab open for the human.

## In scope
Danish job discovery · triage and evaluation through career-ops · per-role bundles · form filling on Greenhouse and Ashby · macOS and Linux.

## Out of scope (by design)
Submitting applications · guessing any answer that is not in the candidate's profile · storing personal data in the repo · forking career-ops.

## Key assumptions to test
1. A human review step is cheap enough that people keep it, rather than wanting full auto-submit.
2. A higher score bar gives more interviews per application than applying widely.
3. Jobindex stays the highest-yield source for Danish product roles.

## Risks and mitigations
| Risk | Mitigation |
|---|---|
| The agent submits an application | The click action is shadowed in code and refuses submit-like buttons in English and Danish; navigation is limited to the posting's own hosts; a human reviews before anything is sent |
| One employer's cover letter goes to another | Checksums for every file in the bundle, and the runner checks the cover letter names the right company before uploading |
| The agent invents an answer | Facts are copied from the profile, never written by a model; unknown questions stop the run and are recorded word for word |
| Applying twice to the same role | Submitted bundles move to `done/` and are skipped on later runs |
| Personal data leaks into a public repo | The repo holds no personal data; the candidate's files stay in their own checkout and are gitignored |
| Prompt injection in job postings | Posting text is treated as untrusted data in every prompt |

## Success
See [metrics.md](metrics.md).

# Success metrics

career-ops-dk is a personal tool, so volumes are small. This page sets out which metrics it should be run on and how each is measured. Where a number has been measured, it says so.

## North star
**Interviews per application submitted.**
Why: the goal is a job, not a high number of applications. A tool that doubles applications but halves the interview rate has made the search worse. This metric rewards finding the right roles and sending applications the candidate stands behind.

## Supporting metrics

| Area | Metric | Target | How measured |
|---|---|---|---|
| Discovery | Relevant Danish roles found per scan, by source | Track; Jobindex measured at 13 vs 2 from ten company boards | Scan history by provider |
| Discovery | Roles first seen within 2 days of posting | ≥ 80% | Scan date vs posting date |
| Focus | Share of new roles cut at triage before paid evaluation | Track | Shortlist groups |
| Effort | Time from "worth a look" to a form ready for review | < 10 min | Bundle export time to runner finish |
| Cost | Model cost per filled application | ≤ $0.50; measured about $0.26 | API usage per run |
| Quality | Form fields filled correctly at review, without edits | ≥ 90% | Candidate review notes |

## Guardrails (must stay at zero)
- Applications submitted without a human click.
- Answers guessed rather than taken from the profile (authorisation, sponsorship, salary, diversity questions).
- Files sent to the wrong employer.
- Duplicate applications to the same posting.
- Personal data committed to the repo.

## What is not tracked on purpose
Number of applications sent per week. It is easy to raise and says nothing about whether the search is working.

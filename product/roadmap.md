# Roadmap

Now / Next / Later. Items move when evidence changes, not on a date.

## Now (in use)
- Jobindex.dk discovery, one-command pipeline, cheap triage and evaluation
- Per-role bundles with checksums and the right-company check
- Form filler that stops before Submit, with a free dry run
- Choice of tailored or fixed CV
- Runs on macOS and Linux

## Next
- **Block the submit request at network level,** not only the button. The current click guard is text matching; blocking the form's final request is strictly stronger.
- **Record diversity and equal-opportunity answers once in the profile,** so "prefer not to say" is the candidate's recorded choice and not a stop on every form.
- **Narrow what evaluation workers can touch,** removing the need for the upstream permission bypass (D14).
- **Outcome tracking:** log interview invitations against applications, so the north star can be measured rather than estimated.

## Later
- Better handling for Lever (raises a captcha on automated clicks) and Workday (ignores values set by script). Today these end as stops, not fills.
- More Danish sources, if a scan shows roles Jobindex misses.
- An optional encrypted backup of the candidate's checkout, kept off by default.

## Not planned
- Automatic submission.
- Applying below the score bar by default.

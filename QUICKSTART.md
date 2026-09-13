# Quickstart — talking to career-ops

After `./bootstrap.sh`, everything else is a conversation. Open your agent CLI
**inside the career-ops checkout** and say what you want in plain English:

```bash
cd ../career-ops     # important: this directory, not career-ops-dk
claude
```

career-ops' `CLAUDE.md` loads automatically from there, so the agent already
knows the whole system — the modes, the scoring, and which file each kind of
change belongs in. You do not need to learn the file layout; you do need to be
in that directory.

It also finds the additions in this repo — the Jobindex scanner, `run-chain.sh`,
and how applying actually works here. `bootstrap.sh` writes a short pointer into
`modes/_custom.md` (loaded on every mode) that sends the agent to
`AGENT-NOTES.md` in this repo when the question calls for it. So *"apply to this
one"* gets the bundle-and-runner workflow, not a stock answer, without carrying
the full explanation in context all day.

That pointer is managed by `setup.sh`. Your own rules can live in the same file
underneath it and are never touched. To change what agents are told, edit
`AGENT-NOTES.md` here and re-run `./setup.sh`.

## First session

> set me up

It asks for your CV and a few details, then writes `cv.md`,
`config/profile.yml`, `modes/_profile.md` and `portals.yml`. All of it stays on
this machine.

Worth spending ten extra minutes on: when it asks what makes you unique, what
drains you, and your deal-breakers, answer properly. That text is what the
scoring actually reads. A thin profile produces confident, useless scores.

## Refining it later

All of these are just things you say:

| What you want | Say something like |
|---|---|
| More/fewer job titles | *"add Solutions Architect and Delivery Manager to the title filters"* |
| Drop noise from scans | *"stop matching anything with 'Sales' or 'Intern' in the title"* |
| Add companies to watch | *"add Pleo, Zettle and Trustpilot to portals.yml"* |
| Change what counts as a good fit | *"I care more about AI-adjacent work than seniority — reweight that"* |
| Fix a bad score | *"this scored 4.5 but I'd never take it — here's why"* |
| Comp or location rules | *"raise my minimum to 60k DKK/month and drop anything outside Zealand"* |
| A standing house rule | *"always write cover letters in Danish for public-sector roles"* |

The last one is different in kind: house rules and workflow preferences go to
`modes/_custom.md`, while facts and targeting go to `modes/_profile.md` or
`config/profile.yml`. The agent knows this split. **Nothing user-specific ever
belongs in `modes/_shared.md`** — that is a system file, and the next update
overwrites it without asking. If you ever see an agent proposing to edit it,
stop it.

Correcting a score is the highest-value thing you can do. Every *"too high"* or
*"you missed my experience in X"* should end up in `modes/_profile.md`, and the
next evaluation is better for it.

## The application threshold

The score needed to export an application bundle is a flag, not a setting:

```bash
node automation/apply-queue.mjs --min-score 4.0     # default
node automation/apply-queue.mjs --min-score 3.5     # widen the net
node automation/apply-queue.mjs --report 11         # just this one
```

4.0 is career-ops' own advice-against-applying line. Lowering it is a real
decision — it means filling forms for roles the evaluation says are a stretch —
so it is typed each time rather than configured once and forgotten.

Nothing is ever submitted by any of this. The runner fills a form, leaves it
open in a browser tab, and stops. You read it and click Submit yourself.

## Useful things to ask for

> what's in my pipeline?
> follow up on anything I applied to more than two weeks ago
> what skills keep showing up that I don't have?
> prep me for the Queue-it interview
> is this company safe to join?
> write a cover letter for report 11

## When something looks wrong

```bash
node doctor.mjs                 # is the setup sane?
node verify-pipeline.mjs        # is the tracker consistent?
./bootstrap.sh --check          # from career-ops-dk: is everything installed?
```

Or just describe the problem to the agent — it can read all of these itself.

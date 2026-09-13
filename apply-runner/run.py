"""Fill a batch of application forms, one at a time, stopping before submit.

    uv run python run.py ~/job-searcher/handoff            # every pending bundle
    uv run python run.py ~/job-searcher/handoff/011-queue-it   # just one
    uv run python run.py ~/job-searcher/handoff --dry-run  # verify, open no browser
    uv run python run.py ~/job-searcher/handoff --no-pause # never stop, fill everything

Input is a handoff directory written by career-ops' automation/apply-queue.mjs,
or a root holding several. Each bundle is self-contained — job.json, cv.pdf,
cv.md, facts.md and an optional cover-letter.md — so the runner never reaches
into career-ops to decide anything, and never picks a file: there is exactly one
candidate per slot. Bundles under done/ are skipped; those were submitted, and
Greenhouse accepts duplicate applications while Ashby merges them silently by
email, so a second fill would be invisible rather than rejected.

Every bundle is checksum-verified and its cover letter re-asserted against the
company name before the browser opens. Posting liveness is checked here rather
than at export: a bundle can sit for days, and an unmetered browser run against
a dead posting costs real money.

Every form is filled and left open in ITS OWN TAB. Nothing is ever submitted —
a human reviews the tabs and submits by hand.

Jobs are filled one after another in a single browser, and the run does NOT
stop for fields needing your own words: that is the normal outcome, it happens
on every job while no cover letter is generated, and stopping for it would mean
answering prompts during filling and then reviewing every tab again anyway.
Walk away, come back to N filled tabs, work through them.

It DOES stop when something looks wrong — no form reached, no CV attached, a
captcha, or anything that touched the submit path — because continuing past
that spends money on jobs likely to fail the same way. --no-pause overrides.

ONE BROWSER PER JOB, not one browser with a tab per job.

`Agent` takes no page argument: it drives whatever its BrowserSession has
focused. So a shared session means every agent competes for one focus, and the
tab route (new_page + SwitchTabEvent) proved unreliable in browser-use 0.13.10 —
focus landed one step behind, a created tab went missing, and probing it hung.
Observed 2026-09-13 on a real two-job run: ONE tab survived. The second agent
found the first job's filled form, correctly judged it an unrelated page, and
navigated away over the top of it. Both jobs reported success, so the summary
said everything was fine while the first form no longer existed.

A session per job removes the failure by construction rather than timing it
right: each agent owns its browser and cannot touch another job's window. It
costs one Chromium window per job instead of one tab, which is the same review
experience — every filled form stays open until you close it.

It also tightens navigation: allowed_domains is now that job's own hosts, not
the union of every job in the batch.

STOPPING (revised 2026-09-13). The batch stops only when something is WRONG —
no form reached, no CV attached, a captcha, or anything that touched the submit
path — because continuing past that spends money repeating the same failure.

It does NOT stop for a field needing your own words. That is the normal outcome
and, while no cover letter is generated, it happens on every single job; pausing
for it meant answering a prompt per job during filling and then reviewing every
window again afterwards. Fill everything, walk away, work through the windows.
--no-pause disables the remaining stops too.
"""

import asyncio
import os
import sys
from urllib.parse import urlparse

from dotenv import load_dotenv

import bundle as bundles
from bundle import BadBundle
from guards import build_profile, build_tools
from result_model import ApplicationResult

load_dotenv()

MAX_STEPS = 40

TASK = """Open the job application form at {url} and fill it in.

## Identity facts (copy verbatim into matching fields)

- Full name: {full_name}
- Email: {email}
- Phone: {phone}
- City: {city}
- LinkedIn: {linkedin}
- Current job title: {current_title}
- Current employer: {current_employer}
- Currently resident in Denmark: {resident_in_denmark}
- CV/resume file to attach: {cv_path}
{cover_block}

## The fact sheet for this application

<facts>
{facts_md}
</facts>

## The CV (ground truth for anything about experience)

<cv>
{cv_text}
</cv>

## How to answer each field

1. Identity field -> copy the fact above, verbatim.
2. Factual question about her experience ("years in product", "have you worked
   with X", "describe your current role", "are you living in Denmark") ->
   answer from the CV and facts. Stay strictly within what they support: never
   inflate scope, seniority, team size or numbers.
3. A cover letter / motivation letter field, when a cover letter is supplied
   below -> paste it VERBATIM. Do not summarise it, shorten it, rewrite it or
   merge it with the job ad's wording. It was written and fact-checked by
   career-ops before this run; copying it is transcription, not composition.
   If no cover letter is supplied, treat the field as case 4 below.
4. A bespoke opinion or speculative question that no supplied artifact answers
   ("where is product management heading with AI?", "what is the most important
   quality of a product manager?") -> LEAVE EMPTY and record it with
   is_free_text=true. A cover letter does NOT answer these; pasting one in
   would be worse than leaving them blank. These are the candidate's own view.
5. No basis for an answer -> leave empty, record why.
6. Attach the CV file to any resume/CV upload field.

Record every field you filled and every field you skipped in the structured
result. Set captcha_present if a captcha appears. submitted must always be false.

You must NOT submit. Do not click Apply, Submit, Send or any equivalent once
the form is filled.
"""

RULES = """
You are filling a job application on behalf of a real person. Absolute rules:

- NEVER click a final submit/send button. A human submits, always.
- NEVER assert anything the CV and facts do not support. Reformulating what the
  CV says is expected; inventing scope, numbers, seniority, employers, tools or
  achievements is not.
- An empty field is always better than a guess.
- NEVER guess work authorization, visa sponsorship, veteran status, disability
  status or salary expectations. Answer only from the facts given.
- Select dropdown and radio options by exact visible text, never by position.
- If you hit a captcha, stop and report it. Never attempt to solve one.
"""


def blocking_reasons(result, blocked_clicks):
    """Signs something is WRONG, so the batch should stop before spending more.

    Deliberately does not include open questions. A field needing the
    candidate's own words is the normal, expected outcome — with no cover letter
    generated it happens on every job — and stopping the batch for it means
    being prompted once per job during filling, then reviewing everything again
    afterwards. These are the cases where continuing wastes money or hides a
    problem: no form, no CV attached, a captcha, or anything that touched the
    submit path.
    """
    if result is None:
        return ["agent returned no structured result"]
    reasons = []
    if not result.form_found:
        reasons.append("no application form was reached (posting may be dead)")
    if result.captcha_present:
        reasons.append("captcha on the form — only a human may solve it")
    if not result.cv_attached:
        reasons.append("CV was not attached")
    if blocked_clicks:
        reasons.append(f"submit guard blocked {len(blocked_clicks)} click(s): {blocked_clicks}")
    if result.submitted:
        reasons.append("AGENT REPORTED A SUBMIT — investigate before continuing")
    return reasons


def review_notes(result):
    """Normal things the human finishes later, tab by tab. Never stops a batch."""
    if result is None:
        return []
    open_questions = [s.label for s in result.skipped if s.is_free_text]
    if not open_questions:
        return []
    return [f"{len(open_questions)} open question(s) need your own words: "
            f"{'; '.join(open_questions[:3])}"]


async def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    dry_run = "--dry-run" in sys.argv
    pause_on_block = "--no-pause" not in sys.argv
    if len(args) != 1:
        print(__doc__)
        return 2

    # Bundles are validated before the API key is required, so --dry-run works
    # without one and a malformed bundle is reported as a bundle problem rather
    # than hiding behind a missing-key message.
    try:
        jobs = bundles.discover(args[0])
    except BadBundle as exc:
        print(f"Cannot run: {exc}")
        return 1

    if dry_run:
        print(f"{len(jobs)} bundle(s) verified — checksums and cover letters OK\n")
        for job in jobs:
            verdict, detail = bundles.liveness(job.url)
            mark = {"active": "live", "expired": "DEAD", "uncertain": "?", "unchecked": "-"}[verdict]
            print(f"  [{mark:4}] {job.path.name:26} {job.label}")
            print(f"           {job.url}")
            print(f"           cv.md {len(job.cv_md)}B | cover letter: {'yes' if job.cover_letter else 'no'} | {detail}")
        print("\n--dry-run: no browser was opened and no tokens were spent.")
        return 0

    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set. Copy .env.example to .env.")
        return 1

    from browser_use import Agent, BrowserSession, ChatAnthropic

    def allowed_for(url):
        """Just this job's own hosts. A board that hands off to an employer's
        real ATS needs that second host too, which job.json records once it is
        known; until then a handoff posting is expected to fail here."""
        host = urlparse(url).netloc
        if not host:
            return []
        root = ".".join(host.split(".")[-2:])
        return sorted({f"https://{root}", f"https://*.{root}"})

    llm = ChatAnthropic(model=os.getenv("BROWSER_USE_MODEL", "claude-sonnet-5"))

    # browser-use reports no token usage by default, so the per-application cost
    # of this runner was simply unknown — which makes "is this cheaper than a
    # subscription?" unanswerable. Registering the LLM here prints a usage and
    # cost summary at the end of every run. Best-effort: pricing is fetched from
    # the network, and an unmeasured run is better than no run.
    cost = None
    try:
        from browser_use.tokens.service import TokenCost

        cost = TokenCost(include_cost=True)
        cost.register_llm(llm)
    except Exception as exc:  # noqa: BLE001 - accounting must never break a run
        print(f"(token accounting unavailable: {exc})")

    first = jobs[0].identity()
    print(f"Filling as : {first['full_name']} <{first['email']}>")
    print(f"Bundles    : {len(jobs)} (each gets its own browser window)\n")

    summary = []
    sessions = []
    for index, job in enumerate(jobs, start=1):
        label, url, cv = job.label, job.url, job.cv_pdf
        print("=" * 72)
        print(f"[{index}/{len(jobs)}] {label}")
        print(f"          {url}")
        print(f"          bundle: {job.path.name}")
        print(f"          cover letter: {'yes' if job.cover_letter else '(none — cover fields stay empty)'}")
        print("=" * 72)

        verdict, detail = bundles.liveness(url)
        print(f"          liveness: {verdict} ({detail})")
        if verdict == "expired":
            print("  SKIPPED — the posting is gone; no browser run, no tokens spent.")
            summary.append((label, None, ["posting expired — never opened"], []))
            continue

        # This job's own browser. keep_alive=True (see guards.build_profile)
        # keeps the window open after the agent finishes, so the filled form is
        # still there when you get to it.
        try:
            session = BrowserSession(browser_profile=build_profile(allowed_domains=allowed_for(url)))
            await session.start()
            sessions.append(session)
        except Exception as exc:  # noqa: BLE001 - one bad browser must not kill the batch
            print(f"  !! could not start a browser: {exc}")
            summary.append((label, None, [f"browser failed to start: {exc}"], []))
            continue

        tools, state = build_tools()
        agent = Agent(
            task=TASK.format(
                url=url,
                cv_path=cv,
                cv_text=job.cv_md,
                facts_md=job.facts_md,
                cover_block=(
                    "\n## Cover letter for THIS role — paste verbatim into a cover letter field\n\n"
                    f"<cover_letter>\n{job.cover_letter}\n</cover_letter>\n"
                    if job.cover_letter else
                    "\nNo cover letter was supplied for this role. Leave any cover letter\n"
                    "field empty and record it as an open question.\n"
                ),
                **job.identity(),
            ),
            llm=llm,
            tools=tools,
            browser_session=session,
            extend_system_message=RULES,
            available_file_paths=[str(cv)],
            output_model_schema=ApplicationResult,
        )

        result = None
        try:
            history = await agent.run(max_steps=MAX_STEPS)
            raw = history.final_result()
            if raw:
                result = ApplicationResult.model_validate_json(raw)
        except Exception as exc:  # noqa: BLE001 - one bad job must not kill the batch
            print(f"  !! agent error: {exc}")

        blockers = blocking_reasons(result, state.blocked_clicks)
        notes = review_notes(result)
        summary.append((label, result, blockers, notes))

        if result:
            print(f"\n  filled  : {len(result.filled)} field(s)")
            for f in result.filled:
                print(f"            {f.label}: {f.value[:60]}  [{f.source}]")
            print(f"  skipped : {len(result.skipped)} field(s)")
            for s in result.skipped:
                mark = "OPEN Q" if s.is_free_text else "      "
                print(f"     {mark} {s.label}: {s.reason[:60]}")
            print(f"  cv      : {'attached' if result.cv_attached else 'NOT attached'}")
            print(f"  captcha : {'yes' if result.captcha_present else 'no'}")

        for n in notes:
            print(f"\n  for you later: {n}")

        if blockers:
            print("\n  STOPPING — something is wrong here:")
            for r in blockers:
                print(f"    - {r}")
            print("\n  The window is open. Fix or investigate before running the rest.")
            if not sys.stdin.isatty():
                # A blocking prompt with no terminal would EOF and kill the run
                # at the first stop, hiding every job after it.
                print("  [non-interactive: continuing anyway]")
            elif not pause_on_block:
                print("  [--no-pause: continuing anyway]")
            else:
                try:
                    input("  Press Enter to continue anyway (Ctrl-C to stop)... ")
                except (EOFError, KeyboardInterrupt):
                    print("\n  stopping.")
                    break
        else:
            print("\n  filled cleanly — moving to the next job")

    print("\n" + "=" * 72)
    print("BATCH SUMMARY — nothing was submitted")
    print("=" * 72)
    # Three states, not two. A tab that only needs her words is a normal finish;
    # lumping it in with a broken one hides which tabs actually need attention.
    for label, result, blockers, notes in summary:
        if blockers:
            state_text = "PROBLEM"
        elif notes:
            state_text = "your words"
        else:
            state_text = "ready to submit"
        filled = len(result.filled) if result else 0
        print(f"  {state_text:16} {filled:2} filled  {label}")
        for r in blockers + notes:
            print(f"                   - {r}")
    if cost is not None:
        # print(), not log_usage_summary(): that writes at INFO level, so any
        # caller filtering log noise loses exactly the number they asked for.
        try:
            u = await cost.get_usage_summary()
            per = u.total_cost / max(len(jobs), 1)
            print(f"\nTOKENS  in {u.total_prompt_tokens:,} (cached {u.total_prompt_cached_tokens:,})"
                  f"  out {u.total_completion_tokens:,}  over {u.entry_count} call(s)")
            print(f"COST    ${u.total_cost:.4f} total  |  ${per:.4f} per application")
        except Exception as exc:  # noqa: BLE001
            print(f"(could not summarise token usage: {exc})")

    print(f"\n{len(sessions)} browser window(s) open, one per job. Review and submit by hand.")
    if sys.stdin.isatty():
        try:
            input("Press Enter to close the browser... ")
        except (EOFError, KeyboardInterrupt):
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

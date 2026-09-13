"""Fill a real application form from profile facts, and stop before submit.

    uv run python fill_test.py <posting-url>

Fills only the identity fields every form asks for — name, email, phone — and
attaches the CV. It deliberately does NOT answer posting-specific questions:
those are career-ops' `apply` mode output, reviewed by the user, and inventing
them here is exactly the fabrication this system exists to prevent.

Nothing is transmitted. A filled form that is never submitted sends the
employer nothing, which is what makes it safe to run against a live posting.
"""

import asyncio
import os
import sys
from urllib.parse import urlparse

from dotenv import load_dotenv

from facts import MissingFact, cv_pdf, cv_text, identity, load_profile
from guards import build_profile, build_tools

load_dotenv()

TASK = """Open the job application form at {url} and fill it in.

## Identity facts (copy these verbatim into matching fields)

- Full name: {full_name}
- Email: {email}
- Phone: {phone}
- City: {city}
- LinkedIn: {linkedin}
- Current job title: {current_title}
- Current employer: {current_employer}
- Currently resident in Denmark: {resident_in_denmark}
- CV/resume file to attach: {cv_path}

## The CV (ground truth for anything about experience)

This is the candidate's CV, verbatim. Any question about roles,
responsibilities, skills, tools, accomplishments, dates or years of experience
is answered FROM THIS TEXT.

<cv>
{cv_text}
</cv>

## How to answer each field

1. An identity field (name, email, phone, title, employer, location, links):
   copy the fact above, verbatim.
2. A factual question about the candidate's experience ("years in product",
   "have you worked with X", "describe your current role", "are you living in
   Denmark"): answer it from the CV and the facts above. Stay strictly within
   what they support — do not inflate scope, seniority, team size or numbers.
3. An opinion, motivation or speculative question ("Where do you see product
   management heading with AI?", "Why do you want to work here?", "What is the
   most important quality of a product manager?"): LEAVE IT EMPTY. The CV
   cannot answer these, they are the candidate's own view, and she writes them
   herself.
4. Anything else you have no basis for: leave it empty and say so.
5. Attach the CV file to any resume/CV upload field.

In your final report, quote VERBATIM every answer you composed for a type-2
question, so a human can check it before submitting. List type-3 fields you
left empty.

You must NOT submit. Do not click Apply, Submit, Send, or any equivalent once
the form is filled. A human reviews and submits.
"""

RULES = """
You are filling a job application on behalf of a real person. Absolute rules:

- NEVER click a final submit/send button. A human submits, always.
- NEVER assert anything the CV and facts do not support. Reformulating what
  the CV says is fine and expected; inventing scope, numbers, seniority,
  employers, tools or achievements is not.
- An empty field is always better than a guess. Say what you left empty.
- NEVER guess work authorization, visa sponsorship, veteran status, disability
  status, or salary expectations. Answer these only from the facts given.
- Select dropdown and radio options by their exact visible text, never by
  position. Option order varies between sites.
- If you hit a captcha, stop and report it. Do not attempt to solve it.
"""


async def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2

    url = sys.argv[1]
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in.")
        return 1

    try:
        facts = identity(load_profile())
        cv = cv_pdf()
        cv_md = cv_text()
    except MissingFact as exc:
        print(f"Cannot run: {exc}")
        return 1

    host = urlparse(url).netloc
    if not host:
        print(f"Not a usable URL: {url}")
        return 2

    from browser_use import Agent, ChatAnthropic

    # The smoke test proved this posting's form is an on-page modal with no
    # handoff to an external ATS, so the board's own host is the whole surface.
    root = ".".join(host.split(".")[-2:])
    profile = build_profile(allowed_domains=[f"https://{root}", f"https://*.{root}"])
    tools, state = build_tools()

    print(f"Filling as: {facts['full_name']} <{facts['email']}>")
    print(f"Attaching : {cv}")
    print(f"Confined  : {root}\n")

    agent = Agent(
        task=TASK.format(url=url, cv_path=cv, cv_text=cv_md, **facts),
        llm=ChatAnthropic(model=os.getenv("BROWSER_USE_MODEL", "claude-sonnet-5")),
        tools=tools,
        browser_profile=profile,
        extend_system_message=RULES,
        available_file_paths=[str(cv)],
    )

    history = await agent.run(max_steps=40)

    print("\n" + "=" * 70)
    print(history.final_result() or "(no result)")
    print("=" * 70)
    print(f"steps: {len(history.history)}")
    print(f"filling detected by guard: {state.filling_started}")
    print(f"submit clicks blocked: {len(state.blocked_clicks)} {state.blocked_clicks}")

    print("\nThe browser window is still open. Look at the tab.")
    print("Nothing was submitted. Review the form, then submit by hand if you want to.")
    try:
        input("Press Enter to close the browser and exit... ")
    except (EOFError, KeyboardInterrupt):
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

"""One-off: point browser-use at a real posting, fill nothing, prove the stack works.

    uv run python smoke_test.py <posting-url>

Opens the posting, reads the application form, and reports what fields it
found. It does not fill or submit anything — this exists to answer "does
browser-use work on this machine, and what does one page cost".
"""

from __future__ import annotations

import asyncio
import os
import sys
from urllib.parse import urlparse

from dotenv import load_dotenv

from guards import build_profile, build_tools

load_dotenv()

TASK = """Open the job posting at {url} and find its application form.

Report back, via the done action:
1. The job title and company.
2. Every field the application form asks for, listed verbatim.
3. For each field, whether it is required.
4. Any question that is a legal declaration (work authorization, visa
   sponsorship, veteran status, disability status).

Do NOT fill in any field. Do NOT click any submit button. Look and report only.
"""

RULES = """
You are filling job applications on behalf of a real person. Absolute rules:

- NEVER click a final submit/send button. A human submits, always.
- NEVER invent an answer. If you do not have a fact, say so and stop.
- NEVER guess work authorization, visa sponsorship, veteran status,
  disability status, or salary expectations. These are legal declarations.
- Select dropdown and radio options by their exact visible text, never by
  position. Option order varies between sites.
- If you hit a captcha, stop and report it.
"""


async def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2

    url = sys.argv[1]
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in.")
        return 1

    from browser_use import Agent, ChatAnthropic

    host = urlparse(url).netloc
    if not host:
        print(f"Not a usable URL: {url}")
        return 2

    # NOTE: no allowed_domains on the smoke test, on purpose.
    #
    # Job boards like The Hub hand off to the employer's real ATS (Greenhouse,
    # Ashby, Teamtailor) for the actual form. Confining navigation to the
    # posting's own host would block that jump and the run would die before
    # ever seeing a form — which is the one thing this pass exists to find.
    #
    # Safe here because this pass is read-only: it fills nothing and submits
    # nothing, and max_steps is short. The real runner DOES restrict, to the
    # hosts this pass discovers.
    profile = build_profile(allowed_domains=None)

    agent = Agent(
        task=TASK.format(url=url),
        llm=ChatAnthropic(model=os.getenv("BROWSER_USE_MODEL", "claude-sonnet-5")),
        tools=build_tools()[0],
        browser_profile=profile,
        extend_system_message=RULES,
    )

    history = await agent.run(max_steps=40)

    print("\n" + "=" * 70)
    print(history.final_result() or "(no result)")
    print("=" * 70)
    print(f"steps: {len(history.history)}  |  urls visited: {history.urls()}")

    # Hold the process open so the browser window stays up for inspection.
    # keep_alive=True stops browser-use closing it; this stops Python exiting
    # and taking the child process with it. In the real runner this is the
    # review-and-submit pause.
    print("\nThe browser window is still open. Look at the tab.")
    print("Nothing was filled and nothing was submitted — this was a read-only pass.")
    try:
        input("Press Enter to close the browser and exit... ")
    except (EOFError, KeyboardInterrupt):
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

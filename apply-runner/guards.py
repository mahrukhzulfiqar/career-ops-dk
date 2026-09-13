"""Safety core for the apply-runner.

Everything here enforces one rule: the agent fills forms, a human submits them.
See ../overlay/automation/BROWSER_USE_SCOPE.md.

NOTE: deliberately NO `from __future__ import annotations` in this module. It
stringifies annotations, and browser-use's registry compares the
`browser_session` annotation against the real class — a string never matches,
so registration is refused with a "conflicts with special argument" error.
"""

import logging
import re
import unicodedata
from dataclasses import dataclass, field

from browser_use import BrowserProfile, Tools
from browser_use.browser.session import BrowserSession
from browser_use.filesystem.file_system import FileSystem
from browser_use.tools.views import (
    ClickElementActionIndexOnly,
    InputTextAction,
    SelectDropdownOptionAction,
    UploadFileAction,
)

log = logging.getLogger(__name__)

# Actions removed from the registry entirely. `evaluate` runs arbitrary
# JavaScript, which turns any hostile text on a job page into code execution;
# the file actions give a web page a route to the filesystem. `upload_file` is
# deliberately KEPT — attaching the CV needs it.
EXCLUDED_ACTIONS = [
    "evaluate",
    "read_file",
    "write_file",
    "replace_file",
    "search",
    "switch",
    "close",
]

# Labels that always mean "this posts the application", whatever else is true.
ALWAYS_BLOCKED_SUBSTRINGS = [
    "submit application",
    "send application",
    "submit my application",
    "complete application",
    "finish application",
    "send ansøgning",
    "indsend ansøgning",
    "indsend ansøgningen",
    "afsend ansøgning",
]
ALWAYS_BLOCKED_EXACT = ["submit", "indsend", "afsend"]

# Labels that mean "open the application form" BEFORE anything has been
# filled, and "submit it" afterwards.
#
# This tier exists because of a real observation, not a hypothetical: on
# thehub.io the button that opens the modal and the button that posts the
# application are BOTH labelled "Apply" (verified 2026-09-09 against
# Embankment / Senior Product Manager). Blocking "Apply" outright would stop
# every run before it began; allowing it outright would let the submit through.
AMBIGUOUS_ONCE_FILLING_STARTS = [
    "apply",
    "apply now",
    "apply for this position",
    "ansøg",
    "ansøg nu",
    "send",
    "continue",
    "fortsæt",
]


@dataclass
class RunState:
    """Tracks whether the agent has begun entering data."""

    filling_started: bool = False
    blocked_clicks: list = field(default_factory=list)

    def mark_filling(self, what: str) -> None:
        if not self.filling_started:
            log.info("filling has started (%s) — ambiguous submit labels now blocked", what)
        self.filling_started = True


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


# A verb that posts, and the thing it posts. Matched as TOKENS rather than as an
# adjacent phrase, because adjacency is what the substring list got wrong: an
# adversarial run on 2026-09-13 blocked "Submit application" five times and then
# submitted through "Indsend ansogning", and the same list also let through
# "Submit your application", "Send my application" and "Complete your
# application" — ordinary ATS labels, defeated by one word in the middle.
SUBMIT_VERBS = frozenset({
    "submit", "send", "complete", "finish", "confirm",
    "indsend", "afsend", "bekraeft", "faerdiggor",
})
APPLICATION_NOUNS = frozenset({
    "application", "applications",
    "ansogning", "ansogningen", "ansogninger",
})

# Danish keyboard characters do not decompose under NFKD, and the DOM text a
# site serves may be folded, unfolded, or inconsistently either.
_FOLD = str.maketrans({"ø": "o", "Ø": "o", "æ": "ae", "Æ": "ae", "å": "a", "Å": "a"})


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.translate(_FOLD))
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def looks_like_final_submit(text: str, filling_started: bool = False) -> bool:
    """Would clicking this element post the application?

    `filling_started` promotes the ambiguous tier. Before any data is entered,
    "Apply" opens a form; after, it sends one.

    Still a heuristic, and still not the guarantee: a button labelled something
    this does not anticipate gets through, which is why a human reviews the
    filled form before anything is sent.
    """
    normalized = _fold(_normalize(text))
    if not normalized:
        return False
    # Both sides are folded: folding only the input silently un-matched the
    # Danish entries in these lists, which a passing test caught.
    if normalized in {_fold(label) for label in ALWAYS_BLOCKED_EXACT}:
        return True
    if any(_fold(label) in normalized for label in ALWAYS_BLOCKED_SUBSTRINGS):
        return True

    # verb + noun anywhere in the label, in any order, with anything between
    tokens = set(re.findall(r"[a-z]+", normalized))
    if tokens & SUBMIT_VERBS and tokens & APPLICATION_NOUNS:
        return True

    if filling_started and normalized in {_fold(label) for label in AMBIGUOUS_ONCE_FILLING_STARTS}:
        return True
    return False


def _element_text(element) -> str:
    """Best-effort visible text for a DOM element, across browser-use versions."""
    for attr in ("text", "inner_text", "node_value"):
        value = getattr(element, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()

    get_text = getattr(element, "get_all_children_text", None)
    if callable(get_text):
        try:
            value = get_text()
            if isinstance(value, str) and value.strip():
                return value.strip()
        except Exception:  # noqa: BLE001 - never let a guard crash the run
            log.debug("get_all_children_text failed", exc_info=True)

    attributes = getattr(element, "attributes", None) or {}
    for key in ("aria-label", "value", "title"):
        value = attributes.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return ""


def build_tools(state: RunState = None) -> tuple:
    """Tools registry with file/JS actions removed and submit-clicks guarded.

    Returns (tools, state). Registering an action of the same name shadows the
    built-in — verified against browser-use 0.13.10. `param_model` is REQUIRED
    on every shadow: without it the registry infers the schema from the
    signature, defaults an unannotated parameter to `str`, and the original
    function fails with "'str' object has no attribute 'model_dump'".

    HONEST LIMIT: still text matching. A submit button with an unusual label
    and no data entered yet gets through. The backstop is that a human reviews
    the filled form on screen, and allowed_domains keeps a stray submit on the
    posting's own host.
    """
    state = state or RunState()
    tools = Tools(exclude_actions=EXCLUDED_ACTIONS)
    registry = tools.registry.registry.actions
    original_click = registry["click"].function
    original_input = registry["input"].function
    original_select = registry["select_dropdown"].function
    original_upload = registry["upload_file"].function

    @tools.action("Click element by index.", param_model=ClickElementActionIndexOnly)
    async def click(params: ClickElementActionIndexOnly, browser_session: BrowserSession):
        index = getattr(params, "index", None)
        try:
            element = await browser_session.get_dom_element_by_index(index)
            text = _element_text(element) if element is not None else ""
        except Exception:  # noqa: BLE001 - a lookup failure must not auto-allow
            log.warning("could not resolve element %s; refusing click", index)
            return (
                f"REFUSED: could not identify element {index}, so it could not be "
                "checked against the submit guard. Take a screenshot and stop."
            )

        if looks_like_final_submit(text, state.filling_started):
            state.blocked_clicks.append(text)
            log.warning("BLOCKED submit-like click on %r (filling_started=%s)", text, state.filling_started)
            return (
                f"REFUSED: element {index} ({text!r}) would submit the application. "
                "You must never submit — a human does that. The form is filled; "
                "call done and stop."
            )

        return await original_click(params=params, browser_session=browser_session)

    # Every shadow must mirror the built-in's FULL signature, special injected
    # parameters included. Declaring fewer means the original is called without
    # them and fails at runtime — `upload_file` losing `available_file_paths`
    # is how the first fill test failed to attach a CV, five times over.
    @tools.action("Input text into an element.", param_model=InputTextAction)
    async def input(  # noqa: A001
        params: InputTextAction,
        browser_session: BrowserSession,
        has_sensitive_data: bool = False,
    ):
        state.mark_filling("text input")
        return await original_input(
            params=params,
            browser_session=browser_session,
            has_sensitive_data=has_sensitive_data,
        )

    @tools.action("Select a dropdown option.", param_model=SelectDropdownOptionAction)
    async def select_dropdown(params: SelectDropdownOptionAction, browser_session: BrowserSession):
        state.mark_filling("dropdown selection")
        return await original_select(params=params, browser_session=browser_session)

    @tools.action("Upload a file to an element.", param_model=UploadFileAction)
    async def upload_file(
        params: UploadFileAction,
        browser_session: BrowserSession,
        available_file_paths: list,
        file_system: FileSystem,
    ):
        state.mark_filling("file upload")
        return await original_upload(
            params=params,
            browser_session=browser_session,
            available_file_paths=available_file_paths,
            file_system=file_system,
        )

    return tools, state


def build_profile(allowed_domains, downloads_path: str = None) -> BrowserProfile:
    """Visible browser, confined to the posting's own hosts, left open at the end.

    allowed_domains is enforced at navigation, not in the prompt. Entries must
    be scheme-qualified (https://boards.greenhouse.io) or globs
    (https://*.greenhouse.io) — a malformed entry blocks every URL including
    the ones you meant to allow (browser-use issue #3153). Pass None only for
    read-only passes.

    headless=False is the product, not a debug setting: the filled form on
    screen is what the human reviews. keep_alive=True stops browser-use tearing
    the window down when the agent finishes — without it the filled form
    vanishes at the moment it is needed.
    """
    if allowed_domains is None:
        log.warning("allowed_domains is None — navigation is UNRESTRICTED (read-only passes only)")

    return BrowserProfile(
        allowed_domains=allowed_domains,
        headless=False,
        keep_alive=True,
        downloads_path=downloads_path,
    )

"""Regression tests for the safety core.

Two bug classes are pinned here, both of which reached a live application form
before being caught:

1. A shadowed action registered without `param_model`, so browser-use inferred
   the schema from the signature and defaulted the parameter to `str`. The
   original then failed with "'str' object has no attribute 'model_dump'".
2. A shadowed action that did not declare every special parameter the built-in
   declares, so the original was called without them. `upload_file` lost
   `available_file_paths` and failed to attach a CV five times in a row.

Both are structural, so both are testable without a browser.
"""

import inspect

import pytest
from browser_use import Tools

from guards import EXCLUDED_ACTIONS, RunState, build_tools, looks_like_final_submit

SHADOWED = ["click", "input", "select_dropdown", "upload_file"]


@pytest.fixture(scope="module")
def builtin_actions():
    return Tools().registry.registry.actions


@pytest.fixture(scope="module")
def guarded_actions():
    tools, _ = build_tools()
    return tools.registry.registry.actions


@pytest.mark.parametrize("name", SHADOWED)
def test_shadow_replaces_the_builtin(name, guarded_actions):
    assert guarded_actions[name].function.__name__ == name


@pytest.mark.parametrize("name", SHADOWED)
def test_shadow_declares_a_param_model(name, guarded_actions, builtin_actions):
    # Bug class 1: without param_model the registry infers `str`.
    assert guarded_actions[name].param_model is builtin_actions[name].param_model


@pytest.mark.parametrize("name", SHADOWED)
def test_shadow_accepts_every_injected_parameter(name, guarded_actions, builtin_actions):
    # Bug class 2: a missing special param breaks the call to the original.
    expected = set(inspect.signature(builtin_actions[name].function).parameters)
    actual = set(inspect.signature(guarded_actions[name].function).parameters)
    assert not (expected - actual), f"{name} is missing {sorted(expected - actual)}"


def test_dangerous_actions_are_excluded(guarded_actions):
    for action in EXCLUDED_ACTIONS:
        assert action not in guarded_actions


def test_upload_file_is_kept(guarded_actions):
    # Attaching the CV needs it; excluding it would silently break every run.
    assert "upload_file" in guarded_actions


@pytest.mark.parametrize("label", ["Submit", "Submit application", "Send ansøgning", "Indsend"])
def test_unambiguous_submit_is_always_blocked(label):
    assert looks_like_final_submit(label, filling_started=False)
    assert looks_like_final_submit(label, filling_started=True)


@pytest.mark.parametrize("label", ["Apply", "Apply now", "Apply for this position", "Ansøg"])
def test_apply_opens_before_filling_and_submits_after(label):
    # thehub.io labels BOTH the modal-opening button and the submit button
    # "Apply" (verified 2026-09-09). Only the sequence disambiguates them.
    assert not looks_like_final_submit(label, filling_started=False)
    assert looks_like_final_submit(label, filling_started=True)


@pytest.mark.parametrize("label", ["Next", "Back", "Save draft", "Submit a question", ""])
def test_benign_labels_are_never_blocked(label):
    assert not looks_like_final_submit(label, filling_started=False)
    assert not looks_like_final_submit(label, filling_started=True)


def test_state_starts_unfilled_and_latches():
    state = RunState()
    assert state.filling_started is False
    state.mark_filling("text input")
    assert state.filling_started is True


# --- Regression: the adversarial run of 2026-09-13 ---------------------------
# The guard blocked "Submit application" five times, then the agent submitted
# through "Indsend ansogning". The substring list required verb and noun to be
# ADJACENT, so one word in the middle — or a folded Danish character — defeated
# it. These are ordinary ATS labels, not exotic ones.

import pytest

from guards import looks_like_final_submit


@pytest.mark.parametrize("label", [
    "Submit application",
    "Submit your application",
    "Send my application",
    "Complete your application",
    "Finish your application",
    "Indsend ansøgning",
    "Indsend ansogning",          # folded ø — the label that actually got through
    "Indsend din ansøgning",
    "Send ansøgningen nu",
    "Afsend ansøgning",
    "submit",
    "indsend",
])
def test_submit_labels_are_blocked(label):
    assert looks_like_final_submit(label, filling_started=True), f"{label!r} must be blocked"


@pytest.mark.parametrize("label", [
    "Save draft",
    "Gem kladde",
    "Add another file",
    "Application form",      # noun without a verb is not a submit
    "Upload CV",
    "Back",
])
def test_non_submit_labels_are_allowed(label):
    """Over-blocking makes the runner useless; it must not block everything."""
    assert not looks_like_final_submit(label, filling_started=True), f"{label!r} must be allowed"

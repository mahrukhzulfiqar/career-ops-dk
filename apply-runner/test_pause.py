"""Cover for what stops a batch and what does not.

Getting this wrong is expensive in both directions: stopping on a normal open
question means a prompt per job during filling, and NOT stopping on a real
failure means paying to repeat that failure on every remaining job.
"""

from types import SimpleNamespace as NS

from run import blocking_reasons, review_notes


def skipped(label, free_text):
    return NS(label=label, reason="", is_free_text=free_text)


def result(**kw):
    base = dict(form_found=True, captcha_present=False, cv_attached=True,
                submitted=False, filled=[], skipped=[])
    base.update(kw)
    return NS(**base)


# --- the normal case: an open question must NOT stop the batch
def test_open_question_is_not_blocking():
    r = result(skipped=[skipped("Cover letter", True)])
    assert blocking_reasons(r, []) == []
    assert len(review_notes(r)) == 1


def test_cover_letter_plus_opinion_question_still_not_blocking():
    r = result(skipped=[skipped("Cover letter", True), skipped("Why us?", True)])
    assert blocking_reasons(r, []) == []
    assert "2 open question" in review_notes(r)[0]


def test_a_clean_fill_has_neither():
    r = result()
    assert blocking_reasons(r, []) == []
    assert review_notes(r) == []


def test_non_free_text_skip_is_not_a_review_note():
    """An optional file field left empty needs nothing from her."""
    r = result(skipped=[skipped("Additional files", False)])
    assert review_notes(r) == []


# --- the failure cases: these MUST stop
def test_no_form_blocks():
    assert blocking_reasons(result(form_found=False), []) != []


def test_missing_cv_blocks():
    assert blocking_reasons(result(cv_attached=False), []) != []


def test_captcha_blocks():
    assert blocking_reasons(result(captcha_present=True), []) != []


def test_blocked_submit_click_blocks():
    """The guard firing means the agent tried to submit. Stop and look."""
    assert blocking_reasons(result(), ["Submit application"]) != []


def test_reported_submit_blocks_loudly():
    reasons = blocking_reasons(result(submitted=True), [])
    assert any("SUBMIT" in r for r in reasons)


def test_no_result_blocks():
    assert blocking_reasons(None, []) != []
    assert review_notes(None) == []


def test_a_failure_still_blocks_when_there_are_open_questions_too():
    """An open question must never mask a real failure."""
    r = result(cv_attached=False, skipped=[skipped("Cover letter", True)])
    assert blocking_reasons(r, []) != []

"""Structured result the agent must return for each application.

The adaptive pause rule reads these fields, so they must be machine-readable
facts rather than prose. Asking the model to describe what it did in a
paragraph and then parsing that paragraph is how a pause condition gets
silently missed.
"""

from pydantic import BaseModel, Field


class FilledField(BaseModel):
    label: str = Field(description="The form field's visible label, verbatim")
    value: str = Field(description="Exactly what was entered")
    source: str = Field(description="'identity fact' or 'composed from CV'")


class SkippedField(BaseModel):
    label: str = Field(description="The form field's visible label, verbatim")
    reason: str = Field(description="Why it was left empty")
    is_free_text: bool = Field(description="True if it is an open/essay question needing the candidate's own words")


class ApplicationResult(BaseModel):
    company: str
    role: str
    form_found: bool = Field(description="False if no application form could be reached")
    filled: list[FilledField]
    skipped: list[SkippedField]
    cv_attached: bool
    captcha_present: bool = Field(description="True if a captcha appears anywhere on the form")
    submitted: bool = Field(description="Must always be False. A human submits.")
    notes: str = Field(description="Anything the reviewer should know, one or two sentences")

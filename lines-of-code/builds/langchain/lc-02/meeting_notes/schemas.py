"""Typed data contracts shared across the pipeline.

``FinalNotes`` is the structured-output schema the orchestrator is forced to
return. Keeping the two sections as separate, typed fields is what lets the
deterministic renderer guarantee the output contract instead of trusting the
model to emit exact Markdown headers.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class FinalNotes(BaseModel):
    """The orchestrator's reconciled output, before contract rendering."""

    executive_summary: str = Field(
        ...,
        description=(
            "A 3-4 sentence executive summary, strictly under 100 words, focused "
            "on what was decided and what happens next. No header, no bullet "
            "points, no preamble - just the summary prose."
        ),
    )
    follow_up_email: str = Field(
        ...,
        description=(
            "A follow-up email body, strictly under 200 words, in a plain "
            "professional tone. Greet attendees by name, recap the decisions, "
            "list action items with their owners and deadlines, and propose next "
            "steps. No subject line and no header - just the email body."
        ),
    )

"""Output-contract enforcement.

The stop condition is a strict two-section document. We never trust a single
LLM call to hit it exactly, so this module provides:

- ``assemble_deterministic`` -- build the document directly from the two
  sub-agent outputs (no LLM), used as a guaranteed fallback.
- ``validate_contract`` -- check headers, ordering, and word limits, returning
  a list of human-readable problems (empty == valid).
- ``strip_fences`` -- defensive cleanup of accidental ``` code fences.
"""
from __future__ import annotations

import re

from .prompts import (
    EMAIL_HEADER,
    EMAIL_WORD_LIMIT,
    SUMMARY_HEADER,
    SUMMARY_WORD_LIMIT,
)


def strip_fences(text: str) -> str:
    """Remove a single wrapping ```/```markdown code fence if present."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z]*\n", "", stripped)
        if stripped.endswith("```"):
            stripped = stripped[: -len("```")]
    return stripped.strip()


def assemble_deterministic(summary: str, email: str) -> str:
    """Build a contract-compliant document straight from sub-agent outputs."""
    return (
        f"{SUMMARY_HEADER}\n\n{summary.strip()}\n\n"
        f"{EMAIL_HEADER}\n\n{email.strip()}\n"
    )


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w[\w'-]*\b", text))


def _section_body(text: str, header: str, next_header: str | None) -> str:
    """Return the body text following ``header`` up to ``next_header`` (or EOF)."""
    start = text.find(header)
    if start == -1:
        return ""
    start += len(header)
    end = text.find(next_header, start) if next_header else -1
    return text[start:end].strip() if end != -1 else text[start:].strip()


def validate_contract(text: str) -> list[str]:
    """Return a list of contract violations. Empty list means the text is valid."""
    problems: list[str] = []

    if SUMMARY_HEADER not in text:
        problems.append(f"missing header '{SUMMARY_HEADER}'")
    if EMAIL_HEADER not in text:
        problems.append(f"missing header '{EMAIL_HEADER}'")

    # Ordering: summary section must precede the email section.
    if SUMMARY_HEADER in text and EMAIL_HEADER in text:
        if text.find(SUMMARY_HEADER) > text.find(EMAIL_HEADER):
            problems.append("summary section must come before the email section")

        summary_body = _section_body(text, SUMMARY_HEADER, EMAIL_HEADER)
        email_body = _section_body(text, EMAIL_HEADER, None)

        if not summary_body:
            problems.append("executive summary body is empty")
        elif _word_count(summary_body) > SUMMARY_WORD_LIMIT:
            problems.append(
                f"summary is {_word_count(summary_body)} words "
                f"(limit {SUMMARY_WORD_LIMIT})"
            )

        if not email_body:
            problems.append("email body is empty")
        elif _word_count(email_body) > EMAIL_WORD_LIMIT:
            problems.append(
                f"email is {_word_count(email_body)} words (limit {EMAIL_WORD_LIMIT})"
            )

    return problems

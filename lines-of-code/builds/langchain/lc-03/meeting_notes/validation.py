"""Output-contract validation and deterministic assembly.

The system MUST always return:

    ## Executive Summary

    <summary>

    ## Draft Follow-up Email

    <email body>

`validate_contract` reports structural violations. `assemble_deterministic`
builds a guaranteed-compliant document from the raw sub-agent outputs and is
used as a fallback when the orchestrator LLM drifts from the contract.
"""

from __future__ import annotations

import re

from .prompts import (
    EMAIL_HEADER,
    EMAIL_MAX_WORDS,
    SUMMARY_HEADER,
    SUMMARY_MAX_WORDS,
)


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w[\w'-]*\b", text))


def _strip_accidental_header(body: str, header: str) -> str:
    """Remove a leading markdown header a sub-agent may have added anyway."""

    stripped = body.strip()
    if stripped.lower().startswith(header.lower()):
        stripped = stripped[len(header):].lstrip("\n").lstrip()
    return stripped


def split_sections(text: str) -> tuple[str | None, str | None]:
    """Return ``(summary_body, email_body)`` parsed from a contract document.

    Either element is ``None`` if its header is absent.
    """

    summary_body: str | None = None
    email_body: str | None = None

    if SUMMARY_HEADER in text and EMAIL_HEADER in text:
        after_summary = text.split(SUMMARY_HEADER, 1)[1]
        summary_part, email_part = after_summary.split(EMAIL_HEADER, 1)
        summary_body = summary_part.strip() or None
        email_body = email_part.strip() or None
    return summary_body, email_body


def validate_contract(text: str, *, strict_word_limits: bool = False) -> list[str]:
    """Return a list of contract violations (empty list == compliant).

    Structural checks (headers, ordering, non-empty bodies) are always
    enforced. Word-limit checks are advisory by default because real model
    output occasionally lands a few words over; pass ``strict_word_limits=True``
    to treat them as violations.
    """

    violations: list[str] = []

    if SUMMARY_HEADER not in text:
        violations.append(f"missing header '{SUMMARY_HEADER}'")
    if EMAIL_HEADER not in text:
        violations.append(f"missing header '{EMAIL_HEADER}'")

    if violations:
        return violations  # cannot meaningfully parse further

    if text.index(SUMMARY_HEADER) > text.index(EMAIL_HEADER):
        violations.append("sections are out of order")

    summary_body, email_body = split_sections(text)
    if not summary_body:
        violations.append("executive summary body is empty")
    if not email_body:
        violations.append("email body is empty")

    if summary_body:
        wc = _word_count(summary_body)
        if wc > SUMMARY_MAX_WORDS:
            msg = f"summary is {wc} words (limit {SUMMARY_MAX_WORDS})"
            violations.append(msg) if strict_word_limits else _advisory(msg)
    if email_body:
        wc = _word_count(email_body)
        if wc > EMAIL_MAX_WORDS:
            msg = f"email is {wc} words (limit {EMAIL_MAX_WORDS})"
            violations.append(msg) if strict_word_limits else _advisory(msg)

    return violations


def _advisory(message: str) -> None:
    import logging

    logging.getLogger("meeting_notes").warning("contract advisory: %s", message)


def assemble_deterministic(summary_body: str, email_body: str) -> str:
    """Build a guaranteed contract-compliant document from raw parts."""

    summary = _strip_accidental_header(summary_body, SUMMARY_HEADER)
    email = _strip_accidental_header(email_body, EMAIL_HEADER)
    return (
        f"{SUMMARY_HEADER}\n\n"
        f"{summary}\n\n"
        f"{EMAIL_HEADER}\n\n"
        f"{email}\n"
    )

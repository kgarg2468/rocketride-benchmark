"""Deterministic post-checks against the output contract.

LLM output is non-deterministic, so after the orchestrator returns we verify the
document structurally. Hard structural failures raise ``ValidationError``;
soft constraint violations (e.g. a summary a few words over budget) are returned
as warnings so the caller can log them without aborting a usable result.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .errors import ValidationError

SUMMARY_HEADER = "## Executive Summary"
EMAIL_HEADER = "## Draft Follow-up Email"

SUMMARY_WORD_LIMIT = 100
EMAIL_WORD_LIMIT = 200


@dataclass
class ValidationResult:
    summary: str
    email: str
    warnings: list[str] = field(default_factory=list)


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w[\w'-]*\b", text))


def validate_document(document: str) -> ValidationResult:
    """Parse and validate the final document.

    Raises:
        ValidationError: if a required header is missing or sections are empty.
    """
    if SUMMARY_HEADER not in document:
        raise ValidationError(f"Missing required header: {SUMMARY_HEADER!r}")
    if EMAIL_HEADER not in document:
        raise ValidationError(f"Missing required header: {EMAIL_HEADER!r}")
    if document.index(SUMMARY_HEADER) > document.index(EMAIL_HEADER):
        raise ValidationError("Sections are out of order (summary must precede email).")

    _, after_summary = document.split(SUMMARY_HEADER, 1)
    summary_part, email_part = after_summary.split(EMAIL_HEADER, 1)
    summary = summary_part.strip()
    email = email_part.strip()

    if not summary:
        raise ValidationError("Executive Summary section is empty.")
    if not email:
        raise ValidationError("Draft Follow-up Email section is empty.")

    warnings: list[str] = []
    summary_words = _word_count(summary)
    if summary_words >= SUMMARY_WORD_LIMIT:
        warnings.append(
            f"Executive Summary is {summary_words} words "
            f"(contract: under {SUMMARY_WORD_LIMIT})."
        )
    sentence_count = len(re.findall(r"[.!?](?:\s|$)", summary))
    if not 3 <= sentence_count <= 4:
        warnings.append(
            f"Executive Summary has ~{sentence_count} sentences (contract: 3-4)."
        )

    email_words = _word_count(email)
    if email_words >= EMAIL_WORD_LIMIT:
        warnings.append(
            f"Follow-up Email is {email_words} words "
            f"(contract: under {EMAIL_WORD_LIMIT})."
        )

    return ValidationResult(summary=summary, email=email, warnings=warnings)

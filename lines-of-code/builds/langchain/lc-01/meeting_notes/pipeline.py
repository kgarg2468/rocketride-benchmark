"""Orchestration: fan-out to the two sub-agents in parallel, fan-in to the
orchestrator, then deterministically guarantee the output contract.

Parallelism uses ``RunnableParallel`` driven by ``ainvoke`` so the summary and
email agents execute as concurrent asyncio tasks (not sequentially). An
``asyncio.wait_for`` wraps each stage as a wall-clock backstop above the
per-call HTTP timeouts.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass

from langchain_core.runnables import RunnableParallel

from .agents import build_agents
from .config import AppConfig, load_config
from .observability import TracingCallbackHandler
from .prompts import EMAIL_HEADER, EXEC_SUMMARY_HEADER

logger = logging.getLogger("meeting_notes")


class PipelineError(RuntimeError):
    """Raised when the system cannot produce a valid result."""


@dataclass
class MeetingNotes:
    """Structured result. ``final_document`` satisfies the output contract."""

    executive_summary: str
    draft_email: str
    final_document: str


# --------------------------------------------------------------------------- #
# Deterministic contract enforcement
# --------------------------------------------------------------------------- #
def _strip_known_headers(text: str) -> str:
    """Remove any contract headers a model may have prepended to a section."""

    cleaned = text.strip()
    for header in (EXEC_SUMMARY_HEADER, EMAIL_HEADER):
        if cleaned.startswith(header):
            cleaned = cleaned[len(header):].lstrip("\n").strip()
    return cleaned


def _word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


def enforce_contract(
    orchestrated: str, *, summary_fallback: str, email_fallback: str
) -> str:
    """Guarantee the exact two-section format.

    If the orchestrator already emitted both headers in order, normalise and
    return it. Otherwise rebuild the document deterministically from the raw
    sub-agent outputs. Either way the stop condition is met by construction.
    """

    text = (orchestrated or "").strip()
    has_summary = EXEC_SUMMARY_HEADER in text
    has_email = EMAIL_HEADER in text
    in_order = (
        has_summary
        and has_email
        and text.index(EXEC_SUMMARY_HEADER) < text.index(EMAIL_HEADER)
    )

    if in_order:
        # Trim anything before the first header (defensive against preamble).
        document = text[text.index(EXEC_SUMMARY_HEADER):].strip()
    else:
        logger.warning(
            "Orchestrator output did not match the contract; rebuilding "
            "deterministically from sub-agent outputs."
        )
        document = (
            f"{EXEC_SUMMARY_HEADER}\n\n{_strip_known_headers(summary_fallback)}\n\n"
            f"{EMAIL_HEADER}\n\n{_strip_known_headers(email_fallback)}"
        )

    _warn_on_length(document)
    return document


def _warn_on_length(document: str) -> None:
    """Log (do not fail) if a section exceeds its word budget."""

    parts = document.split(EMAIL_HEADER, 1)
    summary_body = parts[0].replace(EXEC_SUMMARY_HEADER, "").strip()
    email_body = parts[1].strip() if len(parts) > 1 else ""
    if _word_count(summary_body) > 100:
        logger.warning("Executive summary exceeds 100 words (%d).", _word_count(summary_body))
    if _word_count(email_body) > 200:
        logger.warning("Draft email exceeds 200 words (%d).", _word_count(email_body))


# --------------------------------------------------------------------------- #
# Async orchestration
# --------------------------------------------------------------------------- #
async def _run_async(transcript: str, cfg: AppConfig) -> MeetingNotes:
    agents = build_agents(cfg)
    tracer = TracingCallbackHandler()
    run_config = {"callbacks": [tracer]}

    # Fan-out: both sub-agents share one input and run concurrently.
    parallel = RunnableParallel(
        executive_summary=agents.summarizer,
        draft_email=agents.emailer,
    ).with_config(run_name="parallel_subagents", tags=["orchestration", "parallel"])

    logger.info("Dispatching summary + email sub-agents in parallel...")
    try:
        sections = await asyncio.wait_for(
            parallel.ainvoke({"transcript": transcript}, config=run_config),
            timeout=cfg.stage_timeout,
        )
    except asyncio.TimeoutError as exc:
        raise PipelineError(
            f"Sub-agent stage exceeded {cfg.stage_timeout:.0f}s wall-clock budget."
        ) from exc
    except Exception as exc:  # retries already exhausted inside the chains
        raise PipelineError(f"Sub-agent execution failed: {exc}") from exc

    summary = (sections.get("executive_summary") or "").strip()
    email = (sections.get("draft_email") or "").strip()
    if not summary or not email:
        raise PipelineError("A sub-agent returned an empty result.")

    # Fan-in: orchestrator assembles the final document.
    logger.info("Sub-agents complete; orchestrator assembling final document...")
    try:
        orchestrated = await asyncio.wait_for(
            agents.orchestrator.ainvoke(
                {"executive_summary": summary, "draft_email": email},
                config=run_config,
            ),
            timeout=cfg.stage_timeout,
        )
    except asyncio.TimeoutError as exc:
        logger.warning("Orchestrator timed out; using deterministic assembly.")
        orchestrated = ""  # triggers the deterministic fallback below
    except Exception as exc:
        logger.warning("Orchestrator failed (%s); using deterministic assembly.", exc)
        orchestrated = ""

    final_document = enforce_contract(
        orchestrated, summary_fallback=summary, email_fallback=email
    )
    return MeetingNotes(
        executive_summary=summary, draft_email=email, final_document=final_document
    )


def generate_meeting_notes(transcript: str, cfg: AppConfig | None = None) -> MeetingNotes:
    """Synchronous entry point. Validates input, runs the async pipeline."""

    if not transcript or not transcript.strip():
        raise PipelineError("Transcript is empty.")
    cfg = cfg or load_config()
    return asyncio.run(_run_async(transcript, cfg))

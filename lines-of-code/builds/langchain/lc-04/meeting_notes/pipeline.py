"""Pipeline assembly + invocation.

Graph (LCEL):

    {transcript}
        |
        v
    RunnableParallel(                # <-- the two sub-agents run CONCURRENTLY
        summary = summarizer(gpt-4.1),
        email   = emailer(gpt-4.1-mini),
    )
        |  -> {summary, email}
        v
    RunnableParallel(                # keep raw outputs alongside the LLM assembly
        final   = orchestrator(gpt-4.1),   # uses {summary, email}
        summary = passthrough,
        email   = passthrough,
    )
        |  -> {final, summary, email}
        v
    RunnableLambda(finalize)         # validate vs. contract; deterministic repair
        |
        v
    contract-compliant document (str)
"""
from __future__ import annotations

import logging

from langchain_core.runnables import (
    Runnable,
    RunnableLambda,
    RunnableParallel,
    RunnablePassthrough,
)
from langchain_core.runnables.utils import Input

from .agents import build_emailer, build_orchestrator, build_summarizer
from .config import AppConfig
from .formatting import assemble_deterministic, strip_fences, validate_contract
from .observability import TracingCallbackHandler, enable_langsmith_tracing

logger = logging.getLogger("meeting_notes.pipeline")


class PipelineError(RuntimeError):
    """Raised when the pipeline cannot produce any valid output."""


def _finalize(payload: dict) -> str:
    """Validate the orchestrator's document; fall back to deterministic assembly.

    This is the contract-enforcement gate: even if the orchestrator LLM drifts,
    we still emit a valid two-section document built from the sub-agent outputs.
    """
    summary = (payload.get("summary") or "").strip()
    email = (payload.get("email") or "").strip()
    final = strip_fences(payload.get("final") or "")

    problems = validate_contract(final)
    if not problems:
        return final.strip() + "\n"

    logger.warning(
        "Orchestrator output failed contract checks (%s); "
        "falling back to deterministic assembly.",
        "; ".join(problems),
    )
    repaired = assemble_deterministic(summary, email)
    residual = validate_contract(repaired)
    if residual:
        # Both the LLM and the deterministic assembly are invalid -> the
        # sub-agents themselves produced unusable content. Fail loudly.
        raise PipelineError(
            "Unable to produce a contract-compliant document. "
            f"Remaining issues: {'; '.join(residual)}"
        )
    return repaired


def build_pipeline(cfg: AppConfig) -> Runnable[Input, str]:
    """Assemble the full orchestrator pipeline as a single Runnable."""
    summarizer = build_summarizer(cfg)
    emailer = build_emailer(cfg)
    orchestrator = build_orchestrator(cfg)

    # Stage 1: fan out to both specialists in parallel. RunnableParallel runs
    # each branch concurrently and passes the same {transcript} input to both.
    fan_out = RunnableParallel(summary=summarizer, email=emailer)

    # Stage 2: orchestrator assembles, while we retain the raw sub-agent outputs
    # for the deterministic fallback in _finalize.
    assemble = RunnableParallel(
        final=orchestrator,
        summary=RunnablePassthrough() | (lambda d: d["summary"]),
        email=RunnablePassthrough() | (lambda d: d["email"]),
    )

    pipeline = (
        fan_out
        | assemble
        | RunnableLambda(_finalize).with_config(run_name="finalize_contract")
    )
    return pipeline.with_config(run_name="meeting_notes_pipeline")


def run_pipeline(cfg: AppConfig, transcript: str) -> str:
    """Run the pipeline against a transcript and return the final document.

    Attaches the tracing callback (and LangSmith, if configured) and caps
    parallel branch concurrency at 2 (the two sub-agents).
    """
    transcript = (transcript or "").strip()
    if not transcript:
        raise PipelineError("Transcript is empty -- nothing to summarize.")

    enable_langsmith_tracing()
    pipeline = build_pipeline(cfg)

    config = {
        "callbacks": [TracingCallbackHandler()],
        "max_concurrency": 2,
        "run_name": "meeting_notes_pipeline",
    }
    logger.info("Invoking pipeline (transcript: %d chars).", len(transcript))
    result = pipeline.invoke({"transcript": transcript}, config=config)
    logger.info("Pipeline complete (%d chars produced).", len(result))
    return result

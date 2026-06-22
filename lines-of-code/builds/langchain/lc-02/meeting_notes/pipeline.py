"""Orchestration pipeline.

Builds the LangChain runnable graph:

    {"transcript"}
        │
        ├─ RunnableParallel ─────────────────────────────────────────────┐
        │     summary  = SUMMARY_PROMPT  | gpt-4.1      | StrOutputParser │  (parallel)
        │     email    = EMAIL_PROMPT    | gpt-4.1-mini | StrOutputParser │
        │     transcript = passthrough                                    │
        │                                                                 ▼
        ├─ ORCHESTRATOR_PROMPT | gpt-4.1.with_structured_output(FinalNotes)
        │
        └─ render_contract  ->  exact "## Executive Summary ... ## Draft Follow-up Email ..."

Each sub-agent chain carries chain-level retry (tenacity, exponential jitter)
on top of the SDK-level retry baked into the model client. The two sub-agents
run concurrently inside ``RunnableParallel`` (threadpool on sync ``.invoke``).
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import (
    Runnable,
    RunnableLambda,
    RunnableParallel,
)

from .config import Settings
from .models import build_chat_model
from .observability import TracingCallbackHandler, configure_logging
from .prompts import EMAIL_PROMPT, ORCHESTRATOR_PROMPT, SUMMARY_PROMPT
from .schemas import FinalNotes


class PipelineError(RuntimeError):
    """Raised when the pipeline fails terminally (after retries)."""


def _with_retry(chain: Runnable, settings: Settings, run_name: str, tags: list[str]) -> Runnable:
    """Attach chain-level retry + a run-name/tags for tracing."""
    return chain.with_retry(
        retry_if_exception_type=(Exception,),
        wait_exponential_jitter=True,
        stop_after_attempt=settings.chain_max_attempts,
    ).with_config(run_name=run_name, tags=tags)


def render_contract(notes: FinalNotes) -> str:
    """Deterministically render the strict output contract.

    The headers are owned here - NOT by any LLM - so the stop condition is
    guaranteed regardless of model whitespace behaviour.
    """
    return (
        "## Executive Summary\n\n"
        f"{notes.executive_summary.strip()}\n\n"
        "## Draft Follow-up Email\n\n"
        f"{notes.follow_up_email.strip()}\n"
    )


def build_pipeline(settings: Settings, handler: Optional[TracingCallbackHandler] = None) -> Runnable:
    """Assemble and return the full runnable pipeline."""
    # --- model clients (per-call timeout + SDK retry applied in factory) --- #
    summary_llm = build_chat_model(settings.summary_model, settings)
    email_llm = build_chat_model(settings.email_model, settings)
    orchestrator_llm = build_chat_model(settings.orchestrator_model, settings)

    # --- sub-agent chains (templated prompt | llm | parser) + retry -------- #
    summary_chain = _with_retry(
        SUMMARY_PROMPT | summary_llm | StrOutputParser(),
        settings,
        run_name="summary_subagent",
        tags=["subagent", "summary", settings.summary_model],
    )
    email_chain = _with_retry(
        EMAIL_PROMPT | email_llm | StrOutputParser(),
        settings,
        run_name="email_subagent",
        tags=["subagent", "email", settings.email_model],
    )

    # --- parallel fan-out: both sub-agents run concurrently ---------------- #
    fan_out = RunnableParallel(
        summary=summary_chain,
        email=email_chain,
        transcript=RunnableLambda(lambda x: x["transcript"]),
    ).with_config(run_name="parallel_subagents", tags=["fan-out"])

    # --- orchestrator reconciliation pass (structured output) -------------- #
    orchestrator_chain = _with_retry(
        ORCHESTRATOR_PROMPT | orchestrator_llm.with_structured_output(FinalNotes),
        settings,
        run_name="orchestrator",
        tags=["orchestrator", settings.orchestrator_model],
    )

    # --- deterministic contract renderer ----------------------------------- #
    render = RunnableLambda(render_contract).with_config(run_name="render_contract")

    pipeline = (fan_out | orchestrator_chain | render).with_config(
        run_name="meeting_notes_pipeline"
    )
    return pipeline


def validate_contract(output: str, settings: Settings, logger: logging.Logger) -> None:
    """Soft-validate the rendered output against the contract.

    Logs warnings rather than failing: the format is guaranteed by the renderer,
    but word-limit overruns by the model are worth surfacing in observability.
    """
    if "## Executive Summary" not in output or "## Draft Follow-up Email" not in output:
        logger.error("Contract violation: required section header missing.")
        return

    try:
        summary_part = output.split("## Executive Summary", 1)[1].split(
            "## Draft Follow-up Email", 1
        )[0]
        email_part = output.split("## Draft Follow-up Email", 1)[1]
    except IndexError:  # pragma: no cover - guarded by the check above
        logger.error("Contract violation: could not split sections.")
        return

    summary_words = len(re.findall(r"\S+", summary_part))
    email_words = len(re.findall(r"\S+", email_part))

    if summary_words > settings.summary_word_limit:
        logger.warning(
            "Executive summary is %d words (limit %d).",
            summary_words,
            settings.summary_word_limit,
        )
    if email_words > settings.email_word_limit:
        logger.warning(
            "Follow-up email is %d words (limit %d).",
            email_words,
            settings.email_word_limit,
        )
    logger.info(
        "Contract OK | summary=%dw email=%dw", summary_words, email_words
    )


def run_meeting_notes(
    transcript: str,
    settings: Optional[Settings] = None,
) -> str:
    """End-to-end entry point: transcript in, contract-formatted notes out.

    Raises:
        PipelineError: if the pipeline fails after all retries.
    """
    if not transcript or not transcript.strip():
        raise PipelineError("Transcript is empty.")

    settings = settings or Settings.from_env()
    logger = configure_logging(settings.log_level)
    handler = TracingCallbackHandler(logger)

    pipeline = build_pipeline(settings, handler)

    logger.info(
        "Starting pipeline | orchestrator=%s summary=%s email=%s | timeout=%.0fs",
        settings.orchestrator_model,
        settings.summary_model,
        settings.email_model,
        settings.request_timeout,
    )

    config: Dict[str, Any] = {
        "callbacks": [handler],
        "run_name": "meeting_notes_request",
        "metadata": {"component": "meeting_notes"},
    }

    try:
        result: str = pipeline.invoke({"transcript": transcript}, config=config)
    except Exception as exc:  # terminal failure after retries
        logger.exception("Pipeline failed terminally.")
        raise PipelineError(f"Meeting-notes pipeline failed: {exc}") from exc

    validate_contract(result, settings, logger)
    logger.info("Pipeline complete.")
    return result

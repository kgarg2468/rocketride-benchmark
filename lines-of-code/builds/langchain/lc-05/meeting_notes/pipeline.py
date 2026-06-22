"""High-level entry points: build the graph and run it against a transcript."""
from __future__ import annotations

import logging

from langchain_core.runnables import Runnable, RunnableConfig

from .chains import build_orchestration_graph
from .config import AppConfig, load_config
from .errors import PipelineError
from .tracing import ConsoleTracer, setup_logging
from .validation import validate_document

logger = logging.getLogger("meeting_notes")


def build_pipeline(config: AppConfig | None = None) -> Runnable:
    """Construct the orchestration graph. Loads config from env if not given."""
    config = config or load_config()
    setup_logging(config.log_level)
    return build_orchestration_graph(config)


def run_pipeline(
    transcript: str,
    attendees: str = "",
    *,
    config: AppConfig | None = None,
    pipeline: Runnable | None = None,
) -> str:
    """Run the system end-to-end and return the validated document.

    Args:
        transcript: the raw meeting transcript.
        attendees:  optional comma-separated attendee names (the email agent will
                    otherwise infer them from the transcript).
        config:     optional pre-loaded config.
        pipeline:   optional pre-built graph (avoids rebuilding across calls).

    Returns:
        The final formatted document (validated against the contract).

    Raises:
        PipelineError: on any failure during graph execution.
        ValidationError: if the output violates the structural contract.
    """
    if not transcript or not transcript.strip():
        raise PipelineError("Transcript is empty.")

    config = config or load_config()
    setup_logging(config.log_level)
    pipeline = pipeline or build_orchestration_graph(config)

    # Attach the console tracer so every LLM call is observable at runtime.
    run_config: RunnableConfig = {"callbacks": [ConsoleTracer()]}

    logger.info("Starting meeting-notes pipeline (transcript: %d chars).", len(transcript))
    try:
        document = pipeline.invoke(
            {"transcript": transcript, "attendees": attendees},
            config=run_config,
        )
    except Exception as exc:  # noqa: BLE001 - normalize into a typed error
        logger.exception("Pipeline execution failed.")
        raise PipelineError(f"Pipeline execution failed: {exc}") from exc

    document = document.strip()

    # Deterministic contract enforcement. Structural failures raise;
    # soft constraint breaches are logged as warnings but do not abort.
    result = validate_document(document)
    for warning in result.warnings:
        logger.warning("Contract warning: %s", warning)

    logger.info("Pipeline complete. Document validated.")
    return document

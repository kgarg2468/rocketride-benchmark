"""Runtime tracing / observability.

Two layers:

1. ``TracingCallbackHandler`` -- a lightweight ``BaseCallbackHandler`` that logs
   the lifecycle of every chain and LLM call (start, latency, token usage,
   errors) through the standard ``logging`` module. Attached to the pipeline at
   invocation time, so it captures the parallel sub-agents too.
2. Optional LangSmith tracing -- enabled automatically when ``LANGSMITH_API_KEY``
   is present, giving full distributed traces in the LangSmith UI.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any
from uuid import UUID

from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.outputs import LLMResult

logger = logging.getLogger("meeting_notes.trace")


class TracingCallbackHandler(BaseCallbackHandler):
    """Logs timings and token usage for chains and LLM calls.

    State is keyed by ``run_id`` so concurrent (parallel) runs don't clobber
    each other's start times.
    """

    def __init__(self) -> None:
        self._llm_starts: dict[UUID, float] = {}
        self._chain_starts: dict[UUID, float] = {}

    # --- LLM lifecycle ---------------------------------------------------- #
    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        self._llm_starts[run_id] = time.monotonic()
        model = self._extract_model(serialized, kwargs)
        logger.info("LLM start    | model=%s | run=%s", model, _short(run_id))

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: Any,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        # Chat models emit this instead of on_llm_start.
        self._llm_starts[run_id] = time.monotonic()
        model = self._extract_model(serialized, kwargs)
        logger.info("LLM start    | model=%s | run=%s", model, _short(run_id))

    def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs: Any) -> None:
        elapsed = self._elapsed(self._llm_starts, run_id)
        tokens = self._extract_tokens(response)
        logger.info(
            "LLM end      | %.2fs | tokens=%s | run=%s",
            elapsed,
            tokens,
            _short(run_id),
        )

    def on_llm_error(
        self, error: BaseException, *, run_id: UUID, **kwargs: Any
    ) -> None:
        elapsed = self._elapsed(self._llm_starts, run_id)
        logger.warning(
            "LLM ERROR    | %.2fs | %s: %s | run=%s",
            elapsed,
            type(error).__name__,
            error,
            _short(run_id),
        )

    # --- Chain lifecycle -------------------------------------------------- #
    def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: Any,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        self._chain_starts[run_id] = time.monotonic()
        name = self._extract_name(serialized, kwargs)
        if name:
            logger.debug("chain start  | %s | run=%s", name, _short(run_id))

    def on_chain_end(self, outputs: Any, *, run_id: UUID, **kwargs: Any) -> None:
        elapsed = self._elapsed(self._chain_starts, run_id)
        name = kwargs.get("name")
        if name:
            logger.debug("chain end    | %s | %.2fs | run=%s", name, elapsed, _short(run_id))

    def on_chain_error(
        self, error: BaseException, *, run_id: UUID, **kwargs: Any
    ) -> None:
        elapsed = self._elapsed(self._chain_starts, run_id)
        logger.warning(
            "chain ERROR  | %.2fs | %s: %s | run=%s",
            elapsed,
            type(error).__name__,
            error,
            _short(run_id),
        )

    # --- helpers ---------------------------------------------------------- #
    @staticmethod
    def _elapsed(store: dict[UUID, float], run_id: UUID) -> float:
        start = store.pop(run_id, None)
        return (time.monotonic() - start) if start is not None else float("nan")

    @staticmethod
    def _extract_model(serialized: dict[str, Any], kwargs: dict[str, Any]) -> str:
        params = kwargs.get("invocation_params") or {}
        model = params.get("model") or params.get("model_name")
        if not model and serialized:
            model = (serialized.get("kwargs") or {}).get("model")
        return model or "unknown"

    @staticmethod
    def _extract_name(serialized: dict[str, Any], kwargs: dict[str, Any]) -> str | None:
        return kwargs.get("name") or (serialized or {}).get("name")

    @staticmethod
    def _extract_tokens(response: LLMResult) -> str:
        # Prefer aggregated llm_output usage; fall back to per-generation metadata.
        usage = (response.llm_output or {}).get("token_usage") if response.llm_output else None
        if not usage:
            try:
                gen = response.generations[0][0]
                usage = getattr(gen.message, "usage_metadata", None)  # type: ignore[attr-defined]
            except (IndexError, AttributeError):
                usage = None
        if not usage:
            return "n/a"
        total = usage.get("total_tokens") or usage.get("total_token_count")
        prompt = usage.get("prompt_tokens") or usage.get("input_tokens")
        completion = usage.get("completion_tokens") or usage.get("output_tokens")
        return f"total={total} prompt={prompt} completion={completion}"


def _short(run_id: UUID) -> str:
    return str(run_id)[:8]


def configure_logging(level: str = "INFO") -> None:
    """Configure root logging once, idempotently."""
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def enable_langsmith_tracing(project: str | None = None) -> bool:
    """Turn on LangSmith tracing if an API key is configured.

    Returns ``True`` if tracing was enabled. LangChain reads these env vars
    natively, so we just set them and let the runtime export traces.
    """
    if not os.environ.get("LANGSMITH_API_KEY", "").strip():
        return False
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault(
        "LANGCHAIN_PROJECT", project or os.environ.get("LANGSMITH_PROJECT", "meeting-notes")
    )
    # Mirror the v2 key names some versions still read.
    os.environ.setdefault("LANGCHAIN_API_KEY", os.environ["LANGSMITH_API_KEY"])
    logger.info("LangSmith tracing enabled (project=%s)", os.environ["LANGCHAIN_PROJECT"])
    return True

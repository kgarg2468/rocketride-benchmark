"""Runtime tracing / observability.

Two complementary mechanisms:

1. :class:`TracingCallbackHandler` — a LangChain ``BaseCallbackHandler`` that
   emits structured, timed log lines for every chain and LLM invocation,
   including token usage when the provider reports it. This works with no
   external service and is always on.

2. LangSmith — if ``LANGCHAIN_TRACING_V2=true`` and ``LANGCHAIN_API_KEY`` are
   set, LangChain automatically exports full traces to LangSmith. We only need
   to surface that it is active.
"""

from __future__ import annotations

import logging
import time
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from .config import AppConfig

logger = logging.getLogger("meeting_notes")


def setup_logging(config: AppConfig) -> None:
    """Configure the package logger once, idempotently."""

    level = getattr(logging, config.log_level, logging.INFO)
    root = logging.getLogger("meeting_notes")
    root.setLevel(level)
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        root.addHandler(handler)
    root.propagate = False

    if config.langsmith_enabled:
        logger.info(
            "LangSmith tracing ENABLED (project=%s). Full traces will be "
            "exported to LangSmith.",
            config.langsmith_project,
        )
    else:
        logger.debug(
            "LangSmith tracing disabled (set LANGCHAIN_TRACING_V2=true and "
            "LANGCHAIN_API_KEY to enable). Local callback tracing is active."
        )


class TracingCallbackHandler(BaseCallbackHandler):
    """Logs lifecycle + timing + token usage for chains and LLM calls.

    Timings are keyed by the run UUID that LangChain assigns to every node, so
    overlapping (parallel) runs are tracked independently.
    """

    def __init__(self, logger_: logging.Logger | None = None) -> None:
        self._log = logger_ or logger
        self._starts: dict[UUID, float] = {}

    # ----- chains -------------------------------------------------------
    def on_chain_start(
        self,
        serialized: dict[str, Any] | None,
        inputs: dict[str, Any],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        self._starts[run_id] = time.perf_counter()
        name = (serialized or {}).get("name") or kwargs.get("name") or "chain"
        self._log.debug("→ chain start: %s", name)

    def on_chain_end(
        self, outputs: dict[str, Any], *, run_id: UUID, **kwargs: Any
    ) -> None:
        elapsed = self._elapsed(run_id)
        self._log.debug("← chain end (%.2fs)", elapsed)

    def on_chain_error(
        self, error: BaseException, *, run_id: UUID, **kwargs: Any
    ) -> None:
        elapsed = self._elapsed(run_id)
        self._log.error("✗ chain error after %.2fs: %s", elapsed, error)

    # ----- LLMs ---------------------------------------------------------
    def on_llm_start(
        self,
        serialized: dict[str, Any] | None,
        prompts: list[str],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        self._starts[run_id] = time.perf_counter()
        model = self._model_name(serialized, kwargs)
        self._log.info("→ LLM call start: model=%s", model)

    def on_chat_model_start(
        self,
        serialized: dict[str, Any] | None,
        messages: list[list[Any]],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        self._starts[run_id] = time.perf_counter()
        model = self._model_name(serialized, kwargs)
        self._log.info("→ chat model start: model=%s", model)

    def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs: Any) -> None:
        elapsed = self._elapsed(run_id)
        usage = self._token_usage(response)
        if usage:
            self._log.info(
                "← LLM call end (%.2fs) tokens: prompt=%s completion=%s total=%s",
                elapsed,
                usage.get("prompt_tokens", "?"),
                usage.get("completion_tokens", "?"),
                usage.get("total_tokens", "?"),
            )
        else:
            self._log.info("← LLM call end (%.2fs)", elapsed)

    def on_llm_error(
        self, error: BaseException, *, run_id: UUID, **kwargs: Any
    ) -> None:
        elapsed = self._elapsed(run_id)
        self._log.warning(
            "✗ LLM error after %.2fs (will retry if attempts remain): %s",
            elapsed,
            error,
        )

    # ----- helpers ------------------------------------------------------
    def _elapsed(self, run_id: UUID) -> float:
        start = self._starts.pop(run_id, None)
        return (time.perf_counter() - start) if start is not None else 0.0

    @staticmethod
    def _model_name(serialized: dict[str, Any] | None, kwargs: dict[str, Any]) -> str:
        invocation = kwargs.get("invocation_params") or {}
        if invocation.get("model"):
            return str(invocation["model"])
        if serialized:
            kw = serialized.get("kwargs") or {}
            if kw.get("model"):
                return str(kw["model"])
            if serialized.get("name"):
                return str(serialized["name"])
        return "unknown"

    @staticmethod
    def _token_usage(response: LLMResult) -> dict[str, Any] | None:
        output = response.llm_output or {}
        usage = output.get("token_usage") or output.get("usage")
        if usage:
            return dict(usage)
        # Newer langchain surfaces usage on the generation message metadata.
        try:
            gen = response.generations[0][0]
            meta = getattr(gen, "message", None)
            if meta is not None and getattr(meta, "usage_metadata", None):
                um = meta.usage_metadata
                return {
                    "prompt_tokens": um.get("input_tokens"),
                    "completion_tokens": um.get("output_tokens"),
                    "total_tokens": um.get("total_tokens"),
                }
        except (IndexError, AttributeError):
            pass
        return None

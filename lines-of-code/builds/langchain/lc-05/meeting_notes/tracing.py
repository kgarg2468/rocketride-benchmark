"""Runtime tracing / observability.

Provides:
  * ``setup_logging`` - configures the root logger once.
  * ``ConsoleTracer`` - a LangChain callback handler that records per-call
    latency, token usage and errors for every LLM invocation in the graph.

If ``LANGCHAIN_TRACING_V2=true`` is set in the environment, LangChain *also*
exports full traces to LangSmith automatically; this console tracer is the
zero-dependency baseline that always runs.
"""
from __future__ import annotations

import logging
import time
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

logger = logging.getLogger("meeting_notes")


def setup_logging(level: str = "INFO") -> None:
    """Configure console logging exactly once (idempotent)."""
    root = logging.getLogger("meeting_notes")
    if root.handlers:
        root.setLevel(level)
        return
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    root.addHandler(handler)
    root.setLevel(level)
    root.propagate = False


class ConsoleTracer(BaseCallbackHandler):
    """Logs the lifecycle, latency and token cost of every LLM call.

    Keyed by ``run_id`` so concurrently-executing sub-agents are tracked
    independently and never clobber each other's timers.
    """

    def __init__(self) -> None:
        self._start_times: dict[UUID, float] = {}

    # -- LLM lifecycle ------------------------------------------------------
    # Chat models (ChatOpenAI) trigger on_chat_model_start; completion-style
    # models trigger on_llm_start. We handle both so the timer always starts.
    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        self._on_start(run_id, kwargs)

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        self._on_start(run_id, kwargs)

    def _on_start(self, run_id: UUID, kwargs: dict[str, Any]) -> None:
        self._start_times[run_id] = time.perf_counter()
        label = self._label(kwargs)
        model = (kwargs.get("invocation_params") or {}).get("model", "?")
        logger.info("LLM start   | %-22s | model=%s", label, model)

    def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs: Any) -> None:
        elapsed = self._elapsed(run_id)
        label = self._label(kwargs)
        usage = self._token_usage(response)
        logger.info(
            "LLM end     | %-22s | %.2fs | tokens(prompt=%s, completion=%s, total=%s)",
            label,
            elapsed,
            usage.get("prompt_tokens", "?"),
            usage.get("completion_tokens", "?"),
            usage.get("total_tokens", "?"),
        )

    def on_llm_error(
        self, error: BaseException, *, run_id: UUID, **kwargs: Any
    ) -> None:
        elapsed = self._elapsed(run_id)
        label = self._label(kwargs)
        logger.error(
            "LLM ERROR   | %-22s | %.2fs | %s: %s",
            label,
            elapsed,
            type(error).__name__,
            error,
        )

    # -- helpers ------------------------------------------------------------
    def _label(self, kwargs: dict[str, Any]) -> str:
        meta = kwargs.get("metadata") or {}
        tags = kwargs.get("tags") or []
        return meta.get("agent") or (tags[0] if tags else "llm")

    def _elapsed(self, run_id: UUID) -> float:
        start = self._start_times.pop(run_id, None)
        return (time.perf_counter() - start) if start is not None else float("nan")

    @staticmethod
    def _token_usage(response: LLMResult) -> dict[str, Any]:
        output = response.llm_output or {}
        return output.get("token_usage") or output.get("usage") or {}

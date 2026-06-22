"""Runtime tracing & logging.

Observability has two layers:

1. ``configure_logging`` — structured, level-controlled stdlib logging.
2. ``TracingCallbackHandler`` — a LangChain callback that records every model
   invocation: which agent ran, latency, and token usage. Attached once at the
   top of the run so *all* nested runnables inherit it.

If ``LANGCHAIN_TRACING_V2=true`` and a ``LANGCHAIN_API_KEY`` are present,
LangChain additionally streams traces to LangSmith automatically — this handler
is complementary and needs no external service.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

logger = logging.getLogger("meeting_notes")


def configure_logging(level: str | None = None) -> None:
    """Configure root logging once. Level via arg or ``LOG_LEVEL`` env."""

    resolved = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    logging.basicConfig(
        level=getattr(logging, resolved, logging.INFO),
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


class TracingCallbackHandler(BaseCallbackHandler):
    """Lightweight per-run tracer for chat-model calls.

    Tracks wall-clock latency per ``run_id`` and logs token usage on completion.
    Errors are logged with the owning agent's tags for fast diagnosis.
    """

    def __init__(self) -> None:
        self._starts: dict[UUID, float] = {}
        self._labels: dict[UUID, str] = {}

    @staticmethod
    def _label(tags: list[str] | None, serialized: dict[str, Any] | None) -> str:
        if tags:
            return ",".join(tags)
        if serialized:
            return serialized.get("name", "chat-model")
        return "chat-model"

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id: UUID,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        self._starts[run_id] = time.monotonic()
        self._labels[run_id] = self._label(tags, serialized)
        logger.info("[trace] start    %-28s run=%s", self._labels[run_id], run_id)

    def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs: Any) -> None:
        started = self._starts.pop(run_id, None)
        label = self._labels.pop(run_id, "chat-model")
        elapsed = (time.monotonic() - started) if started is not None else float("nan")

        usage: dict[str, Any] = {}
        if response.llm_output:
            usage = response.llm_output.get("token_usage") or {}
        # Fallback for providers that attach usage to generation metadata.
        if not usage and response.generations:
            meta = getattr(response.generations[0][0], "message", None)
            usage = getattr(meta, "usage_metadata", None) or {}

        logger.info(
            "[trace] complete %-28s %6.2fs tokens(prompt=%s completion=%s total=%s)",
            label,
            elapsed,
            usage.get("prompt_tokens", usage.get("input_tokens", "?")),
            usage.get("completion_tokens", usage.get("output_tokens", "?")),
            usage.get("total_tokens", "?"),
        )

    def on_llm_error(
        self, error: BaseException, *, run_id: UUID, **kwargs: Any
    ) -> None:
        label = self._labels.pop(run_id, "chat-model")
        self._starts.pop(run_id, None)
        logger.warning("[trace] error    %-28s %s: %s", label, type(error).__name__, error)

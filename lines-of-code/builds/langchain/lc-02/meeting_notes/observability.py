"""Runtime tracing and observability.

Two layers:

1. ``configure_logging`` - structured stderr logging for the whole package.
2. ``TracingCallbackHandler`` - a LangChain callback handler that records the
   latency and token usage of every individual LLM call and every chain step,
   tagged with the runnable's run-name so you can see exactly which sub-agent
   did what.

If the standard LangSmith environment variables are present
(``LANGCHAIN_TRACING_V2=true`` and ``LANGCHAIN_API_KEY``), LangChain will also
export full traces to LangSmith automatically - no code change required.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict
from uuid import UUID

from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.outputs import LLMResult

LOGGER_NAME = "meeting_notes"


def configure_logging(level: str = "INFO") -> logging.Logger:
    """Configure and return the package logger (idempotent)."""
    logger = logging.getLogger(LOGGER_NAME)
    if not logger.handlers:
        handler = logging.StreamHandler()  # stderr
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        logger.addHandler(handler)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False
    return logger


class TracingCallbackHandler(BaseCallbackHandler):
    """Logs per-call latency and token usage for LLM and chain runs."""

    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger
        self._llm_starts: Dict[UUID, float] = {}
        self._chain_starts: Dict[UUID, float] = {}

    # ----------------------------- LLM events ---------------------------- #
    def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: list,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        self._llm_starts[run_id] = time.perf_counter()
        model = self._model_name(serialized, kwargs)
        self._logger.info("LLM start    | model=%s | run=%s", model, run_id)

    def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs: Any) -> None:
        elapsed = self._elapsed(self._llm_starts.pop(run_id, None))
        usage = self._token_usage(response)
        self._logger.info(
            "LLM end      | %.2fs | tokens(prompt=%s, completion=%s, total=%s) | run=%s",
            elapsed,
            usage.get("prompt_tokens", "?"),
            usage.get("completion_tokens", "?"),
            usage.get("total_tokens", "?"),
            run_id,
        )

    def on_llm_error(
        self, error: BaseException, *, run_id: UUID, **kwargs: Any
    ) -> None:
        elapsed = self._elapsed(self._llm_starts.pop(run_id, None))
        self._logger.warning(
            "LLM error    | %.2fs | %s: %s | run=%s (retry/fallback may apply)",
            elapsed,
            type(error).__name__,
            error,
            run_id,
        )

    # ---------------------------- Chain events --------------------------- #
    def on_chain_start(
        self,
        serialized: Dict[str, Any],
        inputs: Any,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        name = kwargs.get("name") or (serialized or {}).get("name") or "chain"
        self._chain_starts[run_id] = time.perf_counter()
        self._logger.debug("Chain start  | %s | run=%s", name, run_id)

    def on_chain_end(self, outputs: Any, *, run_id: UUID, **kwargs: Any) -> None:
        elapsed = self._elapsed(self._chain_starts.pop(run_id, None))
        self._logger.debug("Chain end    | %.2fs | run=%s", elapsed, run_id)

    def on_chain_error(
        self, error: BaseException, *, run_id: UUID, **kwargs: Any
    ) -> None:
        elapsed = self._elapsed(self._chain_starts.pop(run_id, None))
        self._logger.warning(
            "Chain error  | %.2fs | %s: %s | run=%s",
            elapsed,
            type(error).__name__,
            error,
            run_id,
        )

    # ------------------------------ helpers ------------------------------ #
    @staticmethod
    def _elapsed(start: float | None) -> float:
        return (time.perf_counter() - start) if start is not None else float("nan")

    @staticmethod
    def _model_name(serialized: Dict[str, Any], kwargs: Dict[str, Any]) -> str:
        meta = kwargs.get("metadata") or {}
        if meta.get("ls_model_name"):
            return meta["ls_model_name"]
        invocation = (serialized or {}).get("kwargs", {}) if serialized else {}
        return invocation.get("model") or invocation.get("model_name") or "llm"

    @staticmethod
    def _token_usage(response: LLMResult) -> Dict[str, Any]:
        # langchain-openai surfaces usage in llm_output; fall back to
        # per-generation usage_metadata if needed.
        if response.llm_output and "token_usage" in response.llm_output:
            return dict(response.llm_output["token_usage"])
        for gen_list in response.generations:
            for gen in gen_list:
                msg = getattr(gen, "message", None)
                usage = getattr(msg, "usage_metadata", None)
                if usage:
                    return {
                        "prompt_tokens": usage.get("input_tokens"),
                        "completion_tokens": usage.get("output_tokens"),
                        "total_tokens": usage.get("total_tokens"),
                    }
        return {}

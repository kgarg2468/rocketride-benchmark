"""Model factory.

Centralizes construction of :class:`ChatOpenAI` instances so every model in the
system gets consistent, production-grade settings:

  * ``timeout``     - a per-call wall-clock budget (one of the quality-bar items).
  * ``max_retries`` - client-level retries for transient OpenAI API errors
    (rate limits, 5xx, connection resets) with exponential backoff handled by
    the OpenAI SDK. This is layered *under* the Runnable-level ``.with_retry``
    applied in chains.py for defence in depth.
"""
from __future__ import annotations

from langchain_openai import ChatOpenAI

from .config import ModelConfig


def build_chat_model(cfg: ModelConfig, api_key: str) -> ChatOpenAI:
    """Create a configured :class:`ChatOpenAI` for one role."""
    return ChatOpenAI(
        model=cfg.name,
        temperature=cfg.temperature,
        timeout=cfg.timeout,         # per-call timeout (seconds)
        max_retries=cfg.max_retries, # transient-error retries at the API client
        api_key=api_key,
    )

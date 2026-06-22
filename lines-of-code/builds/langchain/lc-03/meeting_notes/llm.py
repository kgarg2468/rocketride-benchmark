"""ChatOpenAI factory.

Centralises construction of model clients so retry, timeout, and API-key
wiring are applied identically everywhere. Per-call timeout and SDK-level
retries are configured here; chain-level retry is added in :mod:`agents`.
"""

from __future__ import annotations

from langchain_openai import ChatOpenAI

from .config import AppConfig, ModelConfig


def build_chat_model(model_config: ModelConfig, app_config: AppConfig) -> ChatOpenAI:
    """Construct a configured :class:`ChatOpenAI` client.

    * ``timeout``     — per-call wall-clock limit enforced by the OpenAI client.
    * ``max_retries`` — SDK-level automatic retries for transient failures
                        (HTTP 429/5xx, connection errors) with backoff.
    """

    return ChatOpenAI(
        model=model_config.model,
        temperature=model_config.temperature,
        timeout=model_config.timeout,
        max_retries=model_config.max_retries,
        api_key=app_config.openai_api_key,
    )

"""LLM factory.

Centralises construction of ``ChatOpenAI`` clients so that the two
production-critical knobs - **per-call timeout** and **SDK-level retry** - are
applied consistently to every model in the system.
"""

from __future__ import annotations

from langchain_openai import ChatOpenAI

from .config import Settings


def build_chat_model(model: str, settings: Settings) -> ChatOpenAI:
    """Construct a configured ``ChatOpenAI`` client.

    - ``timeout``      -> hard per-request timeout (seconds).
    - ``max_retries``  -> SDK-level retry on transient API errors (429/5xx/
      connection resets) with the OpenAI client's built-in exponential backoff.
    """
    return ChatOpenAI(
        model=model,
        api_key=settings.openai_api_key,
        temperature=settings.temperature,
        timeout=settings.request_timeout,
        max_retries=settings.sdk_max_retries,
    )

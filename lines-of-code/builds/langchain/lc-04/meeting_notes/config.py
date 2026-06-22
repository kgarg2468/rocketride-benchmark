"""Centralized configuration: env loading, model specs, retry/timeout knobs.

Everything tunable lives here so another engineer can change behaviour without
touching the chain logic. Values come from environment variables (a local
``.env`` file is loaded automatically) with production-safe defaults.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Load .env once, at import time. Real environment variables take precedence.
load_dotenv(override=False)


class ConfigError(RuntimeError):
    """Raised when required configuration (e.g. the API key) is missing."""


@dataclass(frozen=True)
class ModelConfig:
    """Per-model settings. ``timeout`` and ``max_retries`` are passed straight
    through to ``ChatOpenAI`` (per-call timeout + SDK-level retry)."""

    model: str
    temperature: float
    timeout: float
    max_retries: int


@dataclass(frozen=True)
class AppConfig:
    """Top-level application configuration."""

    openai_api_key: str
    orchestrator: ModelConfig
    summarizer: ModelConfig
    emailer: ModelConfig
    # Runnable-level retry (wraps an entire sub-chain, on top of SDK retries).
    chain_max_attempts: int
    chain_retry_wait: float
    log_level: str
    langsmith_enabled: bool


def _get_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:  # pragma: no cover - defensive
        raise ConfigError(f"Environment variable {name}={raw!r} is not a number.") from exc


def _get_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:  # pragma: no cover - defensive
        raise ConfigError(f"Environment variable {name}={raw!r} is not an integer.") from exc


def load_config() -> AppConfig:
    """Build an :class:`AppConfig` from the environment.

    Raises :class:`ConfigError` if ``OPENAI_API_KEY`` is absent.
    """
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ConfigError(
            "OPENAI_API_KEY is not set. Export it or add it to a .env file "
            "(see .env.example)."
        )

    timeout = _get_float("LLM_TIMEOUT_SECONDS", 60.0)
    max_retries = _get_int("LLM_MAX_RETRIES", 4)

    orchestrator = ModelConfig(
        model=os.environ.get("ORCHESTRATOR_MODEL", "gpt-4.1"),
        temperature=0.0,  # deterministic assembly of the final document
        timeout=timeout,
        max_retries=max_retries,
    )
    summarizer = ModelConfig(
        model=os.environ.get("SUMMARIZER_MODEL", "gpt-4.1"),
        temperature=0.2,
        timeout=timeout,
        max_retries=max_retries,
    )
    emailer = ModelConfig(
        # Smaller/cheaper model for the more constrained drafting task.
        model=os.environ.get("EMAILER_MODEL", "gpt-4.1-mini"),
        temperature=0.3,
        timeout=timeout,
        max_retries=max_retries,
    )

    langsmith_enabled = bool(os.environ.get("LANGSMITH_API_KEY", "").strip())

    return AppConfig(
        openai_api_key=api_key,
        orchestrator=orchestrator,
        summarizer=summarizer,
        emailer=emailer,
        chain_max_attempts=_get_int("CHAIN_MAX_ATTEMPTS", 3),
        chain_retry_wait=_get_float("CHAIN_RETRY_WAIT", 1.5),
        log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        langsmith_enabled=langsmith_enabled,
    )

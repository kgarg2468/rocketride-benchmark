"""Centralised, validated configuration.

All tunables (model names, timeouts, retry counts) are read once from the
environment so the rest of the code never touches ``os.environ`` directly.
This keeps configuration auditable and makes the system testable.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Load a local .env (if present) before anything reads the environment.
load_dotenv()


class ConfigError(RuntimeError):
    """Raised when the runtime is missing required configuration."""


@dataclass(frozen=True)
class ModelConfig:
    """Per-model settings. ``timeout`` and ``max_retries`` are the first line
    of the timeout/retry defences (enforced by the OpenAI client itself)."""

    name: str
    temperature: float
    timeout: float          # seconds: per-request HTTP timeout
    max_retries: int        # OpenAI-client-level retries (network / 429 / 5xx)


@dataclass(frozen=True)
class AppConfig:
    openai_api_key: str
    orchestrator: ModelConfig
    summarizer: ModelConfig
    emailer: ModelConfig
    # Chain-level retry (LCEL ``.with_retry``) — broader than the client retry.
    chain_max_attempts: int
    # Wall-clock ceiling (seconds) applied with ``asyncio.wait_for`` around the
    # parallel sub-agent stage. Acts as a backstop above the per-call timeouts.
    stage_timeout: float


def _env_float(key: str, default: float) -> float:
    raw = os.getenv(key)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:  # pragma: no cover - defensive
        raise ConfigError(f"{key} must be a number, got {raw!r}") from exc


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:  # pragma: no cover - defensive
        raise ConfigError(f"{key} must be an integer, got {raw!r}") from exc


def load_config() -> AppConfig:
    """Build an :class:`AppConfig` from the environment.

    Raises :class:`ConfigError` if ``OPENAI_API_KEY`` is absent so the program
    fails fast with a clear message instead of deep inside an HTTP call.
    """

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ConfigError(
            "OPENAI_API_KEY is not set. Export it or add it to a .env file "
            "(see .env.example)."
        )

    timeout = _env_float("LLM_TIMEOUT_SECONDS", 60.0)
    max_retries = _env_int("LLM_MAX_RETRIES", 3)

    return AppConfig(
        openai_api_key=api_key,
        # Orchestrator and summary writer share the larger model.
        orchestrator=ModelConfig(
            name=os.getenv("MODEL_ORCHESTRATOR", "gpt-4.1"),
            temperature=_env_float("TEMP_ORCHESTRATOR", 0.2),
            timeout=timeout,
            max_retries=max_retries,
        ),
        summarizer=ModelConfig(
            name=os.getenv("MODEL_SUMMARIZER", "gpt-4.1"),
            temperature=_env_float("TEMP_SUMMARIZER", 0.2),
            timeout=timeout,
            max_retries=max_retries,
        ),
        # Email drafting is the more constrained task -> smaller, cheaper model.
        emailer=ModelConfig(
            name=os.getenv("MODEL_EMAILER", "gpt-4.1-mini"),
            temperature=_env_float("TEMP_EMAILER", 0.3),
            timeout=timeout,
            max_retries=max_retries,
        ),
        chain_max_attempts=_env_int("CHAIN_MAX_ATTEMPTS", 3),
        stage_timeout=_env_float("STAGE_TIMEOUT_SECONDS", timeout + 15.0),
    )

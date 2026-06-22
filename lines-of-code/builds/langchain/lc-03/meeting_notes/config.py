"""Centralised, environment-driven configuration.

All tunables (model names, timeouts, retry counts, temperature) live here so an
operator can change behaviour without touching agent logic. Values are read
once from the environment and frozen into dataclasses.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from .exceptions import ConfigurationError

# Optional .env support — never fatal if python-dotenv is absent.
try:  # pragma: no cover - trivial import guard
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover
    pass


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a number, got {raw!r}") from exc


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer, got {raw!r}") from exc


@dataclass(frozen=True)
class ModelConfig:
    """Per-model runtime configuration shared by every ChatOpenAI instance."""

    model: str
    temperature: float = 0.0
    # Per-call wall-clock timeout (seconds) enforced by the OpenAI client.
    timeout: float = 45.0
    # SDK-level automatic retries for transient API errors (429/5xx/network).
    max_retries: int = 3


@dataclass(frozen=True)
class AppConfig:
    """Top-level application configuration."""

    openai_api_key: str
    orchestrator: ModelConfig
    summary_agent: ModelConfig
    email_agent: ModelConfig

    # Chain-level retry (LCEL `.with_retry`) layered on top of SDK retries.
    chain_max_attempts: int = 2

    # Observability
    log_level: str = "INFO"
    langsmith_enabled: bool = False
    langsmith_project: str = "meeting-notes"

    @property
    def models(self) -> dict[str, ModelConfig]:
        return {
            "orchestrator": self.orchestrator,
            "summary_agent": self.summary_agent,
            "email_agent": self.email_agent,
        }


def load_config() -> AppConfig:
    """Build an :class:`AppConfig` from environment variables.

    Raises
    ------
    ConfigurationError
        If ``OPENAI_API_KEY`` is missing.
    """

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ConfigurationError(
            "OPENAI_API_KEY is not set. Export it before running, e.g.\n"
            "    export OPENAI_API_KEY='sk-...'"
        )

    timeout = _env_float("MN_LLM_TIMEOUT", 45.0)
    sdk_retries = _env_int("MN_LLM_MAX_RETRIES", 3)
    temperature = _env_float("MN_LLM_TEMPERATURE", 0.0)

    # gpt-4.1 for the heavier reasoning tasks; gpt-4.1-mini for the more
    # constrained drafting task (cheaper / faster).
    orchestrator = ModelConfig(
        model=os.getenv("MN_ORCHESTRATOR_MODEL", "gpt-4.1"),
        temperature=temperature,
        timeout=timeout,
        max_retries=sdk_retries,
    )
    summary_agent = ModelConfig(
        model=os.getenv("MN_SUMMARY_MODEL", "gpt-4.1"),
        temperature=temperature,
        timeout=timeout,
        max_retries=sdk_retries,
    )
    email_agent = ModelConfig(
        model=os.getenv("MN_EMAIL_MODEL", "gpt-4.1-mini"),
        temperature=temperature,
        timeout=timeout,
        max_retries=sdk_retries,
    )

    # LangSmith tracing auto-enables when the standard env vars are present.
    langsmith_enabled = os.getenv("LANGCHAIN_TRACING_V2", "").lower() == "true" and bool(
        os.getenv("LANGCHAIN_API_KEY")
    )

    return AppConfig(
        openai_api_key=api_key,
        orchestrator=orchestrator,
        summary_agent=summary_agent,
        email_agent=email_agent,
        chain_max_attempts=_env_int("MN_CHAIN_MAX_ATTEMPTS", 2),
        log_level=os.getenv("MN_LOG_LEVEL", "INFO").upper(),
        langsmith_enabled=langsmith_enabled,
        langsmith_project=os.getenv("LANGCHAIN_PROJECT", "meeting-notes"),
    )

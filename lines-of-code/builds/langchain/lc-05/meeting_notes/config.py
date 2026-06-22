"""Runtime configuration.

All knobs are read once, validated, and frozen into immutable dataclasses so the
rest of the package can depend on a single, well-typed source of truth. Values
come from environment variables (a local ``.env`` is loaded automatically).
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from .errors import ConfigError

# Load a local .env (if present) before reading anything. No-op in production
# environments where the variables are already exported.
load_dotenv()


@dataclass(frozen=True)
class ModelConfig:
    """Per-model settings. One instance per LLM role."""

    name: str
    temperature: float
    timeout: float          # per-call wall-clock timeout, seconds
    max_retries: int        # client-level retries for transient API errors


@dataclass(frozen=True)
class AppConfig:
    """Top-level, validated application configuration."""

    openai_api_key: str
    orchestrator: ModelConfig
    summary: ModelConfig
    email: ModelConfig
    log_level: str


def _get_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:  # pragma: no cover - defensive
        raise ConfigError(f"{name} must be a number, got {raw!r}") from exc


def _get_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:  # pragma: no cover - defensive
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc


def load_config() -> AppConfig:
    """Build and validate :class:`AppConfig` from the environment.

    Raises:
        ConfigError: if ``OPENAI_API_KEY`` is absent.
    """
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ConfigError(
            "OPENAI_API_KEY is not set. Export it or add it to a .env file "
            "(see .env.example)."
        )

    timeout = _get_float("MEETING_NOTES_TIMEOUT", 30.0)
    max_retries = _get_int("MEETING_NOTES_MAX_RETRIES", 3)

    orchestrator_model = os.environ.get("MEETING_NOTES_ORCHESTRATOR_MODEL", "gpt-4.1")
    summary_model = os.environ.get("MEETING_NOTES_SUMMARY_MODEL", "gpt-4.1")
    email_model = os.environ.get("MEETING_NOTES_EMAIL_MODEL", "gpt-4.1-mini")

    return AppConfig(
        openai_api_key=api_key,
        # Orchestrator: deterministic assembly/editing -> temperature 0.
        orchestrator=ModelConfig(orchestrator_model, 0.0, timeout, max_retries),
        # Summary: near-deterministic, lightly fluent.
        summary=ModelConfig(summary_model, 0.2, timeout, max_retries),
        # Email: a touch more natural phrasing, still constrained.
        email=ModelConfig(email_model, 0.3, timeout, max_retries),
        log_level=os.environ.get("MEETING_NOTES_LOG_LEVEL", "INFO").upper(),
    )

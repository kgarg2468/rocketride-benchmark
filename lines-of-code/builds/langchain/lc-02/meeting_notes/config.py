"""Runtime configuration.

All tunables live here so model names, timeouts and retry budgets are not
scattered through the codebase. Secrets are read from the environment only;
they are never hard-coded or logged.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

try:
    # Optional convenience: load a local .env file if python-dotenv is present.
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv is optional
    pass


class ConfigError(RuntimeError):
    """Raised when required configuration (e.g. the API key) is missing."""


@dataclass(frozen=True)
class Settings:
    """Immutable runtime settings.

    Build one with :meth:`Settings.from_env`. Every field has a production-sane
    default; only ``OPENAI_API_KEY`` is mandatory.
    """

    openai_api_key: str

    # Model assignment per the architecture.
    orchestrator_model: str = "gpt-4.1"
    summary_model: str = "gpt-4.1"
    email_model: str = "gpt-4.1-mini"

    # Per-call request timeout (seconds) applied to every model call.
    request_timeout: float = 60.0

    # SDK-level retry budget (transient API errors: 429/5xx/connection resets).
    sdk_max_retries: int = 2

    # Chain-level retry budget (timeouts, parse failures, anything the SDK
    # retry does not cover). Applied via tenacity with exponential jitter.
    chain_max_attempts: int = 3

    # Low temperature: this is an extraction/drafting task, not creative writing.
    temperature: float = 0.2

    # Contract guard-rails (soft-validated; logged, not fatal).
    summary_word_limit: int = 100
    email_word_limit: int = 200

    # Logging verbosity.
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise ConfigError(
                "OPENAI_API_KEY is not set. Export it before running, e.g.\n"
                "    export OPENAI_API_KEY='sk-...'"
            )

        def _float(name: str, default: float) -> float:
            raw = os.environ.get(name)
            return float(raw) if raw else default

        def _int(name: str, default: int) -> int:
            raw = os.environ.get(name)
            return int(raw) if raw else default

        return cls(
            openai_api_key=api_key,
            orchestrator_model=os.environ.get("MN_ORCHESTRATOR_MODEL", "gpt-4.1"),
            summary_model=os.environ.get("MN_SUMMARY_MODEL", "gpt-4.1"),
            email_model=os.environ.get("MN_EMAIL_MODEL", "gpt-4.1-mini"),
            request_timeout=_float("MN_REQUEST_TIMEOUT", 60.0),
            sdk_max_retries=_int("MN_SDK_MAX_RETRIES", 2),
            chain_max_attempts=_int("MN_CHAIN_MAX_ATTEMPTS", 3),
            temperature=_float("MN_TEMPERATURE", 0.2),
            log_level=os.environ.get("MN_LOG_LEVEL", "INFO").upper(),
        )

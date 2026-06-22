"""Agent (Runnable chain) definitions.

Each agent is a small LCEL chain:  prompt | model | StrOutputParser.

Chain-level retry (`.with_retry`) is layered on top of the SDK-level retry
configured in :mod:`llm`, giving two independent backoff layers. The two
sub-agent chains are returned as named Runnables so the orchestrator can wrap
them in a ``RunnableParallel`` for concurrent execution.
"""

from __future__ import annotations

from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import Runnable

from .config import AppConfig
from .llm import build_chat_model
from .prompts import EMAIL_PROMPT, ORCHESTRATOR_PROMPT, SUMMARY_PROMPT


def _with_chain_retry(chain: Runnable, app_config: AppConfig) -> Runnable:
    """Add exponential-backoff retry around an entire LCEL chain."""

    return chain.with_retry(
        stop_after_attempt=app_config.chain_max_attempts,
        wait_exponential_jitter=True,
    )


def build_summary_agent(app_config: AppConfig) -> Runnable:
    """Sub-agent 1: executive-summary writer (gpt-4.1)."""

    model = build_chat_model(app_config.summary_agent, app_config)
    chain = (SUMMARY_PROMPT | model | StrOutputParser()).with_config(
        run_name="summary_agent"
    )
    return _with_chain_retry(chain, app_config)


def build_email_agent(app_config: AppConfig) -> Runnable:
    """Sub-agent 2: follow-up-email drafter (gpt-4.1-mini)."""

    model = build_chat_model(app_config.email_agent, app_config)
    chain = (EMAIL_PROMPT | model | StrOutputParser()).with_config(
        run_name="email_agent"
    )
    return _with_chain_retry(chain, app_config)


def build_orchestrator_agent(app_config: AppConfig) -> Runnable:
    """Orchestrator synthesis chain (gpt-4.1).

    Consumes ``{summary, email}`` and emits the final contract-formatted text.
    """

    model = build_chat_model(app_config.orchestrator, app_config)
    chain = (ORCHESTRATOR_PROMPT | model | StrOutputParser()).with_config(
        run_name="orchestrator_synthesis"
    )
    return _with_chain_retry(chain, app_config)

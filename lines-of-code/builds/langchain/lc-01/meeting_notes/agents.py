"""Agent (chain) construction.

Each agent is an LCEL chain: ``prompt | ChatOpenAI | StrOutputParser``.
Two retry layers and one timeout layer are baked in here so every agent is
production-hardened the moment it is built:

  * ``ChatOpenAI(timeout=...)``     -> per-request HTTP timeout
  * ``ChatOpenAI(max_retries=...)`` -> client retry on network/429/5xx
  * ``.with_retry(...)``            -> chain-level retry (exponential + jitter)

``.with_config(run_name=, tags=)`` names each chain so the tracing callback and
LangSmith can attribute latency/tokens to the right agent.
"""

from __future__ import annotations

from dataclasses import dataclass

from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI

from .config import AppConfig, ModelConfig
from .prompts import EMAIL_PROMPT, ORCHESTRATOR_PROMPT, SUMMARY_PROMPT


@dataclass
class Agents:
    """The three runnables that make up the system."""

    summarizer: Runnable
    emailer: Runnable
    orchestrator: Runnable


def _make_llm(mc: ModelConfig, api_key: str) -> ChatOpenAI:
    """Build a ChatOpenAI client with per-call timeout + client-side retries."""

    return ChatOpenAI(
        model=mc.name,
        temperature=mc.temperature,
        timeout=mc.timeout,          # per-request HTTP timeout (seconds)
        max_retries=mc.max_retries,  # retry layer 1: OpenAI client
        api_key=api_key,
    )


def _harden(chain: Runnable, *, run_name: str, tags: list[str], attempts: int) -> Runnable:
    """Apply chain-level retry (layer 2) and tracing identity to a chain."""

    return chain.with_retry(
        retry_if_exception_type=(Exception,),
        wait_exponential_jitter=True,
        stop_after_attempt=attempts,
    ).with_config(run_name=run_name, tags=tags)


def build_agents(cfg: AppConfig) -> Agents:
    summarizer = _harden(
        SUMMARY_PROMPT | _make_llm(cfg.summarizer, cfg.openai_api_key) | StrOutputParser(),
        run_name="subagent.executive_summary",
        tags=["subagent", "summary", cfg.summarizer.name],
        attempts=cfg.chain_max_attempts,
    )

    emailer = _harden(
        EMAIL_PROMPT | _make_llm(cfg.emailer, cfg.openai_api_key) | StrOutputParser(),
        run_name="subagent.follow_up_email",
        tags=["subagent", "email", cfg.emailer.name],
        attempts=cfg.chain_max_attempts,
    )

    orchestrator = _harden(
        ORCHESTRATOR_PROMPT | _make_llm(cfg.orchestrator, cfg.openai_api_key) | StrOutputParser(),
        run_name="orchestrator.assemble",
        tags=["orchestrator", cfg.orchestrator.name],
        attempts=cfg.chain_max_attempts,
    )

    return Agents(summarizer=summarizer, emailer=emailer, orchestrator=orchestrator)

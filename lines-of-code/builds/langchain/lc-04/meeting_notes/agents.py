"""Agent (sub-chain) builders.

Each agent is a small LCEL chain: ``prompt | ChatOpenAI | StrOutputParser``.

Resilience is layered:
- ``ChatOpenAI(timeout=...)``      -> per-call timeout.
- ``ChatOpenAI(max_retries=...)``  -> SDK-level retry (429 / 5xx / transient net).
- ``.with_retry(...)``             -> runnable-level retry wrapping the whole
                                      sub-chain (catches parse/other failures),
                                      with exponential backoff + jitter.
Every chain is tagged with ``run_name`` so it is identifiable in traces.
"""
from __future__ import annotations

from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI

from .config import AppConfig, ModelConfig
from .prompts import EMAILER_PROMPT, ORCHESTRATOR_PROMPT, SUMMARIZER_PROMPT


def _build_llm(spec: ModelConfig, api_key: str) -> ChatOpenAI:
    """Construct a ChatOpenAI client with per-call timeout + SDK retries."""
    return ChatOpenAI(
        model=spec.model,
        temperature=spec.temperature,
        timeout=spec.timeout,          # per-call timeout (seconds)
        max_retries=spec.max_retries,  # SDK-level retry on transient errors
        api_key=api_key,
    )


def _with_resilience(chain: Runnable, cfg: AppConfig, run_name: str) -> Runnable:
    """Add runnable-level retry + a stable run name for tracing."""
    return chain.with_retry(
        stop_after_attempt=cfg.chain_max_attempts,
        wait_exponential_jitter=True,
    ).with_config(run_name=run_name)


def build_summarizer(cfg: AppConfig) -> Runnable:
    """Sub-agent 1: executive summary writer (gpt-4.1). Input {transcript}."""
    llm = _build_llm(cfg.summarizer, cfg.openai_api_key)
    chain = SUMMARIZER_PROMPT | llm | StrOutputParser()
    return _with_resilience(chain, cfg, "summarizer_subagent")


def build_emailer(cfg: AppConfig) -> Runnable:
    """Sub-agent 2: follow-up email drafter (gpt-4.1-mini). Input {transcript}."""
    llm = _build_llm(cfg.emailer, cfg.openai_api_key)
    chain = EMAILER_PROMPT | llm | StrOutputParser()
    return _with_resilience(chain, cfg, "emailer_subagent")


def build_orchestrator(cfg: AppConfig) -> Runnable:
    """Orchestrator (gpt-4.1). Input {summary, email} -> assembled document."""
    llm = _build_llm(cfg.orchestrator, cfg.openai_api_key)
    chain = ORCHESTRATOR_PROMPT | llm | StrOutputParser()
    return _with_resilience(chain, cfg, "orchestrator")

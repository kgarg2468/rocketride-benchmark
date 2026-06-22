"""Agent and orchestration graph construction (LangChain LCEL).

The graph is::

                         ┌───────────────────────────┐
    transcript ─────────▶│ RunnablePassthrough.assign │
    attendees            │   summary = summary_chain  │  ← these two run
                         │   email   = email_chain    │    CONCURRENTLY
                         └─────────────┬──────────────┘
                                       │  {transcript, attendees, summary, email}
                                       ▼
                              orchestrator_chain  (gpt-4.1)
                                       │
                                       ▼
                              final formatted document

``RunnablePassthrough.assign`` evaluates its assigned keys as a
``RunnableParallel``; on a synchronous ``.invoke`` LangChain dispatches the
branches across a thread pool, so the two sub-agents genuinely execute in
parallel while the original ``transcript``/``attendees`` pass straight through
to the orchestrator.
"""
from __future__ import annotations

from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import Runnable, RunnablePassthrough

from .config import AppConfig
from .llms import build_chat_model
from .prompts import EMAIL_PROMPT, ORCHESTRATOR_PROMPT, SUMMARY_PROMPT

# Runnable-level retry policy (tenacity). This wraps each chain so that *any*
# failure in the prompt->model->parse pipeline (not just transient API errors,
# which max_retries already covers) is retried with exponential backoff+jitter.
_RETRY = dict(
    retry_if_exception_type=(Exception,),
    wait_exponential_jitter=True,
    stop_after_attempt=3,
)


def _build_summary_chain(config: AppConfig) -> Runnable:
    model = build_chat_model(config.summary, config.openai_api_key)
    chain = SUMMARY_PROMPT | model | StrOutputParser()
    return chain.with_retry(**_RETRY).with_config(
        run_name="summary_agent",
        tags=["summary_agent"],
        metadata={"agent": "summary_agent"},
    )


def _build_email_chain(config: AppConfig) -> Runnable:
    model = build_chat_model(config.email, config.openai_api_key)
    chain = EMAIL_PROMPT | model | StrOutputParser()
    return chain.with_retry(**_RETRY).with_config(
        run_name="email_agent",
        tags=["email_agent"],
        metadata={"agent": "email_agent"},
    )


def _build_orchestrator_chain(config: AppConfig) -> Runnable:
    model = build_chat_model(config.orchestrator, config.openai_api_key)
    chain = ORCHESTRATOR_PROMPT | model | StrOutputParser()
    return chain.with_retry(**_RETRY).with_config(
        run_name="orchestrator",
        tags=["orchestrator"],
        metadata={"agent": "orchestrator"},
    )


def build_orchestration_graph(config: AppConfig) -> Runnable:
    """Compose the full fan-out / gather / format graph.

    Input:  {"transcript": str, "attendees": str}
    Output: str  (the final formatted document)
    """
    summary_chain = _build_summary_chain(config)
    email_chain = _build_email_chain(config)
    orchestrator_chain = _build_orchestrator_chain(config)

    fan_out = RunnablePassthrough.assign(
        summary=summary_chain,
        email=email_chain,
    )

    return (fan_out | orchestrator_chain).with_config(run_name="meeting_notes_pipeline")

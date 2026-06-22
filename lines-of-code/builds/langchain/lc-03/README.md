# Multi-Agent Meeting Notes (LangChain + OpenAI)

An orchestrator agent reads a meeting transcript and fans it out to **two
specialist sub-agents that run in parallel**, then assembles their outputs into
a single response that satisfies a strict two-section contract.

```
transcript
    │
    ▼
┌─────────────────────────── RunnableParallel (concurrent) ───────────────────────────┐
│   summary_agent  (gpt-4.1)            │            email_agent  (gpt-4.1-mini)        │
│   executive summary writer            │            follow-up email drafter           │
└───────────────────────────────────────┴──────────────────────────────────────────────┘
    │  {summary, email}
    ▼
orchestrator_synthesis (gpt-4.1)  ── assembles final contract response
    │
    ▼
contract validation + deterministic fallback  ── guarantees the output format
    │
    ▼
## Executive Summary … / ## Draft Follow-up Email …
```

## Why these LangChain primitives

| Concern | Primitive |
|---|---|
| Sub-agents & orchestrator | LCEL chains: `ChatPromptTemplate \| ChatOpenAI \| StrOutputParser` |
| Parallel execution | `RunnableParallel(summary=…, email=…)` — one `.invoke` runs both legs on a thread pool |
| Retry | `ChatOpenAI(max_retries=…)` (SDK) **+** `Runnable.with_retry(...)` (chain, exponential backoff w/ jitter) |
| Per-call timeout | `ChatOpenAI(timeout=…)` |
| Tracing / observability | custom `BaseCallbackHandler` (`tracing.py`) with timing + token usage; optional LangSmith via env |
| Structured prompts | `ChatPromptTemplate` in `prompts.py` (no inlined prompt strings) |
| Contract guarantee | `validation.py` — validate, then deterministic assembly fallback |

No LangGraph — orchestration is pure LangChain (LCEL + `RunnableParallel`).

## Layout

```
meeting_notes/
  config.py        env-driven configuration (models, timeouts, retries)
  exceptions.py    typed error hierarchy
  llm.py           ChatOpenAI factory (timeout + SDK retries)
  prompts.py       ChatPromptTemplate definitions + contract constants
  agents.py        the two sub-agent chains + orchestrator chain (+ chain retry)
  validation.py    contract validation + deterministic assembly
  orchestrator.py  RunnableParallel fan-out → synthesis → contract enforcement
  tracing.py       callback-handler tracing + logging + LangSmith wiring
  cli.py           CLI entry point
requirements.txt   pinned dependencies
sample_transcript.txt
```

## Install

```bash
python -m venv .venv && source .venv/bin/activate   # Python 3.11+
pip install -r requirements.txt
```

## Configure

```bash
export OPENAI_API_KEY='sk-...'        # required
# or: cp .env.example .env  and fill it in (auto-loaded)
```

## Run

```bash
# from a file:
python -m meeting_notes sample_transcript.txt

# from STDIN:
cat sample_transcript.txt | python -m meeting_notes
```

The contract document is written to **STDOUT**; logs/traces go to **STDERR**,
so you can capture just the result:

```bash
python -m meeting_notes sample_transcript.txt 2>run.log > notes.md
```

## Output contract

```
## Executive Summary

[3-4 sentence summary, under 100 words]

## Draft Follow-up Email

[email body under 200 words: greeting, decisions, action items w/ owners+deadlines, next steps]
```

This format is enforced: the orchestrator LLM produces it, and if it ever
drifts, `validation.py` repairs it via deterministic assembly so the contract
is always met.

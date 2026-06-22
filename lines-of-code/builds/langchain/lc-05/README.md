# Multi-Agent Meeting Notes (LangChain + OpenAI)

An orchestrator agent reads a meeting transcript, delegates to two specialist
sub-agents **in parallel**, and assembles a single contract-shaped document:

```
## Executive Summary
...
## Draft Follow-up Email
...
```

## Architecture

```
                         ┌───────────────────────────┐
   transcript ──────────▶│ RunnablePassthrough.assign │
   attendees             │   summary = summary_agent  │  ← run CONCURRENTLY
                         │   email   = email_agent    │
                         └─────────────┬──────────────┘
                                       ▼
                          orchestrator (gpt-4.1) — gather + edit + format
                                       ▼
                          validate_document() — contract enforcement
```

| Role | Model | Implementation |
|------|-------|----------------|
| Orchestrator | `gpt-4.1` | LCEL chain; gathers both drafts, enforces format |
| Summary sub-agent | `gpt-4.1` | `SUMMARY_PROMPT \| ChatOpenAI \| StrOutputParser` |
| Email sub-agent | `gpt-4.1-mini` | `EMAIL_PROMPT \| ChatOpenAI \| StrOutputParser` |

LangChain (LCEL Runnables) is the orchestration framework. No LangGraph — the
graph is a static DAG, so LCEL is the idiomatic fit.

### Where each quality-bar item lives

| Requirement | Location |
|-------------|----------|
| Retry on LLM failure | `chains.py` → `.with_retry(...)` (tenacity) **+** `llms.py` → `max_retries` (OpenAI client) |
| Per-call timeouts | `llms.py` → `ChatOpenAI(timeout=...)` |
| Parallel sub-agents | `chains.py` → `RunnablePassthrough.assign(summary=..., email=...)` (RunnableParallel; thread-pool fan-out) |
| Templated prompts | `prompts.py` → `ChatPromptTemplate`s (no inlined strings) |
| Tracing / observability | `tracing.py` → `ConsoleTracer` callback (latency + tokens) + optional LangSmith via env |
| Error handling | `errors.py` typed exceptions + `pipeline.py` try/except + `validation.py` contract checks |

## Setup

```bash
python -m venv .venv && source .venv/bin/activate   # Python 3.11+
pip install -r requirements.txt
cp .env.example .env        # then put your real OPENAI_API_KEY in .env
```

## Run

```bash
# Bundled sample transcript:
python -m meeting_notes

# Your own transcript:
python -m meeting_notes path/to/transcript.txt --attendees "Priya, Marcus, Dana, Tom"

# From stdin:
cat transcript.txt | python -m meeting_notes -
```

Diagnostics (LLM start/end, latency, token usage, warnings) go to **stderr**;
the final validated document is printed to **stdout**.

## Layout

```
meeting_notes/
  config.py       # env-driven, validated, frozen config
  errors.py       # typed exception hierarchy
  llms.py         # ChatOpenAI factory (timeout + retries)
  prompts.py      # ChatPromptTemplate definitions
  chains.py       # LCEL agents + fan-out/gather graph
  validation.py   # deterministic output-contract checks
  tracing.py      # logging + LLM callback tracer
  pipeline.py     # build_pipeline / run_pipeline
  __main__.py     # CLI
transcripts/
  sample_meeting.txt
requirements.txt
.env.example
```

# Multi-Agent Meeting Notes (LangChain)

An orchestrator agent reads a meeting transcript and delegates, **in parallel**,
to two specialist sub-agents:

| Agent | Model | Job |
|---|---|---|
| `subagent.executive_summary` | `gpt-4.1` | 3–4 sentence executive summary (<100 words) |
| `subagent.follow_up_email` | `gpt-4.1-mini` | Recap email body (<200 words) |
| `orchestrator.assemble` | `gpt-4.1` | Collects both, emits the final two-section doc |

The orchestrator output is then passed through a deterministic `enforce_contract`
step that **guarantees** the exact output format (the stop condition).

## Architecture (LangChain primitives)

- **LCEL chains** — each agent is `ChatPromptTemplate | ChatOpenAI | StrOutputParser`.
- **`RunnableParallel`** — fans out to both sub-agents as concurrent asyncio
  tasks via `ainvoke` (concurrent execution, no LangGraph).
- **Retry (2 layers)** — `ChatOpenAI(max_retries=...)` (client) + `.with_retry(...)`
  (chain, exponential backoff + jitter).
- **Timeouts (2 layers)** — `ChatOpenAI(timeout=...)` per call + `asyncio.wait_for`
  wall-clock backstop per stage.
- **Observability** — `TracingCallbackHandler` logs per-agent latency + token
  usage; optional LangSmith via env vars.
- **Structured prompts** — all prompts live in `prompts.py`, never inlined.

```
meeting_notes/
├─ config.py         # env-driven, validated configuration
├─ prompts.py        # ChatPromptTemplate definitions (single source of truth)
├─ observability.py  # logging + tracing callback handler
├─ agents.py         # builds the 3 hardened LCEL chains
├─ pipeline.py       # RunnableParallel fan-out/in + contract enforcement
├─ cli.py            # argparse entry point
├─ sample.py         # bundled synthetic transcript
└─ __main__.py       # python -m meeting_notes
```

## Output contract

```
## Executive Summary

[3-4 sentence summary, under 100 words]

## Draft Follow-up Email

[email body under 200 words: greeting, decisions, action items w/ owners +
deadlines, next steps]
```

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then put your real OPENAI_API_KEY in .env
# or: export OPENAI_API_KEY=sk-...
```

## Run

```bash
# Bundled sample transcript:
python -m meeting_notes

# Your own transcript file:
python -m meeting_notes --file sample_transcript.txt

# From stdin:
cat sample_transcript.txt | python -m meeting_notes

# As a positional argument:
python -m meeting_notes "Attendees: ... full transcript text ..."
```

Diagnostic logs go to **stderr**; the contract document goes to **stdout**, so
you can pipe it: `python -m meeting_notes -f sample_transcript.txt > notes.md`.

Requires Python 3.11+.

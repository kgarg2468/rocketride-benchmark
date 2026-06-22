# Multi-Agent Meeting Notes (LangChain)

An orchestrator agent reads a meeting transcript and delegates, **in parallel**,
to two specialist sub-agents:

- **Executive summary writer** — OpenAI `gpt-4.1`
- **Follow-up email drafter** — OpenAI `gpt-4.1-mini` (smaller/cheaper, suited to
  the more constrained drafting task)

The orchestrator (`gpt-4.1`) collects both outputs and emits a single
contract-compliant document with two clearly marked sections.

## Architecture

Built on **LangChain LCEL** (no LangGraph). The fan-out/join is a static graph,
so plain runnables are the right primitive:

```
{transcript}
   └─ RunnableParallel(summary=summarizer, email=emailer)   # concurrent
        └─ RunnableParallel(final=orchestrator, summary=…, email=…)
             └─ RunnableLambda(finalize)   # validate contract + deterministic repair
                  └─ final document (str)
```

| Concern | Where |
|---|---|
| Parallel sub-agents | `RunnableParallel` in `pipeline.py` |
| Structured prompts | `ChatPromptTemplate`s in `prompts.py` |
| Retry on LLM failure | `ChatOpenAI(max_retries=…)` + `.with_retry()` in `agents.py` |
| Per-call timeout | `ChatOpenAI(timeout=…)` in `agents.py` |
| Tracing/observability | `TracingCallbackHandler` + optional LangSmith in `observability.py` |
| Output-contract enforcement | `formatting.py` + `finalize()` in `pipeline.py` |
| Error handling | custom exceptions + CLI exit codes in `__main__.py` |

## Files

```
meeting_notes/
  config.py          env loading, model specs, timeout/retry knobs
  prompts.py         ChatPromptTemplate definitions + contract constants
  observability.py   tracing callback handler + LangSmith toggle
  agents.py          the three agent sub-chains
  pipeline.py        parallel orchestration + contract finalize
  formatting.py      contract validation + deterministic assembly
  __main__.py        CLI entrypoint
requirements.txt     pinned, exact versions
sample_transcript.txt
.env.example
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then put your real OPENAI_API_KEY in .env
```

> Requires Python 3.11+.

## Run

```bash
# Uses the bundled sample_transcript.txt by default:
python -m meeting_notes

# Or pass your own transcript file:
python -m meeting_notes path/to/transcript.txt

# Or pipe via stdin:
cat transcript.txt | python -m meeting_notes -
```

The contract document is printed to **stdout**; logs/traces go to **stderr**
(so `python -m meeting_notes > out.md` captures only the document).

## Optional: LangSmith tracing

Set `LANGSMITH_API_KEY` (and optionally `LANGSMITH_PROJECT`) in `.env` to stream
full traces to LangSmith in addition to local logging.

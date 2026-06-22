# Multi-Agent Meeting Notes (LangChain)

An orchestrator + two parallel specialist sub-agents that turn a meeting
transcript into an executive summary and a follow-up email, rendered against a
strict output contract.

## Architecture

```
{"transcript"}
     │
     ├─ RunnableParallel  (the two sub-agents run concurrently)
     │     summary_subagent : SUMMARY_PROMPT | gpt-4.1      | StrOutputParser
     │     email_subagent   : EMAIL_PROMPT   | gpt-4.1-mini | StrOutputParser
     │
     ├─ orchestrator        : ORCHESTRATOR_PROMPT | gpt-4.1.with_structured_output(FinalNotes)
     │                        (reconciles the two drafts, enforces word limits)
     │
     └─ render_contract     : deterministic → "## Executive Summary … ## Draft Follow-up Email …"
```

| Requirement | Where it lives |
|---|---|
| Parallel sub-agents | `RunnableParallel` in `pipeline.build_pipeline` |
| Templated prompts | `prompts.py` (`ChatPromptTemplate`, system/human roles) |
| Per-call timeout | `models.build_chat_model` → `ChatOpenAI(timeout=…)` |
| Retry on failure | SDK-level `ChatOpenAI(max_retries=…)` + chain-level `.with_retry(...)` |
| Tracing / observability | `observability.TracingCallbackHandler` + optional LangSmith env hooks |
| Error handling | typed exceptions (`ConfigError`, `PipelineError`) + CLI exit codes |
| Output contract guarantee | `pipeline.render_contract` (deterministic, not LLM-owned) |

## Package layout

```
meeting_notes/
  __init__.py        public API
  config.py          Settings (env-driven), ConfigError
  schemas.py         FinalNotes pydantic structured-output contract
  prompts.py         ChatPromptTemplate definitions
  models.py          ChatOpenAI factory (timeout + retry)
  observability.py   logging + tracing callback handler
  pipeline.py        runnable graph, contract renderer, validator, run_meeting_notes
  __main__.py        CLI entry point
requirements.txt
sample_transcript.txt
.env.example
```

## Setup

```bash
pip install -r requirements.txt
export OPENAI_API_KEY='sk-...'        # or copy .env.example to .env
```

## Run

```bash
# bundled sample
python -m meeting_notes

# your own transcript
python -m meeting_notes path/to/transcript.txt

# via stdin
cat transcript.txt | python -m meeting_notes

# notes to a file, logs stay on stderr
python -m meeting_notes transcript.txt > notes.md
```

Programmatic use:

```python
from meeting_notes import run_meeting_notes
print(run_meeting_notes(open("transcript.txt").read()))
```

## Output contract

```
## Executive Summary

[3-4 sentences, under 100 words]

## Draft Follow-up Email

[email body under 200 words]
```

The headers are emitted by the deterministic renderer, so the format is
guaranteed regardless of model behaviour. Word limits are enforced by the
orchestrator and soft-validated (logged) after rendering.
```

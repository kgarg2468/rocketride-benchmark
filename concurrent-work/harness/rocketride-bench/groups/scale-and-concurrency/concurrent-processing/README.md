# concurrent-processing — `bench-pipe` vs `demo-pipe`

Two pipelines live in this folder:

| File | Role | Shape |
|---|---|---|
| `pipeline.pipe` | **benchmark instrument** (the measured stub) | `webhook → workload` |
| `demo.pipe` | **runnable showcase** (real nodes) | `webhook → parse → question → prompt → llm_openai → response_answers` |

`pipeline.pipe` is synthetic on purpose: its `workload` node does AST-identical `sqlite`+sleep
work so RocketRide and LangChain execute *identical* per-doc work (AST-parity-gated) — that's what
makes the head-to-head fair. `demo.pipe` is the human-runnable version: it summarizes each document
with a real LLM call, so you can watch RocketRide process many docs concurrently and cleanly.

## What the demo shows
**64 docs of real per-doc work — concurrent and clean.** RocketRide runs **M warm pipes, each its
own runtime process**, so 64 documents are summarized concurrently with **zero concurrency code in
the `.pipe`**. The head-to-head — where stock
LangChain's `.batch` crashes (`sqlite3.ProgrammingError`) and `.abatch`/sequential serialize — lives
in the benchmark: [`runs/concurrent-processing/REPORT.md`](../../../../../runs/concurrent-processing/REPORT.md).

## Run it
Needs a live runtime (`ws://localhost:5565`) and an OpenAI key — substituted into the pipe's
`${ROCKETRIDE_OPENAI_KEY}` at run time, **never committed**:

```bash
export ROCKETRIDE_OPENAI_KEY=sk-...
cd concurrent-work/harness
python run_demo.py pick --m 16 --n 64
```
Writes `demo-output.sample.md` (per-pipe doc counts, wall time, sample summaries).
Input: `demo-data/meetings.jsonl` (64 short meeting snippets).

## Proof signal
**64 / 64 completed, 0 node errors**, spread across M distinct pipe processes.

## Status
`demo.pipe` is **structurally validated** against runtime v3.2.1.30 (`rrext_validate` → ok). An
end-to-end LLM run needs your key; without one the pipeline still runs but the `llm_openai` node
returns HTTP 401.

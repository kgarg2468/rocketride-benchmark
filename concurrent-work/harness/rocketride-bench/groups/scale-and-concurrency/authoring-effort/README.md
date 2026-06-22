# authoring-effort — `bench-pipe` vs `demo-pipe`

| File | Role | Shape |
|---|---|---|
| `run.py` + `lc/` | **benchmark instrument** | validates the committed RR `rr/workflow.pipe` (regenerated + schema-checked at runtime by `run.py`) and counts imperative concurrency lines / decision-points vs the LangChain `lc/` sources |
| `demo.pipe` | **runnable showcase** (real nodes) | `dropper/chat → parse → question → agent_deepagent → [llm_openai + 2 sub-agents (OpenAI + Gemini)] → response_answers` |

Unlike the other benches, authoring-effort has **no committed `pipeline.pipe`** — its measurement
*generates* a small RR pipe at runtime purely to count authoring cost (0 imperative concurrency lines
for RocketRide vs 14–17 for correct LangChain). `demo.pipe` is the committed, runnable artifact that
makes the authoring claim tangible: a real multi-agent meeting-notes app.

## What the demo shows
**A declarative multi-agent app — 0 lines of orchestration code.** One `agent_deepagent` orchestrator
fans out to **two sub-agents in parallel** — an Executive Summary Writer (gpt-4-1) and an Action-Item
Extractor (gemini) — and assembles a 2-section brief. That's **3 LLM calls across 2 providers and 2
concurrent sub-agents**, and the fan-out is **pure topology** (two `deepagent` control edges), not
code. The authoring-cost head-to-head is in the benchmark:
[`runs/authoring-effort/REPORT.md`](../../../../../runs/authoring-effort/REPORT.md).

## Run it
Needs **both** keys (the Gemini sub-agent):
```bash
export ROCKETRIDE_OPENAI_KEY=sk-...
export ROCKETRIDE_GOOGLE_KEY=...
cd concurrent-work/harness
python run_demo.py authoring
```
Writes `demo-output.sample.md` (the assembled brief). Input: `demo-data/transcript.txt` (one meeting
transcript) — or drop your own file / paste a transcript via the `dropper`/`chat` sources.

## Proof signal
A single `answers` document with `## Executive Summary` + `## Action Items`, produced by the two
sub-agents — with no scheduling code anywhere in `demo.pipe`.

## Status
`demo.pipe` is **structurally validated** against runtime v3.2.1.30 (`rrext_validate` → ok). It mirrors
a proven multi-agent meeting-notes structure (authored fresh). An end-to-end run needs both
keys above.

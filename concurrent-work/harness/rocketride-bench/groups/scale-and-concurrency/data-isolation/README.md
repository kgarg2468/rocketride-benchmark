# data-isolation — `bench-pipe` vs `demo-pipe`

Two pipelines live in this folder:

| File | Role | Shape |
|---|---|---|
| `pipeline.pipe` | **benchmark instrument** (the measured stub) | `webhook → workload` |
| `demo.pipe` | **runnable showcase** (real nodes) | `webhook → parse → question → agent_rocketride → [llm_openai + memory_internal] → response_answers` |

`pipeline.pipe`'s `workload` (`iso_accumulate` mode) appends each doc to a module-level list and
emits it — the measurement instrument that proves per-pipe state. `demo.pipe` does the same thing
with a **real agent + run-scoped `memory_internal`**: each pipe extracts the key entity from every
document it sees and accumulates them in its own private memory.

## What the demo shows
**Each pipe is its own data.** Run two pipes with **disjoint** document sets: each pipe's final list
holds **only its own** docs' entities — **0 leak**, by construction, because `memory_internal` is
private to each run (there's no shared mutable place to get wrong across pipes). The head-to-head —
where under concurrent writers stock LangChain's shared-state idiom **silently drops updates, up to
84% in our runs** — is in the benchmark:
[`runs/data-isolation/REPORT.md`](../../../../../runs/data-isolation/REPORT.md).

## Run it
```bash
export ROCKETRIDE_OPENAI_KEY=sk-...
cd concurrent-work/harness
python run_demo.py instance
```
Writes `demo-output.sample.md` (each pipe's accumulated list, side by side).
Input: `demo-data/set-a.jsonl` + `demo-data/set-b.jsonl` (two disjoint entity sets).

## Proof signal
Pipe A's list = the **set-A** entities only; pipe B's list = the **set-B** entities only. Neither
pipe sees the other's data.

## Status
`demo.pipe` is **structurally validated** against runtime v3.2.1.30 (`rrext_validate` → ok). An
end-to-end run needs your OpenAI key (the agent's LLM). Isolation is a property of the topology, not
the model — it holds regardless of which LLM drives the extraction.

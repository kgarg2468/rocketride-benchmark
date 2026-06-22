# fault-isolation — `bench-pipe` vs `demo-pipe`

Two pipelines live in this folder:

| File | Role | Shape |
|---|---|---|
| `pipeline.pipe` | **benchmark instrument** (the measured stub) | `filesys → workload` |
| `demo.pipe` | **runnable showcase** (real nodes) | `filesys → parse → question → prompt → llm_openai → response_answers` |

`pipeline.pipe` is the measured stub; `demo.pipe` is the runnable version — a folder of good documents
plus **one deliberately-malformed `.pdf`** that the parser cannot read.

## What the demo shows
**A fault stays contained.** Each file is its own run (its own runtime process). The malformed file's
run fails in `parse`; **the server survives and every good file's run still completes**. The
head-to-head — where real in-process LangChain runs all 4 tasks in one interpreter, so a hard process
abort terminates the interpreter and loses **all 4 of 4** tasks — is in the benchmark:
[`runs/fault-isolation/REPORT.md`](../../../../../runs/fault-isolation/REPORT.md).

## Run it
```bash
export ROCKETRIDE_OPENAI_KEY=sk-...
cd concurrent-work/harness
python run_demo.py crash      # sets ROCKETRIDE_DEMO_DOCS to demo-data/docs for you
```
Writes `demo-output.sample.md` (the completed/failed/serviceUp counts).
Input: `demo-data/docs/` — `good1..good4.txt` + `broken-notes.pdf` (a corrupt PDF: valid `%PDF` header, garbage body — the parser cannot read it).

## Proof signal
`completedCount = 4`, `failedCount = 1` (the malformed file), **`serviceUp = true`** — the runtime
keeps running and the good documents are summarized.

## Status
`demo.pipe` is **structurally validated** against runtime v3.2.1.30 (`rrext_validate` → ok). The good
files need your OpenAI key to summarize; the containment behavior (server survives, good runs
complete) does not depend on the LLM.

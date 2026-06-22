# lines-of-code · same workflow, AI-built in both frameworks — one file vs a package

> **Verdict: one declarative pipeline file vs a multi-file Python package — with zero
> concurrency/wiring lines on the RocketRide side and ~3.6× fewer characters, every build.** We had
> Claude (Claude Code) build the **same** meeting-notes assistant — transcript in → executive summary +
> follow-up email out — **5 times in RocketRide** and **5 times in LangChain**. Every single build, the
> RocketRide version is a **single declarative `.pipe` (~120 lines)** while the LangChain version is a
> **multi-file Python package (~690 lines)** — and **~3.6× fewer characters** too, so it's genuinely
> less to write and maintain.

## Results (5 builds each)

| Build | RocketRide `.pipe` | LangChain (Python) | Characters |
|---|---:|---:|---:|
| 1 | 115 lines · 1 file | 689 lines · 9 files | **4.0× fewer** |
| 2 | 104 lines · 1 file | 685 lines · 8 files | **3.1× fewer** |
| 3 | 123 lines · 1 file | 930 lines · 11 files | **4.4× fewer** |
| 4 | 128 lines · 1 file | 771 lines · 8 files | **3.9× fewer** |
| 5 | 136 lines · 1 file | 682 lines · 10 files | **3.9× fewer** |
| **median** | **123 lines · 1 file** | **689 lines · 8–11 files** | **≈3.6×** (of medians) |

The per-build character ratios span **3.1–4.4×**; the headline **≈3.6×** is the ratio of the median
artifact sizes (below), the same figure the rest of the series reports. Descriptively, that's a
**~120-line pipeline vs a ~690-line package** (line range 104–136 vs 682–930).

**Characters tell the same story** (median): RocketRide **~7,000** vs LangChain **~25,000** — **3.6× fewer**
(3.1–4.4× on each individual build). One file vs a package, every build, favors RocketRide.

The ~690-line LangChain package also hand-builds the retries, timeouts, tracing, and config validation that RocketRide's runtime provides — part of why the `.pipe` is smaller is that the runtime absorbs that hardening, not that the workflow does less.

## Method

- **Same task, both sides:** a meeting-notes assistant (parse a transcript → an executive summary + a
  draft follow-up email with owners/deadlines). Identical spec given to the builder for each framework.
- **Built by AI:** Claude Code authored every artifact — built with the RocketRide pipeline-building
  skills on one side (the realistic way you'd build it), and as an idiomatic Python package on the other.
- **What's counted:** the RocketRide artifact is one `.pipe` (declarative JSON); the LangChain artifact is
  a Python package (`meeting_notes/` — `agents.py`, `pipeline.py`, `prompts.py`, `cli.py`, …). Lines and
  characters are measured by [`artifact_size.py`](artifact_size.py), committed in this folder.
- **5 builds each** — the consistency, not a single lucky run, is the point.

## See it / reproduce it

- **Featured pair:** [`builds/rocketride/run-01/meeting-notes-assistant.pipe`](builds/rocketride/run-01/meeting-notes-assistant.pipe)
  — one ~115-line `.pipe` — vs [`builds/langchain/lc-01/`](builds/langchain/lc-01/) (a 9-file, 689-line package).
- **All 10 artifacts** are committed under [`builds/`](builds/) — `wc -l` them yourself.
- **Re-derive the numbers:** `python measure.py` → regenerates [`results.json`](results.json).

For correctness under concurrency, see [`../concurrent-work/`](../concurrent-work/).

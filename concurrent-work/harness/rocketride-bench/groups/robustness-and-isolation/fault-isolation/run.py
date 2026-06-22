"""fault-isolation (D5) — a genuine RocketRide WIN.

Each run is its own runtime process. A node that HARD-crashes (os._exit(134), simulating a
native/segfault crash) kills only THAT run's subprocess — the server and sibling runs survive.
Contrast: REAL in-process LangChain `.abatch` running M tasks in one interpreter — one os._exit
takes the whole process down (0/M complete). Process-per-run buys fault isolation by construction.

Run (engine up):  python groups/robustness-and-isolation/fault-isolation/run.py
"""
import asyncio
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, REPO)

from harness import client as rrclient, competitors as comp, config, measure, pipes  # noqa: E402

PIPE = os.path.join(HERE, "pipeline.pipe")

# In-process competitor: REAL LangChain `.abatch` over 4 tasks in ONE interpreter. argv[1] is the
# leg index that hard-crashes (-1 = none). With a crash, os._exit kills the shared interpreter, so
# NOTHING completes — the in-process model loses all M. STRICT: langchain_core is a hard import here
# (no proxy fallback), and require_real_langchain() proves it ran before any number is recorded.
LC_INPROC = r"""
import asyncio, os, sys
from langchain_core.runnables import RunnableLambda   # STRICT: hard import, no proxy fallback
CRASH = int(sys.argv[1]) if len(sys.argv) > 1 else -1
async def leg(i):
    if i == CRASH:
        sys.stderr.write("INPROC_CRASH\n"); sys.stderr.flush()
        os._exit(134)            # one bad task hard-crashes the shared interpreter
    await asyncio.sleep(0.2); return i
async def main():
    res = await RunnableLambda(leg).abatch(list(range(4)), return_exceptions=True)
    print("framework", "langchain")
    print("completed", len([r for r in res if isinstance(r, int)]))   # never prints if it crashed
asyncio.run(main())
"""


async def _run(c, expect_ok):
    try:
        started = await asyncio.wait_for(c.use(filepath=PIPE, threads=1, ttl=0,
                                               pipelineTraceLevel="none", env=pipes.data_env()), timeout=60)
        tok = started["token"]
    except Exception as e:
        return {"ok": False, "error": "use failed: %r" % e}
    done = False
    for _ in range(100):
        await asyncio.sleep(0.1)
        try:
            st = await c.get_task_status(tok)
        except Exception:
            st = None
        if st and (st.get("completed") or st.get("completedCount", 0) >= 1 or st.get("state", 0) >= 5):
            done = True
            break
    try:
        await c.terminate(tok)
    except Exception:
        pass
    return {"ok": done}


async def main():
    pipes.write_pipe(PIPE, pipes.filesys_work("input1"))
    lc_probe = comp.require_real_langchain()  # STRICT: abort unless REAL LangChain executes
    srv = measure.server_proc()
    server_pid_before = srv.pid if srv else None

    c = await rrclient.connect()
    try:
        pipes.set_params(mode="none", label="healthy")
        healthy_before = await _run(c, True)

        pipes.set_params(mode="crash", label="crash")
        crash_run = await _run(c, False)  # the node os._exit(134)s its own subprocess
        await asyncio.sleep(0.5)
        srv2 = measure.server_proc()
        server_alive = srv2 is not None and srv2.pid == server_pid_before

        pipes.set_params(mode="none", label="recovery")
        healthy_after = await _run(c, True)  # server still serves new runs
    finally:
        await c.disconnect()

    # In-process competitor (real LangChain): healthy probe confirms the framework + that it
    # completes 4/4, then the crash probe shows ONE hard crash takes the whole process down.
    healthy = subprocess.run([sys.executable, "-c", LC_INPROC, "-1"], capture_output=True, text=True)
    inproc_framework, inproc_healthy_completed = "unknown", 0
    for line in healthy.stdout.splitlines():
        if line.startswith("framework"):
            inproc_framework = line.split()[-1]
        elif line.startswith("completed"):
            try:
                inproc_healthy_completed = int(line.split()[-1])
            except Exception:
                pass
    if inproc_framework != "langchain" or inproc_healthy_completed != 4:
        raise SystemExit("in-process LangChain baseline did not execute cleanly "
                         "(framework=%s, healthy=%d/4, stderr=%s) — no number recorded"
                         % (inproc_framework, inproc_healthy_completed, (healthy.stderr or "")[-200:]))

    p = subprocess.run([sys.executable, "-c", LC_INPROC, "2"], capture_output=True, text=True)
    inproc_completed = 0
    for line in p.stdout.splitlines():
        if line.startswith("completed"):
            try:
                inproc_completed = int(line.split()[-1])
            except Exception:
                inproc_completed = 0

    out = {
        "benchmark": "fault-isolation", "old_id": "D5",
        "hypothesis": "a hard node crash is isolated to its run; the server + siblings survive",
        "provenance": config.provenance(),
        "rocketride": {
            "server_pid_before": server_pid_before,
            "healthy_before_ok": healthy_before["ok"],
            "crash_run_completed": crash_run["ok"],
            "server_survived_crash": server_alive,
            "healthy_after_ok": healthy_after["ok"]},
        "in_process_baseline": {
            "framework": inproc_framework, "tasks": 4,
            "lc_version": lc_probe["lc_version"],
            "lc_python": lc_probe.get("lc_python"),
            "langchain_core_file": lc_probe.get("langchain_core_file"),
            "healthy_completed": inproc_healthy_completed,
            "completed": inproc_completed, "process_exit_code": p.returncode,
            "died": p.returncode != 0},
        "verdict_metrics": {
            "rr_isolation_holds": bool(healthy_before["ok"] and server_alive and healthy_after["ok"]),
            "inproc_framework": inproc_framework,
            "inproc_healthy_ok": inproc_healthy_completed == 4,
            "inproc_lost_all": inproc_completed == 0},
    }
    with open(os.path.join(HERE, "results.json"), "w") as f:
        json.dump(out, f, indent=2, default=str)
    subprocess.run([sys.executable, os.path.join(REPO, "scripts", "make_diagrams.py"),
                    PIPE, os.path.join(HERE, "canvas")])

    rr = out["rocketride"]
    print("RocketRide: healthy-before=%s  crash-run-completed=%s  server-survived=%s  healthy-after=%s"
          % (rr["healthy_before_ok"], rr["crash_run_completed"], rr["server_survived_crash"], rr["healthy_after_ok"]))
    print("In-process baseline (%s): healthy %d/4, crash-run %d/4, exit %d (process %s)"
          % (inproc_framework, inproc_healthy_completed, inproc_completed, p.returncode,
             "DIED" if p.returncode != 0 else "survived"))
    print("VERDICT: RR isolation holds = %s ; in-process lost all = %s"
          % (out["verdict_metrics"]["rr_isolation_holds"], out["verdict_metrics"]["inproc_lost_all"]))


if __name__ == "__main__":
    asyncio.run(main())

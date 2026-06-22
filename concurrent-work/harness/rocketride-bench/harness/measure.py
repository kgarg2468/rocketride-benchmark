"""Independent OS-level measurement: peak RSS of the engine's per-run subprocess tree, and CPU
seconds for subprocess baselines. We never trust only the engine's self-report — these are the
cross-check.
"""
import os
import threading
import time

import psutil


def human_mb(nbytes):
    return round(nbytes / (1024 * 1024), 1)


_PROC_ERRS = (psutil.NoSuchProcess, psutil.AccessDenied, PermissionError, SystemError, OSError)


def _cmdline(p):
    try:
        return p.cmdline() or []
    except _PROC_ERRS:
        return []


def server_proc(needle="ai/eaas.py"):
    """The standing EAAS server process (so we can find its per-run children).

    Pidfile-first: scripts/start_engine.sh records OUR server's pid in results/engine.pid —
    needle-scanning alone can match a DIFFERENT engine on the box (e.g. the VS Code
    extension's `engine --autoterm`), which would silently zero the RSS measurement."""
    try:
        from . import config
        with open(os.path.join(config.RESULTS_DIR, "engine.pid")) as f:
            p = psutil.Process(int(f.read().strip()))
        if p.is_running():
            return p
    except (OSError, ValueError, psutil.NoSuchProcess):
        pass
    for p in psutil.process_iter():  # iterate lazily; read cmdline defensively per-process
        if any(needle in str(c) for c in _cmdline(p)):
            return p
    return None


def task_kids(needle="ai/node"):
    """The per-run engine task subprocesses (children of the server) — process-per-run."""
    srv = server_proc()
    if not srv:
        return []
    kids = []
    try:
        for c in srv.children(recursive=True):
            if any(needle in str(x) for x in _cmdline(c)):
                kids.append(c)
    except _PROC_ERRS:
        pass
    return kids


class RSSSampler(threading.Thread):
    """Samples the SUMMED RSS of the processes returned by procs_fn; tracks the peak."""

    def __init__(self, procs_fn, interval=0.05):
        super().__init__(daemon=True)
        self.procs_fn = procs_fn
        self.interval = interval
        self.peak = 0
        self.n_samples = 0
        self._stop_event = threading.Event()  # NOT _stop (collides with Thread._stop())

    def run(self):
        while not self._stop_event.is_set():
            tot = 0
            for p in self.procs_fn():
                try:
                    tot += p.memory_info().rss
                except _PROC_ERRS:
                    pass
            self.peak = max(self.peak, tot)
            self.n_samples += 1
            time.sleep(self.interval)

    def stop(self):
        self._stop_event.set()

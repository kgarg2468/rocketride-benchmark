"""Shared config + provenance for the bench suite.

Public-ready: every path is env-first and falls back to a repo-relative location — there are
NO hardcoded machine/home paths, and missing prerequisites fail loud with a clear message.

  ENGINE_DIR        the extracted RocketRide runtime bundle (contains ./engine, ai/, nodes/).
                    Default: <repo>/engine (where scripts/provision.sh downloads it).
  ROCKETRIDE_URI    the standing EAAS server (direct-connect). Default ws://localhost:5565.
  ROCKETRIDE_APIKEY auth token (any non-empty string works for a local server).
"""
import hashlib
import os
import platform
import subprocess
import sys

HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(HARNESS_DIR)

# Engine: env-first, else the provisioned ./engine inside the repo.
ENGINE_DIR = os.environ.get("ENGINE_DIR") or os.path.join(REPO_DIR, "engine")
ENGINE = os.path.join(ENGINE_DIR, "engine")

# Direct-connect server (the headline product path).
URI = os.environ.get("ROCKETRIDE_URI", "ws://localhost:5565")
AUTH = os.environ.get("ROCKETRIDE_APIKEY", "local-bench")

# Repo locations (all committed; evidence lives next to the benchmark that produced it).
CATALOG_DIR = os.path.join(REPO_DIR, "catalog", ".rocketride")
RESULTS_DIR = os.path.join(REPO_DIR, "results")
DATA_DIR = os.path.join(REPO_DIR, "data")
NODES_DIR = os.path.join(REPO_DIR, "nodes")
BENCH_PARAMS = os.environ.get("ROCKETRIDE_BENCH_PARAMS", "/tmp/rr_bench_params.json")


def engine_present():
    return os.path.isfile(ENGINE)


def require_engine():
    """Fail loud (not silently) when the engine is missing — point the user at provisioning."""
    if not engine_present():
        raise SystemExit(
            "RocketRide runtime not found at %s.\n"
            "  Set $ENGINE_DIR to an extracted engine bundle, or run scripts/provision.sh "
            "to download the pinned prebuilt." % ENGINE
        )


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _cpu_brand():
    try:
        if sys.platform == "darwin":
            return subprocess.check_output(
                ["sysctl", "-n", "machdep.cpu.brand_string"], text=True).strip()
    except Exception:
        pass
    return platform.processor() or "unknown"


def engine_version():
    try:
        out = subprocess.run([ENGINE, "--version"], cwd=ENGINE_DIR,
                             capture_output=True, text=True, timeout=30)
        return (out.stdout or out.stderr).strip()
    except Exception as e:  # pragma: no cover
        return "unknown (%s)" % e


def provenance():
    """Machine + engine identity recorded with every result, so a reader can tell exactly
    what produced the numbers and whether their re-run matches."""
    import psutil

    vm = psutil.virtual_memory()
    prov = {
        "engine_dir": ENGINE_DIR,
        "engine_version": engine_version(),
        "uri": URI,
        "cpu_brand": _cpu_brand(),
        "machine": platform.platform(),
        "arch": platform.machine(),
        "physical_cores": psutil.cpu_count(logical=False),
        "logical_cores": psutil.cpu_count(logical=True),
        "total_ram_gib": round(vm.total / (1024 ** 3), 2),
        "python": sys.version.split()[0],
    }
    try:
        prov["engine_sha256"] = _sha256(ENGINE)
        prov["engine_size_bytes"] = os.path.getsize(ENGINE)
    except OSError:
        pass
    return prov

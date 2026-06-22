"""SDK connection helpers + the validate() double-wrap workaround + .pipe loading.

These wrap the genuine `rocketride` SDK; they add no engine behavior.
"""
import json

from rocketride import RocketRideClient

from . import config


async def connect(on_event=None, uri=None, auth=None):
    client = RocketRideClient(uri=uri or config.URI, auth=auth or config.AUTH,
                              on_event=on_event)
    await client.connect()
    return client


def load_pipe(path):
    """Load a .pipe (JSON) and return the flat pipeline config, unwrapping a
    {"pipeline": {...}} envelope if present — exactly as SDK use(filepath=) does."""
    with open(path, "r", encoding="utf-8") as f:
        parsed = json.load(f)
    return parsed.get("pipeline", parsed) if isinstance(parsed, dict) else parsed


def resolve_source(pipe):
    """Find the entry component id: explicit `source` → the config.mode=='Source' node →
    the first component with no inbound `input` lane."""
    if isinstance(pipe, dict):
        if pipe.get("source"):
            return pipe["source"]
        comps = pipe.get("components", [])
        for c in comps:
            cfg = c.get("config") or {}
            if isinstance(cfg, dict) and str(cfg.get("mode", "")).lower() == "source":
                return c.get("id")
        have_input = {c.get("id") for c in comps if c.get("input")}
        for c in comps:
            if c.get("id") not in have_input:
                return c.get("id")
    return None


async def validate_pipeline(client, pipe, source=None):
    """Validate a flat pipeline config. Returns {ok, errors, warnings}.

    The SDK's client.validate() single-wraps the pipeline, but server-v3.2.1's
    rrext_validate expects it double-wrapped as {"pipeline": cfg} (single-wrapped →
    "'pipeline' is missing or invalid"). use()/execute is unaffected. This is a
    server-version quirk, not our bug — carried forward verbatim and disclosed.
    """
    src = source or resolve_source(pipe)
    res = await client.call("rrext_validate", pipeline={"pipeline": pipe}, source=src)
    errs = res.get("errors") if isinstance(res, dict) else None
    warns = res.get("warnings") if isinstance(res, dict) else None
    return {"ok": not errs, "errors": errs, "warnings": warns, "source": src}

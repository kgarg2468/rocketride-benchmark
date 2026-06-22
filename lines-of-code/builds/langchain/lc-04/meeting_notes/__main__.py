"""Command-line entrypoint.

Usage:
    python -m meeting_notes [TRANSCRIPT_PATH]
    python -m meeting_notes -            # read transcript from stdin
    python -m meeting_notes              # defaults to sample_transcript.txt

Exit codes:
    0  success
    1  configuration error (e.g. missing OPENAI_API_KEY)
    2  bad usage / transcript not found
    3  pipeline failure (after retries)
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .config import ConfigError, load_config
from .observability import configure_logging
from .pipeline import PipelineError, run_pipeline

logger = logging.getLogger("meeting_notes.cli")

DEFAULT_TRANSCRIPT = "sample_transcript.txt"


def _read_transcript(source: str) -> str:
    if source == "-":
        return sys.stdin.read()
    path = Path(source)
    if not path.is_file():
        raise FileNotFoundError(f"Transcript file not found: {source}")
    return path.read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="meeting_notes",
        description="Generate an executive summary + follow-up email from a "
        "meeting transcript using a parallel multi-agent LangChain pipeline.",
    )
    parser.add_argument(
        "transcript",
        nargs="?",
        default=DEFAULT_TRANSCRIPT,
        help=f"Path to a transcript file, or '-' for stdin "
        f"(default: {DEFAULT_TRANSCRIPT}).",
    )
    args = parser.parse_args(argv)

    # Load config first so logging level reflects the environment.
    try:
        cfg = load_config()
    except ConfigError as exc:
        configure_logging("INFO")
        logger.error("Configuration error: %s", exc)
        return 1

    configure_logging(cfg.log_level)

    try:
        transcript = _read_transcript(args.transcript)
    except (FileNotFoundError, OSError) as exc:
        logger.error("%s", exc)
        return 2

    try:
        document = run_pipeline(cfg, transcript)
    except PipelineError as exc:
        logger.error("Pipeline failed: %s", exc)
        return 3
    except Exception as exc:  # noqa: BLE001 - top-level guard for a CLI
        logger.exception("Unexpected failure: %s", exc)
        return 3

    # The contract document goes to stdout; logs/traces go to stderr.
    print(document)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

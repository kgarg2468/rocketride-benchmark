"""Command-line entry point.

Usage:
    python -m meeting_notes <transcript_file>
    python -m meeting_notes -            # read transcript from STDIN
    cat meeting.txt | python -m meeting_notes
"""

from __future__ import annotations

import argparse
import sys

from .config import load_config
from .exceptions import MeetingNotesError
from .orchestrator import MeetingNotesOrchestrator


def _read_transcript(source: str) -> str:
    if source == "-":
        return sys.stdin.read()
    with open(source, "r", encoding="utf-8") as fh:
        return fh.read()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="meeting_notes",
        description=(
            "Multi-agent meeting-notes generator (LangChain + OpenAI). "
            "Produces an executive summary and a follow-up email draft."
        ),
    )
    parser.add_argument(
        "transcript",
        nargs="?",
        default="-",
        help="Path to a transcript file, or '-' for STDIN (default: STDIN).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        transcript = _read_transcript(args.transcript)
    except OSError as exc:
        print(f"error: could not read transcript: {exc}", file=sys.stderr)
        return 2

    try:
        # Validate configuration early so missing keys fail fast and clearly.
        config = load_config()
        orchestrator = MeetingNotesOrchestrator(config)
        result = orchestrator.process_transcript(transcript)
    except MeetingNotesError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - top-level safety net
        print(f"unexpected error: {exc}", file=sys.stderr)
        return 1

    # The contract document goes to STDOUT; logs/traces go to STDERR.
    print(result)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

"""Command-line entry point.

Reads a transcript from (in priority order): a --file path, a positional
argument, stdin, or the bundled sample. Prints the contract-compliant document
to stdout. Diagnostic logging goes to stderr so stdout stays clean/pipeable.

Exit codes:
    0  success
    1  pipeline failure (LLM / runtime)
    2  configuration or input error
"""

from __future__ import annotations

import argparse
import logging
import sys

from .config import ConfigError, load_config
from .observability import configure_logging
from .pipeline import PipelineError, generate_meeting_notes
from .sample import SAMPLE_TRANSCRIPT

logger = logging.getLogger("meeting_notes")


def _read_transcript(args: argparse.Namespace) -> str:
    if args.file:
        with open(args.file, "r", encoding="utf-8") as fh:
            return fh.read()
    if args.transcript:
        return args.transcript
    if not sys.stdin.isatty():
        piped = sys.stdin.read()
        if piped.strip():
            return piped
    logger.info("No transcript supplied; using bundled sample transcript.")
    return SAMPLE_TRANSCRIPT


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="meeting_notes",
        description="Generate an executive summary + follow-up email from a "
        "meeting transcript using a parallel multi-agent LangChain pipeline.",
    )
    parser.add_argument("transcript", nargs="?", help="Transcript text (positional).")
    parser.add_argument("-f", "--file", help="Path to a transcript text file.")
    parser.add_argument("--log-level", default=None, help="DEBUG/INFO/WARNING/ERROR.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging(args.log_level)

    try:
        cfg = load_config()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    try:
        transcript = _read_transcript(args)
    except OSError as exc:
        print(f"Could not read transcript: {exc}", file=sys.stderr)
        return 2

    try:
        notes = generate_meeting_notes(transcript, cfg)
    except PipelineError as exc:
        print(f"Pipeline error: {exc}", file=sys.stderr)
        return 1

    print(notes.final_document)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

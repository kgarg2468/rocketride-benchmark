"""Command-line entry point.

Usage:
    python -m meeting_notes                         # uses the bundled sample transcript
    python -m meeting_notes path/to/transcript.txt  # your own transcript
    python -m meeting_notes -                        # read transcript from stdin
    python -m meeting_notes file.txt --attendees "Ada, Linus, Grace"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .errors import MeetingNotesError
from .pipeline import run_pipeline

DEFAULT_TRANSCRIPT = Path(__file__).resolve().parent.parent / "transcripts" / "sample_meeting.txt"


def _read_transcript(source: str) -> str:
    if source == "-":
        return sys.stdin.read()
    path = Path(source)
    if not path.exists():
        raise MeetingNotesError(f"Transcript file not found: {path}")
    return path.read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="meeting_notes",
        description="Multi-agent meeting-notes system (LangChain + OpenAI).",
    )
    parser.add_argument(
        "transcript",
        nargs="?",
        default=str(DEFAULT_TRANSCRIPT),
        help="Path to a transcript file, or '-' for stdin. "
        "Defaults to the bundled sample transcript.",
    )
    parser.add_argument(
        "--attendees",
        default="",
        help="Optional comma-separated attendee names. If omitted, the email "
        "agent infers names from the transcript.",
    )
    args = parser.parse_args(argv)

    try:
        transcript = _read_transcript(args.transcript)
        document = run_pipeline(transcript, attendees=args.attendees)
    except MeetingNotesError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    # The validated document is the program's stdout payload.
    print("\n" + document)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

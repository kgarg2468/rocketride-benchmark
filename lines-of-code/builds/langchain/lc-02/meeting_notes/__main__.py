"""Command-line entry point.

Usage:
    python -m meeting_notes path/to/transcript.txt
    cat transcript.txt | python -m meeting_notes
    python -m meeting_notes            # falls back to bundled sample_transcript.txt

The rendered notes are printed to stdout; all logs/traces go to stderr, so you
can redirect cleanly:  python -m meeting_notes t.txt > notes.md
"""

from __future__ import annotations

import sys
from pathlib import Path

from .config import ConfigError, Settings
from .pipeline import PipelineError, run_meeting_notes


def _read_transcript(argv: list[str]) -> str:
    # 1) explicit file path argument
    if len(argv) > 1:
        path = Path(argv[1])
        if not path.is_file():
            print(f"error: transcript file not found: {path}", file=sys.stderr)
            raise SystemExit(2)
        return path.read_text(encoding="utf-8")

    # 2) piped stdin
    if not sys.stdin.isatty():
        data = sys.stdin.read()
        if data.strip():
            return data

    # 3) bundled sample
    sample = Path(__file__).resolve().parent.parent / "sample_transcript.txt"
    if sample.is_file():
        print(f"(no input given; using {sample.name})", file=sys.stderr)
        return sample.read_text(encoding="utf-8")

    print(
        "error: no transcript provided. Pass a file path, pipe via stdin, or "
        "add sample_transcript.txt.",
        file=sys.stderr,
    )
    raise SystemExit(2)


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv
    try:
        transcript = _read_transcript(argv)
        settings = Settings.from_env()
        output = run_meeting_notes(transcript, settings)
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2
    except PipelineError as exc:
        print(f"pipeline error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:  # pragma: no cover
        print("interrupted", file=sys.stderr)
        return 130

    # stdout: the contract-formatted notes only.
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

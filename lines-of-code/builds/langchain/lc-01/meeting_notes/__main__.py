"""Enables ``python -m meeting_notes``."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())

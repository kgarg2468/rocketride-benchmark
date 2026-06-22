"""Typed exception hierarchy so callers can distinguish failure modes."""
from __future__ import annotations


class MeetingNotesError(Exception):
    """Base class for every error raised by this package."""


class ConfigError(MeetingNotesError):
    """Configuration/environment is missing or invalid."""


class PipelineError(MeetingNotesError):
    """A failure occurred while executing the orchestration graph."""


class ValidationError(MeetingNotesError):
    """The produced document violated the output contract."""

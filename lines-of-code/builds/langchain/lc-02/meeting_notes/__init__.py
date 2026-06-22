"""Multi-agent meeting-notes system built on LangChain.

Public API:
    from meeting_notes import run_meeting_notes, Settings

The package implements an orchestrator that fans a meeting transcript out to two
specialist sub-agents in parallel (an executive-summary writer on gpt-4.1 and a
follow-up-email drafter on gpt-4.1-mini), reconciles their output with a gpt-4.1
orchestrator pass, and renders the result against a strict output contract.
"""

from .config import Settings
from .pipeline import build_pipeline, run_meeting_notes
from .schemas import FinalNotes

__all__ = ["Settings", "FinalNotes", "build_pipeline", "run_meeting_notes"]

__version__ = "1.0.0"

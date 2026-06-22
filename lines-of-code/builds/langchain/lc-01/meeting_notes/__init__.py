"""Multi-agent meeting-notes system built on LangChain.

Public API:
    load_config()             -> AppConfig
    generate_meeting_notes()  -> MeetingNotes

The package wires an orchestrator (gpt-4.1) to two specialist sub-agents that
run in parallel:
    * executive-summary writer   (gpt-4.1)
    * follow-up email drafter     (gpt-4.1-mini)
"""

from .config import AppConfig, ConfigError, ModelConfig, load_config
from .pipeline import MeetingNotes, PipelineError, generate_meeting_notes

__all__ = [
    "AppConfig",
    "ConfigError",
    "ModelConfig",
    "load_config",
    "MeetingNotes",
    "PipelineError",
    "generate_meeting_notes",
]

__version__ = "1.0.0"

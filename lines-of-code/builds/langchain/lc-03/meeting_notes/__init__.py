"""Multi-agent meeting-notes system built on LangChain.

An orchestrator (gpt-4.1) fans a meeting transcript out to two specialist
sub-agents that run in parallel:

  * an executive-summary writer (gpt-4.1)
  * a follow-up-email drafter   (gpt-4.1-mini)

and assembles their outputs into a single response that satisfies a strict
two-section output contract.
"""

from .config import AppConfig, ModelConfig, load_config
from .orchestrator import MeetingNotesOrchestrator
from .exceptions import (
    MeetingNotesError,
    ConfigurationError,
    SubAgentError,
    OrchestrationError,
    ContractValidationError,
)

__all__ = [
    "AppConfig",
    "ModelConfig",
    "load_config",
    "MeetingNotesOrchestrator",
    "MeetingNotesError",
    "ConfigurationError",
    "SubAgentError",
    "OrchestrationError",
    "ContractValidationError",
]

__version__ = "1.0.0"

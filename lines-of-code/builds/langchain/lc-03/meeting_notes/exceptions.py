"""Typed exception hierarchy for the meeting-notes system.

A single root (`MeetingNotesError`) lets callers catch everything from this
package with one `except`, while the specific subclasses let operational code
distinguish configuration problems from runtime LLM/orchestration failures.
"""

from __future__ import annotations


class MeetingNotesError(Exception):
    """Base class for every error raised by this package."""


class ConfigurationError(MeetingNotesError):
    """Raised when required configuration (e.g. OPENAI_API_KEY) is missing
    or invalid."""


class SubAgentError(MeetingNotesError):
    """Raised when one of the specialist sub-agents fails irrecoverably.

    Carries the logical name of the agent that failed so the orchestrator can
    report precisely which leg of the parallel fan-out broke.
    """

    def __init__(self, agent_name: str, message: str) -> None:
        self.agent_name = agent_name
        super().__init__(f"[{agent_name}] {message}")


class OrchestrationError(MeetingNotesError):
    """Raised when the orchestrator itself fails to assemble a result."""


class ContractValidationError(MeetingNotesError):
    """Raised when output cannot be coerced into the required contract.

    Carries the structured list of contract violations for logging.
    """

    def __init__(self, violations: list[str]) -> None:
        self.violations = violations
        super().__init__("Output failed contract validation: " + "; ".join(violations))

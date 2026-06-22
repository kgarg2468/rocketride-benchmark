"""Multi-agent meeting-notes system built on LangChain (LCEL).

An orchestrator (gpt-4.1) fans a transcript out to two specialist sub-agents
that run in parallel -- an executive-summary writer (gpt-4.1) and a follow-up
email drafter (gpt-4.1-mini) -- then assembles a single, contract-compliant
two-section document.
"""
from .config import AppConfig, ModelConfig, load_config
from .pipeline import build_pipeline, run_pipeline

__all__ = [
    "AppConfig",
    "ModelConfig",
    "load_config",
    "build_pipeline",
    "run_pipeline",
]
__version__ = "1.0.0"

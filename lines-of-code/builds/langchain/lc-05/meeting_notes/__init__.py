"""Multi-agent meeting-notes system built on LangChain (LCEL).

Public surface:
    load_config        -> read & validate runtime configuration
    build_pipeline     -> construct the orchestrator Runnable graph
    run_pipeline       -> execute the graph against a transcript
    MeetingNotesError  -> base class for all package errors
"""
from __future__ import annotations

from .config import AppConfig, ModelConfig, load_config
from .errors import ConfigError, MeetingNotesError, PipelineError, ValidationError
from .pipeline import build_pipeline, run_pipeline

__all__ = [
    "AppConfig",
    "ModelConfig",
    "load_config",
    "build_pipeline",
    "run_pipeline",
    "MeetingNotesError",
    "ConfigError",
    "PipelineError",
    "ValidationError",
]

__version__ = "1.0.0"

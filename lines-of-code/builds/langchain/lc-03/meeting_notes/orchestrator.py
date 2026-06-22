"""The orchestrator.

End-to-end flow:

1. Fan out the transcript to both sub-agents **in parallel** via
   ``RunnableParallel`` (one ``.invoke`` runs both legs concurrently).
2. Verify both legs produced non-empty content.
3. Hand both outputs to the gpt-4.1 orchestrator synthesis chain, which
   assembles the final contract-formatted response.
4. Validate the result against the output contract; if the LLM drifted,
   fall back to deterministic assembly so the contract is *always* met.

Tracing is injected through a shared ``RunnableConfig`` so every node (parallel
legs and the synthesis call) reports to the same callback handler.
"""

from __future__ import annotations

import logging

from langchain_core.runnables import RunnableConfig, RunnableParallel

from .agents import build_email_agent, build_orchestrator_agent, build_summary_agent
from .config import AppConfig, load_config
from .exceptions import OrchestrationError, SubAgentError
from .tracing import TracingCallbackHandler, setup_logging
from .validation import assemble_deterministic, split_sections, validate_contract

logger = logging.getLogger("meeting_notes")


class MeetingNotesOrchestrator:
    """High-level entry point: transcript in, contract-compliant notes out."""

    def __init__(self, config: AppConfig | None = None) -> None:
        self.config = config or load_config()
        setup_logging(self.config)

        # Build the specialist sub-agents and the synthesis agent once; the
        # Runnables are reusable across many transcripts.
        self._summary_agent = build_summary_agent(self.config)
        self._email_agent = build_email_agent(self.config)
        self._orchestrator_agent = build_orchestrator_agent(self.config)

        # RunnableParallel is the LangChain primitive for concurrent fan-out:
        # invoking it runs both sub-agents on a thread pool at the same time.
        self._fanout = RunnableParallel(
            summary=self._summary_agent,
            email=self._email_agent,
        ).with_config(run_name="parallel_subagents")

        self._tracer = TracingCallbackHandler(logger)

    # ------------------------------------------------------------------ #
    def process_transcript(self, transcript: str) -> str:
        """Run the full pipeline for one transcript and return final text."""

        if not transcript or not transcript.strip():
            raise OrchestrationError("Transcript is empty.")

        config: RunnableConfig = {
            "callbacks": [self._tracer],
            "run_name": "meeting_notes_pipeline",
            # Cap concurrency to the two parallel legs.
            "max_concurrency": 2,
        }

        # 1 + 2. Parallel fan-out to the two specialists.
        logger.info("Dispatching transcript to summary + email sub-agents (parallel)…")
        try:
            parts = self._fanout.invoke({"transcript": transcript}, config=config)
        except Exception as exc:  # noqa: BLE001 - re-wrapped below
            raise SubAgentError("parallel_fanout", str(exc)) from exc

        summary = (parts.get("summary") or "").strip()
        email = (parts.get("email") or "").strip()
        if not summary:
            raise SubAgentError("summary_agent", "produced empty output")
        if not email:
            raise SubAgentError("email_agent", "produced empty output")
        logger.info(
            "Sub-agents complete (summary=%d chars, email=%d chars).",
            len(summary),
            len(email),
        )

        # 3. Orchestrator synthesis (gpt-4.1) assembles the contract response.
        logger.info("Orchestrator synthesising final contract response…")
        try:
            final = self._orchestrator_agent.invoke(
                {"summary": summary, "email": email}, config=config
            ).strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Orchestrator synthesis failed (%s); using deterministic "
                "assembly fallback.",
                exc,
            )
            final = assemble_deterministic(summary, email)

        # 4. Contract validation + deterministic fallback.
        final = self._enforce_contract(final, summary, email)
        logger.info("Pipeline complete; contract satisfied.")
        return final

    # ------------------------------------------------------------------ #
    def _enforce_contract(self, final: str, summary: str, email: str) -> str:
        """Guarantee the output contract, repairing via deterministic assembly."""

        violations = validate_contract(final)
        if not violations:
            return final.strip() + "\n"

        logger.warning(
            "Orchestrator output violated contract (%s); repairing.",
            "; ".join(violations),
        )

        # Prefer the orchestrator's own section text if parseable, else the raw
        # sub-agent outputs.
        parsed_summary, parsed_email = split_sections(final)
        repaired = assemble_deterministic(
            parsed_summary or summary,
            parsed_email or email,
        )

        residual = validate_contract(repaired)
        if residual:
            # Should be unreachable: deterministic assembly is contract-shaped.
            raise OrchestrationError(
                "Failed to produce contract-compliant output: "
                + "; ".join(residual)
            )
        return repaired

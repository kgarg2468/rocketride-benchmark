"""Structured, templated prompts for every agent.

All prompts live here as :class:`ChatPromptTemplate` objects — no prompt strings
are inlined at call sites. Each template separates a stable *system* role
(instructions + hard constraints) from the *human* turn (the variable input),
which keeps the contract auditable and makes prompts independently testable.
"""
from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

# ---------------------------------------------------------------------------
# Sub-agent 1: Executive summary writer (gpt-4.1)
# ---------------------------------------------------------------------------
SUMMARY_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are an executive summary writer for meeting notes.\n"
            "Given a raw meeting transcript, write a tight executive summary.\n\n"
            "Hard constraints:\n"
            "- 3 to 4 sentences total.\n"
            "- Strictly under 100 words.\n"
            "- Focus only on what was DECIDED and what HAPPENS NEXT.\n"
            "- No bullet points, no headers, no preamble, no sign-off.\n"
            "- Output only the summary prose itself.",
        ),
        (
            "human",
            "Meeting transcript:\n\n{transcript}",
        ),
    ]
)

# ---------------------------------------------------------------------------
# Sub-agent 2: Follow-up email drafter (gpt-4.1-mini)
# ---------------------------------------------------------------------------
EMAIL_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You draft concise follow-up emails after meetings.\n"
            "Given a raw meeting transcript, write the BODY of a follow-up email.\n\n"
            "Hard constraints:\n"
            "- Strictly under 200 words.\n"
            "- Open by greeting the attendees by name (infer their names from the "
            "transcript; if explicit attendee names are provided below, use those).\n"
            "- Recap the key decisions.\n"
            "- List action items as a short list, each with an owner and a deadline.\n"
            "- Propose clear next steps.\n"
            "- Plain, professional tone. No marketing language.\n"
            "- Output only the email body (greeting through sign-off). "
            "Do NOT include a subject line and do NOT use markdown headers.",
        ),
        (
            "human",
            "Known attendees (may be blank): {attendees}\n\n"
            "Meeting transcript:\n\n{transcript}",
        ),
    ]
)

# ---------------------------------------------------------------------------
# Orchestrator: gather + edit + format (gpt-4.1)
# ---------------------------------------------------------------------------
# The orchestrator receives the two specialists' drafts and is responsible for
# the final, contract-conformant document. It is an editor, not a rewriter: it
# enforces the length/format constraints and fixes violations but must not
# invent facts that were absent from the drafts.
ORCHESTRATOR_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are the orchestrator and final editor of a meeting-notes system.\n"
            "Two specialists have produced drafts: an executive summary and a "
            "follow-up email. Assemble the final deliverable.\n\n"
            "Output the document in EXACTLY this format, with these exact headers "
            "and nothing before or after:\n\n"
            "## Executive Summary\n\n"
            "<the executive summary>\n\n"
            "## Draft Follow-up Email\n\n"
            "<the follow-up email body>\n\n"
            "Editing rules:\n"
            "- The Executive Summary must be 3-4 sentences and under 100 words.\n"
            "- The Draft Follow-up Email must be under 200 words, greet attendees "
            "by name, recap decisions, list action items with owners and "
            "deadlines, and propose next steps.\n"
            "- Trim or tighten drafts that violate these limits.\n"
            "- Do NOT invent facts that are not present in the drafts.\n"
            "- Use the exact headers shown above (verbatim).",
        ),
        (
            "human",
            "Executive summary draft:\n\n{summary}\n\n"
            "---\n\n"
            "Follow-up email draft:\n\n{email}",
        ),
    ]
)

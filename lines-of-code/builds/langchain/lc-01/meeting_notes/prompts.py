"""Structured, templated prompts.

Every prompt is a ``ChatPromptTemplate`` with an explicit system role and a
human message carrying the variable payload. Prompts live here — never inlined
at the call site — so they can be reviewed and tuned independently of logic.
"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

# Canonical contract markers. Used by the orchestrator prompt AND by the
# deterministic enforcement step, so there is a single source of truth.
EXEC_SUMMARY_HEADER = "## Executive Summary"
EMAIL_HEADER = "## Draft Follow-up Email"


# --------------------------------------------------------------------------- #
# Sub-agent 1: executive summary writer (gpt-4.1)
# --------------------------------------------------------------------------- #
SUMMARY_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are an executive-summary specialist. Given a raw meeting "
            "transcript you produce a crisp summary for busy leadership.\n"
            "Rules:\n"
            "- 3 to 4 sentences, STRICTLY under 100 words.\n"
            "- Focus on what was DECIDED and what happens NEXT.\n"
            "- No preamble, no bullet points, no header — return the summary "
            "prose ONLY.\n"
            "- Neutral, factual, professional tone.",
        ),
        ("human", "Meeting transcript:\n\n{transcript}"),
    ]
)


# --------------------------------------------------------------------------- #
# Sub-agent 2: follow-up email drafter (gpt-4.1-mini)
# --------------------------------------------------------------------------- #
EMAIL_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a follow-up email drafter. Given a raw meeting transcript "
            "you write the BODY of a recap email.\n"
            "Rules:\n"
            "- STRICTLY under 200 words.\n"
            "- Greet attendees by name in the opening line.\n"
            "- Recap the key decisions.\n"
            "- List action items, each with an owner and a deadline.\n"
            "- Propose clear next steps / a next meeting.\n"
            "- Plain, professional tone. Return the email body ONLY "
            "(no subject line, no markdown header).",
        ),
        ("human", "Meeting transcript:\n\n{transcript}"),
    ]
)


# --------------------------------------------------------------------------- #
# Orchestrator: assembles both sections (gpt-4.1)
# --------------------------------------------------------------------------- #
ORCHESTRATOR_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are the orchestrator that assembles a final meeting-notes "
            "document from two specialist outputs. You MUST return the document "
            "in EXACTLY this format and nothing else:\n\n"
            f"{EXEC_SUMMARY_HEADER}\n\n"
            "<the executive summary>\n\n"
            f"{EMAIL_HEADER}\n\n"
            "<the draft follow-up email body>\n\n"
            "Do NOT invent content. Use the provided summary and email "
            "verbatim, fixing only obvious formatting/whitespace. Ensure the "
            "two sections are mutually consistent (same decisions, owners, "
            "dates). Keep the summary under 100 words and the email under 200 "
            "words. Output the two sections with their headers and nothing "
            "before or after.",
        ),
        (
            "human",
            "EXECUTIVE SUMMARY (from the summary specialist):\n{executive_summary}\n\n"
            "DRAFT EMAIL BODY (from the email specialist):\n{draft_email}",
        ),
    ]
)

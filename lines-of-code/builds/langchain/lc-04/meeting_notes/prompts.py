"""Structured, templated prompts for every agent.

Prompts are defined declaratively as ``ChatPromptTemplate`` objects (system +
human messages with named input variables) rather than f-strings inlined into
call sites. This keeps prompt engineering in one reviewable place and lets the
chains stay logic-only.
"""
from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

# Shared contract constants so prompts and the validator never drift apart.
SUMMARY_HEADER = "## Executive Summary"
EMAIL_HEADER = "## Draft Follow-up Email"
SUMMARY_WORD_LIMIT = 100
EMAIL_WORD_LIMIT = 200

# --------------------------------------------------------------------------- #
# Sub-agent 1: executive summary writer (gpt-4.1)
# Produces ONLY the body text -- the orchestrator adds the section header.
# --------------------------------------------------------------------------- #
SUMMARIZER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are an executive-summary specialist for a busy leadership team. "
            "Given a raw meeting transcript, write a crisp executive summary.\n\n"
            "Rules (follow exactly):\n"
            "- 3 to 4 sentences, STRICTLY under {word_limit} words.\n"
            "- Focus on what was DECIDED and what happens NEXT. Omit chit-chat.\n"
            "- Neutral, factual, executive tone. No bullet points, no headers, "
            "no preamble such as 'Here is the summary'.\n"
            "- Output the summary body text only.",
        ),
        ("human", "Meeting transcript:\n\n{transcript}"),
    ]
).partial(word_limit=str(SUMMARY_WORD_LIMIT))

# --------------------------------------------------------------------------- #
# Sub-agent 2: follow-up email drafter (gpt-4.1-mini)
# Produces ONLY the email body -- the orchestrator adds the section header.
# --------------------------------------------------------------------------- #
EMAILER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You draft concise, professional follow-up emails after meetings.\n\n"
            "Rules (follow exactly):\n"
            "- STRICTLY under {word_limit} words.\n"
            "- Open by greeting the attendees by name (extract names from the "
            "transcript).\n"
            "- Recap the key decisions.\n"
            "- List action items as 'Owner: task by deadline'.\n"
            "- Propose the next step(s).\n"
            "- Plain, professional tone. No marketing language. No subject line "
            "and no section header -- output the email body only, including a "
            "sign-off.",
        ),
        ("human", "Meeting transcript:\n\n{transcript}"),
    ]
).partial(word_limit=str(EMAIL_WORD_LIMIT))

# --------------------------------------------------------------------------- #
# Orchestrator: collects both sub-agent outputs and assembles the final
# contract-compliant document (gpt-4.1).
# --------------------------------------------------------------------------- #
ORCHESTRATOR_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are the orchestrator. Two specialists have produced a meeting "
            "summary and a follow-up email. Assemble them into ONE document in "
            "EXACTLY this format and nothing else:\n\n"
            "{summary_header}\n\n"
            "<the summary body>\n\n"
            "{email_header}\n\n"
            "<the email body>\n\n"
            "Rules:\n"
            "- Preserve the specialists' content faithfully; fix only obvious "
            "typos or redundancy. Do not invent facts.\n"
            "- Keep the summary under {summary_limit} words and the email under "
            "{email_limit} words.\n"
            "- Output only the two sections with their exact headers. No code "
            "fences, no extra commentary.",
        ),
        (
            "human",
            "EXECUTIVE SUMMARY (from specialist 1):\n{summary}\n\n"
            "FOLLOW-UP EMAIL (from specialist 2):\n{email}",
        ),
    ]
).partial(
    summary_header=SUMMARY_HEADER,
    email_header=EMAIL_HEADER,
    summary_limit=str(SUMMARY_WORD_LIMIT),
    email_limit=str(EMAIL_WORD_LIMIT),
)

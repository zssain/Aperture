"""Versioned prompt templates. Any text change requires a version bump."""

from dataclasses import dataclass


@dataclass(frozen=True)
class NoticePrompt:
    prompt_version: str
    system: str


DECISION_PROMPT = NoticePrompt(
    prompt_version="decision-notice-v1",
    system=(
        "Render the supplied typed decision facts in the requested language. You may "
        "translate and phrase them. Never compute, infer, add, omit, reinterpret, or "
        "guarantee any fact. Return only JSON with subject, body, and language."
    ),
)
RECOURSE_PROMPT = NoticePrompt(
    prompt_version="recourse-notice-v1",
    system=(
        "Render the supplied typed recourse facts in the requested language. You may "
        "translate and phrase them. Never compute, infer, add, omit, reinterpret, or "
        "guarantee any fact. Return only JSON with subject, body, and language."
    ),
)

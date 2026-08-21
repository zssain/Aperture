"""Strict validation gate for optional model-rendered notices."""

import re
import unicodedata
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from app.services.notices.context import NoticeContext


class LLMNotice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=20, max_length=4000)
    language: str = Field(min_length=2, max_length=12)


@dataclass(frozen=True)
class NoticeValidation:
    ok: bool
    errors: tuple[str, ...]


_GUARANTEES = (
    "will be approved",
    "guaranteed",
    "approval is assured",
    "स्वीकृति की गारंटी",
    "स्वीकृत किया जाएगा",
    "गारंटीकृत",
)
_APPROVAL = ("approved", "approval granted", "स्वीकृत", "मंजूर")
_INTERNALS = (
    "threshold",
    "rule ",
    "rule_",
    "policy version",
    "model version",
    "pd_decline",
    "cov_high",
    "scorecard cutoff",
    "similarity score",
    "classifier version",
    "vector_knn",
)
_DIGIT_TRANSLATION = str.maketrans("०१२३४५६७८९٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_NUMBER = re.compile(r"(?<!\w)[₹$€£]?\s*\d[\d,.]*(?:%|\s*(?:months?|महीने))?")


def _normal_number(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).translate(_DIGIT_TRANSLATION)
    return re.sub(r"[^0-9.]", "", value.replace(",", ""))


def injected_numerals(context: NoticeContext) -> set[str]:
    values: set[str] = set()

    def collect(value: object) -> None:
        if isinstance(value, bool):
            return
        if isinstance(value, (int, float)):
            raw = str(value)
            values.add(_normal_number(raw))
            if isinstance(value, int) and value % 100 == 0:
                values.add(str(value // 100))
        elif isinstance(value, dict):
            for child in value.values():
                collect(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                collect(child)

    collect(context.model_dump(mode="json"))
    if context.expiry_date:
        values.update(
            {
                str(context.expiry_date.year),
                str(context.expiry_date.month),
                str(context.expiry_date.day),
            }
        )
    return values


def validate_notice(output: LLMNotice, context: NoticeContext) -> NoticeValidation:
    errors: list[str] = []
    text = f"{output.subject}\n{output.body}"
    allowed = injected_numerals(context)
    for match in _NUMBER.findall(text.translate(_DIGIT_TRANSLATION)):
        number = _normal_number(match)
        if number and number not in allowed:
            errors.append(f"invented numeral: {match.strip()}")
    lowered = text.casefold()
    if (context.outcome.startswith("DECLINE") or context.outcome == "APPROVE_STARTER") and any(
        term in lowered for term in _APPROVAL
    ):
        errors.append("approval language is incompatible with the outcome")
    if any(term in lowered for term in _GUARANTEES):
        errors.append("guarantee language is forbidden")
    if output.language != context.language:
        errors.append("output language does not match request")
    if context.language == "hi" and not re.search(r"[\u0900-\u097F]", text):
        errors.append("Hindi output does not contain Hindi script")
    if context.language == "en" and re.search(r"[\u0900-\u097F]", text):
        errors.append("English output contains unexpected script")
    if any(term in lowered for term in _INTERNALS):
        errors.append("policy or model internals are forbidden")
    return NoticeValidation(ok=not errors, errors=tuple(errors))

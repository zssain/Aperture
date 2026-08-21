"""Document provenance checks — tamper indicators for uploaded statements.

Findings are advisory evidence for the manipulation engine (Prompt 08); they never
gate ingestion here. A declared document is always the weakest tier regardless.
"""

from dataclasses import asdict, dataclass
from typing import Any

# Producers that indicate a document was authored/edited rather than issued by a bank.
_EDITOR_PRODUCERS = (
    "word",
    "libreoffice",
    "openoffice",
    "google",
    "photoshop",
    "canva",
    "pages",
    "excel",
    "wkhtmltopdf",
)


@dataclass(frozen=True)
class ProvenanceFinding:
    code: str
    severity: str  # LOW | MEDIUM | HIGH
    detail: str


def _finding_dicts(findings: list[ProvenanceFinding]) -> list[dict[str, Any]]:
    return [asdict(f) for f in findings]


def check_pdf_provenance(pdf_metadata: dict[str, str], is_signed: bool) -> list[dict[str, Any]]:
    """Inspect PDF metadata + signature presence for tamper indicators."""
    findings: list[ProvenanceFinding] = []

    producer = (pdf_metadata.get("/Producer", "") + " " + pdf_metadata.get("/Creator", "")).lower()
    if any(editor in producer for editor in _EDITOR_PRODUCERS):
        findings.append(
            ProvenanceFinding(
                code="EDITOR_PRODUCED",
                severity="HIGH",
                detail=f"Document producer indicates an editor, not a bank: {producer.strip()!r}",
            )
        )

    if not is_signed:
        findings.append(
            ProvenanceFinding(
                code="NO_ISSUER_SIGNATURE",
                severity="MEDIUM",
                detail="No digital signature; issuer authenticity cannot be verified.",
            )
        )

    if not pdf_metadata.get("/Producer") and not pdf_metadata.get("/Creator"):
        findings.append(
            ProvenanceFinding(
                code="MISSING_PRODUCER_METADATA",
                severity="LOW",
                detail="Producer/Creator metadata is absent.",
            )
        )

    return _finding_dicts(findings)


def check_csv_provenance(
    has_balance_column: bool, balance_consistent: bool
) -> list[dict[str, Any]]:
    """A CSV carries no issuer metadata; note the weak provenance and any anomalies."""
    findings: list[ProvenanceFinding] = [
        ProvenanceFinding(
            code="DECLARED_CSV",
            severity="LOW",
            detail="Self-declared CSV with no issuer metadata or signature.",
        )
    ]
    if has_balance_column and not balance_consistent:
        findings.append(
            ProvenanceFinding(
                code="BALANCE_DISCONTINUITY",
                severity="HIGH",
                detail="Running balance does not reconcile with transaction amounts.",
            )
        )
    return _finding_dicts(findings)

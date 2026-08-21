"""D6 - Document provenance. Surfaces tamper indicators from Prompt 04's provenance checks.

Only native-HIGH provenance codes (editor-tool producer, balance discontinuity) become
manipulation findings, emitted at MEDIUM as corroborating evidence. A declared document
merely lacking an issuer signature is normal and must never flag - flagging every
self-declared statement would quietly destroy the inclusion this product exists to deliver.
The finding cites the ledger events the flagged document actually produced.
"""

from app.services.manipulation.base import DetectorResult, DetectorStatus, Finding
from app.services.manipulation.config import get_manipulation_config
from app.services.manipulation.context import ManipulationContext


class _D6DocumentProvenance:
    detector_id = "D6"

    def run(self, context: ManipulationContext) -> DetectorResult:
        cfg = get_manipulation_config(context.config_version)["d6"]
        trigger = str(cfg["trigger_severity"])

        findings: list[Finding] = []
        for source in context.sources:
            if not source.event_ids:
                continue
            for provenance in source.provenance:
                if provenance.severity != trigger:
                    continue
                findings.append(
                    Finding(
                        detector_id=self.detector_id,
                        severity="MEDIUM",
                        statement=(
                            f"{len(source.event_ids)} transactions were sourced from a "
                            f"document flagged '{provenance.code}': {provenance.detail}"
                        ),
                        cited_event_ids=source.event_ids,
                        confidence=0.7,
                        values={
                            "provenance_code": provenance.code,
                            "provenance_severity": provenance.severity,
                            "source_snapshot_id": (
                                str(source.source_snapshot_id)
                                if source.source_snapshot_id
                                else None
                            ),
                            "event_count": len(source.event_ids),
                        },
                    )
                )

        return DetectorResult(self.detector_id, DetectorStatus.OK, tuple(findings))


DETECTOR: _D6DocumentProvenance = _D6DocumentProvenance()

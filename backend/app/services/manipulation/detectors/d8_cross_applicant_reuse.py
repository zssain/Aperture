"""D8 - Cross-applicant reuse. A shared fingerprint across many applications is a ring.

Fires when one counterparty hash or device fingerprint appears across >= 3 applications
within 14 days. The cross-application signals are precomputed and handed in via the
context; at low volume the list is simply empty and this returns no findings without error.
"""

from app.services.manipulation.base import DetectorResult, DetectorStatus, Finding
from app.services.manipulation.config import get_manipulation_config
from app.services.manipulation.context import ManipulationContext


class _D8CrossApplicantReuse:
    detector_id = "D8"

    def run(self, context: ManipulationContext) -> DetectorResult:
        cfg = get_manipulation_config(context.config_version)["d8"]
        min_apps = int(cfg["min_applications"])
        window = int(cfg["window_days"])

        findings: list[Finding] = []
        for signal in context.cross_applicant:
            if signal.application_count < min_apps:
                continue
            if signal.window_days > window:
                continue
            if not signal.event_ids:
                continue
            findings.append(
                Finding(
                    detector_id=self.detector_id,
                    severity="HIGH",
                    statement=(
                        f"A {signal.kind.lower()} fingerprint appears across "
                        f"{signal.application_count} applications within "
                        f"{signal.window_days} days."
                    ),
                    cited_event_ids=signal.event_ids,
                    confidence=round(min(1.0, signal.application_count / (min_apps * 2)), 4),
                    values={
                        "fingerprint_hash": signal.fingerprint_hash,
                        "kind": signal.kind,
                        "application_count": signal.application_count,
                        "window_days": signal.window_days,
                    },
                )
            )

        return DetectorResult(self.detector_id, DetectorStatus.OK, tuple(findings))


DETECTOR: _D8CrossApplicantReuse = _D8CrossApplicantReuse()

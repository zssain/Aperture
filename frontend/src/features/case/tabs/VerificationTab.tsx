import { Badge } from "../../../components/ui/Badge";
import { Icon } from "../../../components/ui/Icon";
import { InfoHint } from "../../../components/ui/InfoHint";
import { StatusDot } from "../../../components/ui/StatusDot";
import type { Tone } from "../../../components/ui/tones";
import { FindingCard } from "../FindingCard";
import type { CaseData } from "../useCase";

const BAND_TONE: Record<string, Tone> = {
  CLEAR: "positive",
  ELEVATED: "caution",
  HIGH: "negative",
  UNAVAILABLE: "neutral",
  UNKNOWN: "neutral",
};

const DETECTOR_LABELS: Record<string, string> = {
  D1: "Circular flow",
  D2: "Inflow burst",
  D3: "Counterparty concentration",
  D4: "Round-number salary",
  D5: "Balance arithmetic",
  D6: "Document provenance",
  D7: "Account age mismatch",
  D8: "Cross-applicant reuse",
};

interface ManipPayload {
  detector_statuses?: Record<string, string>;
  skipped?: string[];
  insufficient?: string[];
}

type CheckVerdict = "PASS" | "REVIEW" | "NOT_AVAILABLE";

const VERDICT_META: Record<CheckVerdict, { label: string; tone: Tone }> = {
  PASS: { label: "Pass", tone: "positive" },
  REVIEW: { label: "Review", tone: "caution" },
  NOT_AVAILABLE: { label: "Not available", tone: "neutral" },
};

/** Verification tab: a clear success state when nothing was found, the findings expanded
 * to their cited rows, a per-detector check list built ONLY from detectors the payload
 * evidences, a document-provenance panel, and the important distinction that a check
 * which could not run is not the same as clear. */
export function VerificationTab({ data }: { data: CaseData }) {
  const manip = data.assessments.MANIPULATION;
  const payload = (manip?.payload ?? {}) as ManipPayload;
  const skipped = new Set(payload.skipped ?? []);
  const insufficient = new Set(payload.insufficient ?? []);
  const statuses = payload.detector_statuses ?? {};

  const findingsByDetector = new Set(data.manipulation_findings.map((f) => f.detector_id));
  const verification = data.chips.verification;
  const clear = verification === "CLEAR" && data.manipulation_findings.length === 0;

  // Build the check list ONLY from detectors the payload actually reports on — never
  // claim a check ran without evidence.
  const checks = Object.keys(statuses).map((id) => {
    const notRun = skipped.has(id) || insufficient.has(id) || statuses[id] === "UNAVAILABLE";
    const verdict: CheckVerdict = notRun
      ? "NOT_AVAILABLE"
      : findingsByDetector.has(id)
        ? "REVIEW"
        : "PASS";
    const reason = insufficient.has(id)
      ? "insufficient data"
      : skipped.has(id) || statuses[id] === "UNAVAILABLE"
        ? "could not run"
        : null;
    return { id, verdict, reason };
  });

  const declaredDocs = data.sources.filter((s) => s.tier === "DECLARED_DOCUMENT");

  return (
    <div data-testid="case-tab-body" className="space-y-6 case-wide:grid case-wide:grid-cols-2 case-wide:gap-8 case-wide:space-y-0">
      <section aria-label="Findings" className="space-y-3">
        <div className="flex items-center gap-2">
          <StatusDot
            tone={BAND_TONE[verification] ?? "neutral"}
            label={`Verification ${verification}`}
          />
          <InfoHint term="verification_status" />
        </div>

        {clear ? (
          <div className="flex items-start gap-2 rounded border border-positive/40 bg-positive-subtle p-3">
            <span className="mt-0.5 text-positive">
              <Icon name="shield" size={18} />
            </span>
            <p className="text-sm text-ink">
              <span className="font-medium">Clear.</span> No manipulation indicators were
              detected. This does not disable the checks below.
            </p>
          </div>
        ) : data.manipulation_findings.length === 0 ? (
          <p className="text-sm text-muted">
            No manipulation findings were raised. This does not disable the checks below.
          </p>
        ) : (
          <div className="space-y-2">
            {data.manipulation_findings.map((finding, index) => (
              <FindingCard key={`${finding.detector_id}-${index}`} finding={finding} />
            ))}
          </div>
        )}
      </section>

      {checks.length > 0 ? (
        <section aria-label="Detector checks" className="space-y-2">
          <h3 className="eyebrow">Checks</h3>
          <ul className="divide-y divide-border rounded border border-border">
            {checks.map((check) => (
              <li
                key={check.id}
                className="flex items-center justify-between gap-3 px-3 py-2 text-sm"
              >
                <span className="text-ink">{DETECTOR_LABELS[check.id] ?? check.id}</span>
                <span className="flex items-center gap-2">
                  {check.reason ? (
                    <span className="text-xs text-muted">{check.reason}</span>
                  ) : null}
                  <Badge tone={VERDICT_META[check.verdict].tone} glyph>
                    {VERDICT_META[check.verdict].label}
                  </Badge>
                </span>
              </li>
            ))}
          </ul>
          <p className="text-xs text-muted">
            A check that could not run is{" "}
            <span className="font-medium text-caution">not the same as clear</span>.
          </p>
        </section>
      ) : null}

      <section aria-label="Document provenance" className="space-y-2 case-wide:col-span-2">
        <h3 className="eyebrow">Document provenance</h3>
        {declaredDocs.length === 0 ? (
          <p className="text-sm text-muted">No uploaded documents on this case.</p>
        ) : (
          <ul className="divide-y divide-border rounded border border-border">
            {declaredDocs.map((source) => (
              <li key={source.id} className="flex items-center justify-between px-3 py-2 text-sm">
                <span className="text-ink">{source.source_type}</span>
                <span className="text-muted">{source.status}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

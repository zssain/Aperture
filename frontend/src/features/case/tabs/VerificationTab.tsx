import { Badge } from "../../../components/ui/Badge";
import { StatusDot } from "../../../components/ui/StatusDot";
import type { Tone } from "../../../components/ui/tones";
import { FindingCard } from "../FindingCard";
import type { CaseData } from "../useCase";

const BAND_TONE: Record<string, Tone> = {
  CLEAR: "positive",
  ELEVATED: "caution",
  HIGH: "negative",
  UNAVAILABLE: "neutral",
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

/** Verification tab: findings expand inline to their cited rows; a document-provenance panel for
 * uploaded sources; and an explicit list of detectors that could NOT run — insufficient data or
 * unavailable is not the same as clear. */
export function VerificationTab({ data }: { data: CaseData }) {
  const manip = data.assessments.MANIPULATION;
  const payload = (manip?.payload ?? {}) as ManipPayload;
  const skipped = new Set(payload.skipped ?? []);
  const insufficient = new Set(payload.insufficient ?? []);
  const statuses = payload.detector_statuses ?? {};
  const notRun = Object.entries(statuses)
    .filter(([id, status]) => skipped.has(id) || insufficient.has(id) || status === "UNAVAILABLE")
    .map(([id]) => id);

  const declaredDocs = data.sources.filter((s) => s.tier === "DECLARED_DOCUMENT");

  return (
    <div data-testid="case-tab-body" className="space-y-6 case-wide:grid case-wide:grid-cols-2 case-wide:gap-8 case-wide:space-y-0">
      <div className="flex items-center gap-3">
        <StatusDot tone={BAND_TONE[data.chips.verification] ?? "neutral"} label={data.chips.verification} />
        <span className="text-sm text-muted">
          {data.manipulation_findings.length} finding(s)
        </span>
      </div>

      <section aria-label="Findings" className="space-y-2">
        {data.manipulation_findings.length === 0 ? (
          <p className="text-sm text-muted">
            No manipulation findings were raised. This does not disable the checks below.
          </p>
        ) : (
          data.manipulation_findings.map((finding, index) => (
            <FindingCard key={`${finding.detector_id}-${index}`} finding={finding} />
          ))
        )}
      </section>

      <section aria-label="Document provenance" className="space-y-2">
        <h3 className="text-sm font-medium text-ink">Document provenance</h3>
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

      {notRun.length > 0 ? (
        <section aria-label="Checks not completed" className="space-y-2">
          <h3 className="text-sm font-medium text-ink">Checks that could not run</h3>
          <p className="text-sm text-muted">
            These are <span className="font-medium text-caution">not the same as clear</span> — the
            data to run them was missing or unavailable.
          </p>
          <ul className="flex flex-wrap gap-2">
            {notRun.map((id) => (
              <li key={id}>
                <Badge tone="caution">
                  {DETECTOR_LABELS[id] ?? id}: {insufficient.has(id) ? "insufficient data" : "unavailable"}
                </Badge>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

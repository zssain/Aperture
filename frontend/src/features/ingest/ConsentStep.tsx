import { Chip } from "../../components/ui/Chip";
import { Input } from "../../components/ui/Input";
import type { SourceType } from "./useIngest";

interface ConsentStepProps {
  granted: boolean;
  scopes: SourceType[];
  purpose: string;
  expiresOn: string;
  bankName?: string | null;
  disabled?: boolean;
  error?: string;
  onGrantedChange: (granted: boolean) => void;
  onScopeChange: (scope: SourceType, checked: boolean) => void;
  onPurposeChange: (purpose: string) => void;
  onExpiresOnChange: (date: string) => void;
}

const SCOPES: SourceType[] = ["BANK", "UPI"];
const SOURCE_LABELS: Record<SourceType, string> = {
  BANK: "Bank accounts",
  UPI: "UPI accounts",
};

function formatDate(value: string): string {
  const parsed = new Date(`${value}T00:00:00`);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric" });
}

export function ConsentStep({
  granted,
  scopes,
  purpose,
  expiresOn,
  bankName = null,
  disabled = false,
  error,
  onGrantedChange,
  onScopeChange,
  onPurposeChange,
  onExpiresOnChange,
}: ConsentStepProps) {
  return (
    <section aria-labelledby="consent-heading" className="rounded border border-border bg-surface p-5">
      <div className="mb-4">
        <p className="eyebrow">Step 4 · Consent</p>
        <h2 id="consent-heading" className="text-heading font-semibold text-ink">
          Applicant authorisation
        </h2>
        {bankName ? (
          <p className="mt-1 text-sm text-muted">
            The applicant is asked to approve sharing from {bankName} through the Account
            Aggregator sandbox.
          </p>
        ) : null}
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-1">
          <label htmlFor="consent-purpose" className="block text-sm font-medium text-ink">
            Purpose
          </label>
          <Input
            id="consent-purpose"
            value={purpose}
            disabled={disabled}
            onChange={(event) => onPurposeChange(event.target.value)}
          />
        </div>
        <div className="space-y-1">
          <label htmlFor="consent-expiry" className="block text-sm font-medium text-ink">
            Access valid until
          </label>
          <Input
            id="consent-expiry"
            type="date"
            value={expiresOn}
            disabled={disabled}
            onChange={(event) => onExpiresOnChange(event.target.value)}
          />
        </div>
      </div>
      <fieldset className="mt-4 space-y-2">
        <legend className="text-sm font-medium text-ink">Accounts the applicant permits us to access</legend>
        {SCOPES.map((scope) => (
          <label key={scope} className="flex items-center gap-2 text-sm text-ink">
            <input
              type="checkbox"
              checked={scopes.includes(scope)}
              disabled={disabled}
              onChange={(event) => onScopeChange(scope, event.target.checked)}
            />
            {SOURCE_LABELS[scope]}
          </label>
        ))}
      </fieldset>

      {/* Mirror of the consent artefact that will be recorded — what the applicant
          agrees to is exactly what the system stores and hashes. */}
      <div className="mt-4 rounded border border-border bg-sunken p-4">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-ink">What the applicant will see</h3>
          <Chip tone="neutral">Recorded verbatim</Chip>
        </div>
        <dl className="mt-3 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">Purpose</dt>
            <dd className="mt-0.5 text-ink">{purpose.trim() || "—"}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">Valid until</dt>
            <dd className="mt-0.5 text-ink">{expiresOn ? formatDate(expiresOn) : "—"}</dd>
          </div>
          <div className="sm:col-span-2">
            <dt className="text-xs uppercase tracking-wide text-muted">Shared with Aperture</dt>
            <dd className="mt-1 flex flex-wrap gap-1.5">
              {scopes.length > 0 ? (
                scopes.map((scope) => (
                  <Chip key={scope} tone="neutral">
                    {SOURCE_LABELS[scope]}
                    {bankName && scope === "BANK" ? ` · ${bankName}` : ""}
                  </Chip>
                ))
              ) : (
                <span className="text-muted">No accounts selected yet</span>
              )}
            </dd>
          </div>
        </dl>
        <p className="mt-3 text-xs text-muted">
          A cryptographic hash of these exact terms is stored with the consent record, and every
          piece of evidence links back to it. Revocation stops future collection immediately;
          existing decision records remain auditable.
        </p>
      </div>

      <label className="mt-4 flex items-start gap-2 font-medium text-ink">
        <input
          type="checkbox"
          checked={granted}
          disabled={disabled}
          aria-describedby={error ? "consent-error" : undefined}
          onChange={(event) => onGrantedChange(event.target.checked)}
        />
        <span>I confirm the applicant explicitly grants this consent.</span>
      </label>
      {error ? (
        <p id="consent-error" className="mt-1 text-sm text-negative">
          {error}
        </p>
      ) : null}
      <p className="mt-2 text-xs text-muted">No scope or consent is selected by default.</p>
    </section>
  );
}

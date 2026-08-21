import { Input } from "../../components/ui/Input";
import type { SourceType } from "./useIngest";

interface ConsentStepProps {
  granted: boolean;
  scopes: SourceType[];
  purpose: string;
  expiresOn: string;
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

export function ConsentStep({
  granted,
  scopes,
  purpose,
  expiresOn,
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
        <p className="eyebrow">Step 3 · Consent</p>
        <h2 id="consent-heading" className="text-heading font-semibold text-ink">
          Applicant authorisation
        </h2>
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
      <div className="mt-4 rounded border border-border bg-sunken p-3 text-sm text-muted">
        We access only the selected financial history to assess this credit request until the date
        above. The applicant may revoke consent at any time; revocation stops future collection.
        Existing decision records remain auditable.
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

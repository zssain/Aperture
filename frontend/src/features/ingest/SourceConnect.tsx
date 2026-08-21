export type EvidencePath = "connect" | "upload";

interface SourceConnectProps {
  path: EvidencePath | null;
  disabled?: boolean;
  onChange: (path: EvidencePath) => void;
}

export function SourceConnect({ path, disabled = false, onChange }: SourceConnectProps) {
  return (
    <section aria-labelledby="evidence-heading" className="rounded border border-border bg-surface p-5">
      <div className="mb-4">
        <p className="text-xs font-medium uppercase text-muted">2. Evidence source</p>
        <h2 id="evidence-heading" className="text-heading font-semibold text-ink">
          Choose how evidence is provided
        </h2>
        <p className="mt-1 text-sm text-muted">
          The verification method affects evidence coverage. This difference applies before any
          assessment runs.
        </p>
      </div>
      <fieldset className="grid gap-3 md:grid-cols-2">
        <legend className="sr-only">Evidence source</legend>
        <label className="flex cursor-pointer gap-3 rounded border border-border-strong p-4">
          <input
            type="radio"
            name="evidence-path"
            value="connect"
            checked={path === "connect"}
            disabled={disabled}
            onChange={() => onChange("connect")}
          />
          <span>
            <span className="block font-medium text-ink">Connect financial accounts</span>
            <span className="mt-1 block text-sm font-medium text-positive">
              Verified · recommended · highest evidence weight
            </span>
            <span className="mt-1 block text-sm text-muted">
              Pulls consented transactions from the simulated Account Aggregator.
            </span>
          </span>
        </label>
        <label className="flex cursor-pointer gap-3 rounded border border-border-strong p-4">
          <input
            type="radio"
            name="evidence-path"
            value="upload"
            checked={path === "upload"}
            disabled={disabled}
            onChange={() => onChange("upload")}
          />
          <span>
            <span className="block font-medium text-ink">Upload statement</span>
            <span className="mt-1 block text-sm font-medium text-caution">
              Accepted at lower evidence weight
            </span>
            <span className="mt-1 block text-sm text-muted">
              CSV or PDF statements are declared documents and receive less evidential weight.
            </span>
          </span>
        </label>
      </fieldset>
    </section>
  );
}

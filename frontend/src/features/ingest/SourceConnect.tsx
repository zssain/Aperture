import { Icon, type IconName } from "../../components/ui/Icon";
import { cn } from "../../lib/cn";

export type EvidencePath = "connect" | "upload";

interface SourceConnectProps {
  path: EvidencePath | null;
  disabled?: boolean;
  onChange: (path: EvidencePath) => void;
}

interface OptionCardProps {
  value: EvidencePath;
  selected: boolean;
  disabled: boolean;
  icon: IconName;
  title: string;
  weight: string;
  weightTone: string;
  description: string;
  onChange: (path: EvidencePath) => void;
}

/** A selectable card backed by a real radio input, so it stays keyboard- and
 * assistive-tech-accessible while reading as a card. The radio is visually hidden but
 * present (and labelled) — the card is its label. */
function OptionCard({
  value,
  selected,
  disabled,
  icon,
  title,
  weight,
  weightTone,
  description,
  onChange,
}: OptionCardProps) {
  return (
    <label
      className={cn(
        "flex cursor-pointer gap-3 rounded border p-4 transition-colors duration-fast",
        selected
          ? "border-accent bg-accent-subtle ring-1 ring-accent"
          : "border-border-strong bg-surface hover:border-accent/60 hover:bg-surface-subtle",
        disabled && "cursor-not-allowed opacity-60",
      )}
    >
      <input
        type="radio"
        name="evidence-path"
        value={value}
        checked={selected}
        disabled={disabled}
        onChange={() => onChange(value)}
        className="sr-only"
      />
      <span
        className={cn(
          "flex h-9 w-9 shrink-0 items-center justify-center rounded",
          selected ? "bg-accent text-surface" : "bg-sunken text-muted",
        )}
      >
        <Icon name={icon} size={18} />
      </span>
      <span className="min-w-0">
        <span className="block font-medium text-ink">{title}</span>
        <span className={cn("mt-1 block text-sm font-medium", weightTone)}>{weight}</span>
        <span className="mt-1 block text-sm text-muted">{description}</span>
      </span>
    </label>
  );
}

export function SourceConnect({ path, disabled = false, onChange }: SourceConnectProps) {
  return (
    <section aria-labelledby="evidence-heading" className="rounded border border-border bg-surface p-5">
      <div className="mb-4">
        <p className="eyebrow">Step 2 · Evidence source</p>
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
        <OptionCard
          value="connect"
          selected={path === "connect"}
          disabled={disabled}
          icon="bank"
          title="Connect financial accounts"
          weight="Verified · recommended · highest evidence weight"
          weightTone="text-positive"
          description="Pulls consented transactions from the simulated Account Aggregator."
          onChange={onChange}
        />
        <OptionCard
          value="upload"
          selected={path === "upload"}
          disabled={disabled}
          icon="upload"
          title="Upload statement"
          weight="Accepted at lower evidence weight"
          weightTone="text-caution"
          description="CSV or PDF statements are declared documents and receive less evidential weight."
          onChange={onChange}
        />
      </fieldset>
    </section>
  );
}

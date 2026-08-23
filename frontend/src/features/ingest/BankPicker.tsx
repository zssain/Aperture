import { Chip } from "../../components/ui/Chip";
import { cn } from "../../lib/cn";

export interface DemoBank {
  id: string;
  name: string;
  initials: string;
  accent: string;
}

/** Sandbox institutions for the simulated Account Aggregator. The picker is honest
 * theatre: whichever bank is chosen, the same consented sandbox corpus is fetched —
 * but the journey (pick bank → consent → fetch) mirrors a real AA redirect flow. */
export const DEMO_BANKS: DemoBank[] = [
  { id: "hdfc", name: "HDFC Bank", initials: "HD", accent: "bg-[#004c8f]" },
  { id: "sbi", name: "State Bank of India", initials: "SB", accent: "bg-[#22409a]" },
  { id: "icici", name: "ICICI Bank", initials: "IC", accent: "bg-[#b02a30]" },
  { id: "axis", name: "Axis Bank", initials: "AX", accent: "bg-[#97144d]" },
  { id: "kotak", name: "Kotak Mahindra", initials: "KM", accent: "bg-[#ed1c24]" },
  { id: "pnb", name: "Punjab National Bank", initials: "PN", accent: "bg-[#a20e37]" },
  { id: "canara", name: "Canara Bank", initials: "CA", accent: "bg-[#0f9647]" },
  { id: "federal", name: "Federal Bank", initials: "FB", accent: "bg-[#f7a800]" },
];

interface BankPickerProps {
  selected: string | null;
  disabled?: boolean;
  onChange: (bankId: string) => void;
}

export function BankPicker({ selected, disabled = false, onChange }: BankPickerProps) {
  return (
    <section aria-labelledby="bank-heading" className="rounded border border-border bg-surface p-5">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div>
          <p className="eyebrow">Step 3 · Select bank</p>
          <h2 id="bank-heading" className="text-heading font-semibold text-ink">
            Where does the applicant bank?
          </h2>
          <p className="mt-1 text-sm text-muted">
            Fetched through the Account Aggregator framework after consent — statements are
            never uploaded by hand on this path.
          </p>
        </div>
        <Chip tone="neutral" className="ml-auto">
          Sandbox
        </Chip>
      </div>
      <fieldset className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
        <legend className="sr-only">Bank</legend>
        {DEMO_BANKS.map((bank) => {
          const active = selected === bank.id;
          return (
            <label
              key={bank.id}
              className={cn(
                "flex cursor-pointer items-center gap-2.5 rounded border p-3 transition-colors duration-fast",
                active
                  ? "border-accent bg-accent-subtle ring-1 ring-accent"
                  : "border-border-strong bg-surface hover:border-accent/60 hover:bg-surface-subtle",
                disabled && "cursor-not-allowed opacity-60",
              )}
            >
              <input
                type="radio"
                name="demo-bank"
                value={bank.id}
                aria-label={bank.name}
                checked={active}
                disabled={disabled}
                onChange={() => onChange(bank.id)}
                className="sr-only"
              />
              <span
                aria-hidden="true"
                className={cn(
                  "flex h-8 w-8 shrink-0 items-center justify-center rounded text-xs font-semibold text-white",
                  bank.accent,
                )}
              >
                {bank.initials}
              </span>
              <span className="min-w-0 truncate text-sm font-medium text-ink">{bank.name}</span>
            </label>
          );
        })}
      </fieldset>
    </section>
  );
}

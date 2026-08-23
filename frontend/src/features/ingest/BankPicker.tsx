import { Chip } from "../../components/ui/Chip";
import { cn } from "../../lib/cn";

export interface DemoBank {
  id: string;
  name: string;
  logo: string;
}

/** Sandbox institutions for the simulated Account Aggregator. The picker is honest
 * theatre: whichever bank is chosen, the same consented sandbox corpus is fetched —
 * but the journey (pick bank → consent → fetch) mirrors a real AA redirect flow. */
export const DEMO_BANKS: DemoBank[] = [
  { id: "hdfc", name: "HDFC Bank", logo: "/brand/banks/hdfc.svg" },
  { id: "sbi", name: "State Bank of India", logo: "/brand/banks/sbi.svg" },
  { id: "icici", name: "ICICI Bank", logo: "/brand/banks/icici.svg" },
  { id: "axis", name: "Axis Bank", logo: "/brand/banks/axis.svg" },
  { id: "yes", name: "Yes Bank", logo: "/brand/banks/yes.svg" },
  { id: "pnb", name: "Punjab National Bank", logo: "/brand/banks/pnb.svg" },
  { id: "canara", name: "Canara Bank", logo: "/brand/banks/canara.svg" },
  { id: "federal", name: "Federal Bank", logo: "/brand/banks/federal.svg" },
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
      <fieldset className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        <legend className="sr-only">Bank</legend>
        {DEMO_BANKS.map((bank) => {
          const active = selected === bank.id;
          return (
            <label
              key={bank.id}
              title={bank.name}
              className={cn(
                "flex h-[72px] cursor-pointer items-center justify-center rounded border bg-white p-3 transition-colors duration-fast",
                active
                  ? "border-accent ring-2 ring-accent"
                  : "border-border-strong hover:border-accent/60",
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
              <img
                src={bank.logo}
                alt={bank.name}
                className="max-h-9 max-w-full object-contain"
                loading="lazy"
              />
            </label>
          );
        })}
      </fieldset>
    </section>
  );
}

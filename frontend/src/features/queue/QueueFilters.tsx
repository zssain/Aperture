import { useState } from "react";

import { Button } from "../../components/ui/Button";
import { Chip } from "../../components/ui/Chip";
import { Icon } from "../../components/ui/Icon";
import { IconButton } from "../../components/ui/Button";
import { Input } from "../../components/ui/Input";
import { Select } from "../../components/ui/Select";
import { cn } from "../../lib/cn";
import { EMPTY_FILTERS, filtersActive, type QueueFilterState } from "./useQueue";

export interface QueueFiltersProps {
  filters: QueueFilterState;
  onChange: (filters: QueueFilterState) => void;
  /** e.g. "12 results" — shown inline at the end of the toolbar. */
  resultLabel?: string;
}

/** The five numeric bounds that live behind the Ranges disclosure. */
const RANGE_KEYS: (keyof QueueFilterState)[] = [
  "coverageMin",
  "coverageMax",
  "amountMin",
  "amountMax",
  "waitingGt",
];

interface AppliedChip {
  key: keyof QueueFilterState;
  label: string;
}

function appliedChips(filters: QueueFilterState): AppliedChip[] {
  const chips: AppliedChip[] = [];
  if (filters.q.trim()) chips.push({ key: "q", label: `Search: ${filters.q.trim()}` });
  if (filters.band) chips.push({ key: "band", label: `Verification: ${filters.band}` });
  if (filters.coverageMin) chips.push({ key: "coverageMin", label: `Coverage ≥ ${filters.coverageMin}` });
  if (filters.coverageMax) chips.push({ key: "coverageMax", label: `Coverage ≤ ${filters.coverageMax}` });
  if (filters.amountMin) chips.push({ key: "amountMin", label: `Amount ≥ ₹${filters.amountMin}` });
  if (filters.amountMax) chips.push({ key: "amountMax", label: `Amount ≤ ₹${filters.amountMax}` });
  if (filters.waitingGt) chips.push({ key: "waitingGt", label: `Waiting > ${filters.waitingGt}h` });
  return chips;
}

/** The filter bar. Every change is pushed up so the parent can mirror it to the URL; no
 * client-side filtering happens here — the server does the filtering. */
export function QueueFilters({ filters, onChange, resultLabel }: QueueFiltersProps) {
  function set<K extends keyof QueueFilterState>(key: K, value: string): void {
    onChange({ ...filters, [key]: value });
  }
  function clear(key: keyof QueueFilterState): void {
    onChange({ ...filters, [key]: "" });
  }

  // Auto-expand Ranges whenever a range filter is present (e.g. a pasted URL), and
  // let the analyst also open it manually.
  const rangeFilled = RANGE_KEYS.some((key) => filters[key].trim() !== "");
  const [manualOpen, setManualOpen] = useState(false);
  const rangesOpen = manualOpen || rangeFilled;

  const chips = appliedChips(filters);
  const active = filtersActive(filters);

  return (
    <div className="rounded border border-border bg-surface">
      <div className="flex flex-wrap items-center gap-2 p-2">
        {/* Single labelling mechanism per control (aria-label only) — a wrapping
            <label> plus aria-label makes getByLabelText match twice. */}
        <div className="relative">
          <Icon
            name="search"
            size={16}
            className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted"
          />
          <Input
            type="search"
            aria-label="Search"
            className="h-9 w-56 pl-8"
            placeholder="Applicant or ID"
            value={filters.q}
            onChange={(event) => set("q", event.target.value)}
          />
        </div>

        <Select
          aria-label="Verification"
          className="h-9 w-36"
          value={filters.band}
          onChange={(event) => set("band", event.target.value)}
        >
          <option value="">Any verification</option>
          <option value="CLEAR">Clear</option>
          <option value="ELEVATED">Elevated</option>
          <option value="HIGH">High</option>
        </Select>

        <Button
          variant={rangesOpen ? "secondary" : "ghost"}
          size="sm"
          icon="filter"
          aria-expanded={rangesOpen}
          onClick={() => setManualOpen((open) => !open)}
        >
          Ranges
          <Icon name={rangesOpen ? "chevron-up" : "chevron-down"} size={14} />
        </Button>

        <div className="ml-auto flex items-center gap-3">
          {resultLabel ? (
            <span className="text-sm tabular-nums text-muted">{resultLabel}</span>
          ) : null}
          {active ? (
            <Button variant="ghost" size="sm" onClick={() => onChange(EMPTY_FILTERS)}>
              Clear all
            </Button>
          ) : null}
        </div>
      </div>

      <div
        className={cn(
          "flex flex-wrap items-end gap-4 border-t border-border px-2 pb-3 pt-2",
          rangesOpen ? "flex" : "hidden",
        )}
      >
        <fieldset className="flex flex-col gap-1 text-xs text-muted">
          <legend className="mb-1 eyebrow">Coverage</legend>
          <div className="flex items-center gap-2">
            <Input
              type="number"
              aria-label="Coverage minimum"
              className="h-9 w-20"
              placeholder="min"
              value={filters.coverageMin}
              onChange={(event) => set("coverageMin", event.target.value)}
            />
            <span aria-hidden="true">–</span>
            <Input
              type="number"
              aria-label="Coverage maximum"
              className="h-9 w-20"
              placeholder="max"
              value={filters.coverageMax}
              onChange={(event) => set("coverageMax", event.target.value)}
            />
          </div>
        </fieldset>

        <fieldset className="flex flex-col gap-1 text-xs text-muted">
          <legend className="mb-1 eyebrow">Amount (₹)</legend>
          <div className="flex items-center gap-2">
            <Input
              type="number"
              aria-label="Amount minimum"
              className="h-9 w-24"
              placeholder="min"
              value={filters.amountMin}
              onChange={(event) => set("amountMin", event.target.value)}
            />
            <span aria-hidden="true">–</span>
            <Input
              type="number"
              aria-label="Amount maximum"
              className="h-9 w-24"
              placeholder="max"
              value={filters.amountMax}
              onChange={(event) => set("amountMax", event.target.value)}
            />
          </div>
        </fieldset>

        <label className="flex flex-col gap-1 text-xs text-muted">
          <span className="mb-1 eyebrow">Waiting over (h)</span>
          <Input
            type="number"
            className="h-9 w-24"
            placeholder="hours"
            value={filters.waitingGt}
            onChange={(event) => set("waitingGt", event.target.value)}
          />
        </label>
      </div>

      {chips.length > 0 ? (
        <div className="flex flex-wrap items-center gap-2 border-t border-border px-2 py-2">
          {chips.map((chip) => (
            <span key={chip.key} className="inline-flex items-center">
              <Chip tone="accent" className="gap-1">
                {chip.label}
                <IconButton
                  icon="close"
                  size="sm"
                  variant="ghost"
                  label={`Remove filter ${chip.label}`}
                  className="h-4 w-4 border-0 text-accent hover:bg-transparent hover:opacity-70"
                  onClick={() => clear(chip.key)}
                />
              </Chip>
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

import { Button } from "../../components/ui/Button";
import { Input } from "../../components/ui/Input";
import { Select } from "../../components/ui/Select";
import { EMPTY_FILTERS, filtersActive, type QueueFilterState } from "./useQueue";

export interface QueueFiltersProps {
  filters: QueueFilterState;
  onChange: (filters: QueueFilterState) => void;
}

/** The filter bar. Every change is pushed up so the parent can mirror it to the URL; no
 * client-side filtering happens here — the server does the filtering. */
export function QueueFilters({ filters, onChange }: QueueFiltersProps) {
  function set<K extends keyof QueueFilterState>(key: K, value: string): void {
    onChange({ ...filters, [key]: value });
  }

  return (
    <div className="flex flex-wrap items-end gap-3">
      <label className="flex flex-col gap-1 text-xs text-muted">
        Search
        <Input
          type="search"
          className="w-56"
          placeholder="Applicant or ID"
          value={filters.q}
          onChange={(event) => set("q", event.target.value)}
        />
      </label>

      <label className="flex flex-col gap-1 text-xs text-muted">
        Verification
        <Select
          className="w-40"
          value={filters.band}
          onChange={(event) => set("band", event.target.value)}
        >
          <option value="">Any</option>
          <option value="CLEAR">Clear</option>
          <option value="ELEVATED">Elevated</option>
          <option value="HIGH">High</option>
        </Select>
      </label>

      <fieldset className="flex flex-col gap-1 text-xs text-muted">
        <legend className="mb-1">Coverage</legend>
        <div className="flex items-center gap-2">
          <Input
            type="number"
            aria-label="Coverage minimum"
            className="w-20"
            placeholder="min"
            value={filters.coverageMin}
            onChange={(event) => set("coverageMin", event.target.value)}
          />
          <span aria-hidden="true">–</span>
          <Input
            type="number"
            aria-label="Coverage maximum"
            className="w-20"
            placeholder="max"
            value={filters.coverageMax}
            onChange={(event) => set("coverageMax", event.target.value)}
          />
        </div>
      </fieldset>

      <fieldset className="flex flex-col gap-1 text-xs text-muted">
        <legend className="mb-1">Amount (₹)</legend>
        <div className="flex items-center gap-2">
          <Input
            type="number"
            aria-label="Amount minimum"
            className="w-24"
            placeholder="min"
            value={filters.amountMin}
            onChange={(event) => set("amountMin", event.target.value)}
          />
          <span aria-hidden="true">–</span>
          <Input
            type="number"
            aria-label="Amount maximum"
            className="w-24"
            placeholder="max"
            value={filters.amountMax}
            onChange={(event) => set("amountMax", event.target.value)}
          />
        </div>
      </fieldset>

      <label className="flex flex-col gap-1 text-xs text-muted">
        Waiting over (h)
        <Input
          type="number"
          className="w-24"
          placeholder="hours"
          value={filters.waitingGt}
          onChange={(event) => set("waitingGt", event.target.value)}
        />
      </label>

      {filtersActive(filters) ? (
        <Button variant="ghost" size="sm" onClick={() => onChange(EMPTY_FILTERS)}>
          Clear filters
        </Button>
      ) : null}
    </div>
  );
}

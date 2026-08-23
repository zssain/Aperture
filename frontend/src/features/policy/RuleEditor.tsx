import { Input } from "../../components/ui/Input";
import type { PolicyRules } from "./usePolicy";

const NUMERIC_FIELDS: Array<[keyof PolicyRules, string, number]> = [
  ["min_coverage", "Minimum coverage", 1], ["cov_mid", "Mid coverage", 1],
  ["cov_high", "High coverage", 1], ["pd_enhanced", "Enhanced PD", .01],
  ["pd_standard", "Standard PD", .01], ["pd_decline_threshold", "Decline PD", .01],
  ["mandatory_review_ceiling_paise", "Mandatory review ceiling (paise)", 100],
  ["exploration_margin", "Exploration margin", .01], ["exploration_budget", "Exploration budget", .01],
];

function relatedError(field: string, errors: string[]): string | undefined {
  return errors.find((error) => {
    const firstMention = NUMERIC_FIELDS.find(([candidate]) =>
      error.toLowerCase().includes(String(candidate).toLowerCase()),
    );
    return firstMention?.[0] === field;
  });
}

export function RuleEditor({ rules, live, errors, onChange, readOnly = false }: { rules: PolicyRules; live?: PolicyRules; errors: string[]; onChange: (rules: PolicyRules, field: string) => void; readOnly?: boolean }) {
  return <div className="space-y-6 p-5">
    <div className="grid grid-cols-2 gap-4">{NUMERIC_FIELDS.map(([field, label, step]) => {
      const value = rules[field] as number; const changed = !readOnly && live?.[field] !== value; const error = readOnly ? undefined : relatedError(field, errors);
      return <label className="text-sm" key={field}><span className="mb-1 flex gap-2">{label}{changed ? <span className="text-caution">changed</span> : null}</span>
        {changed ? <del className="block text-xs text-muted">Live: {String(live?.[field])}</del> : null}
        <Input autoFocus={Boolean(error)} type="number" step={step} value={value} disabled={readOnly} invalid={Boolean(error)} aria-describedby={error ? `${field}-error` : undefined} onChange={(event) => onChange({ ...rules, [field]: Number(event.target.value) }, field)} />
        {error ? <span id={`${field}-error`} className="block text-xs text-negative">{error}</span> : null}
      </label>;
    })}</div>
    <section><h3 className="mb-2 font-semibold">Terms ladder</h3><div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr><th>Band</th><th>Max principal</th><th>Tenor</th><th>Rate (bps)</th></tr></thead><tbody>{Object.entries(rules.terms).map(([band, terms]) => <tr key={band}><th className="text-left">{band}</th>{(["max_principal_paise", "max_tenor_months", "annual_rate_bps"] as const).map((field) => <td key={field}><Input aria-label={`${band} ${field}`} type="number" value={terms[field]} disabled={readOnly} onChange={(event) => onChange({ ...rules, terms: { ...rules.terms, [band]: { ...terms, [field]: Number(event.target.value) } } }, `terms.${band}.${field}`)} /></td>)}</tr>)}</tbody></table></div></section>
  </div>;
}

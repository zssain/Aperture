import { Link } from "react-router-dom";
import { Icon } from "../../components/ui/Icon";
import type { SimulationReport as Report } from "./usePolicy";

const percent = (value?: number) => value === undefined ? "—" : `${(value * 100).toFixed(2)} pp`;
export function SimulationReport({ report }: { report: Report }) {
  if (report.status !== "SUCCEEDED") return <aside aria-live="polite" className="w-full border-l border-border bg-sunken p-5 text-sm text-muted lg:w-[560px]">Simulation {report.status.toLowerCase()}…</aside>;
  return <aside className="w-full space-y-5 overflow-y-auto border-l border-border bg-surface p-5 scrollbar-slim lg:w-[560px]" aria-label="Simulation report">
    <div>
      <p className="eyebrow">Delta report</p>
      <h2 className="text-heading font-semibold text-ink">Simulated impact</h2>
      <div className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-sm">
        <span className="text-muted">Snapshots <span className="ml-1 tabular-nums text-ink">{report.n_snapshots}</span></span>
        <span className="text-muted">Approval delta <span className="ml-1 tabular-nums text-ink">{percent(report.approval_delta)}</span></span>
      </div>
    </div>

    <section><h3 className="mb-1 eyebrow">Cohorts</h3><div className="overflow-hidden rounded border border-border"><table className="w-full text-sm"><thead className="bg-sunken text-eyebrow uppercase text-muted"><tr><th className="px-3 py-1.5 text-left font-semibold">Cohort</th><th className="px-3 py-1.5 text-right font-semibold">n</th><th className="px-3 py-1.5 text-right font-semibold">Approval delta</th></tr></thead><tbody>{Object.entries(report.cohort_deltas ?? {}).map(([name, value]) => <tr key={name} className="border-t border-border"><th className="px-3 py-1.5 text-left font-normal text-ink">{name}</th><td className="px-3 py-1.5 text-right tabular-nums text-ink">{value.n}</td><td className="px-3 py-1.5 text-right tabular-nums text-ink">{percent(value.approval_delta)}</td></tr>)}</tbody></table></div></section>

    <section><h3 className="mb-1 eyebrow">Transitions</h3><div className="overflow-hidden rounded border border-border"><table className="w-full text-sm"><tbody>{Object.entries(report.transition_matrix ?? {}).map(([name, n]) => <tr key={name} className="border-t border-border first:border-t-0"><th className="px-3 py-1.5 text-left font-normal text-ink">{name}</th><td className="px-3 py-1.5 text-right tabular-nums text-ink">{n}</td></tr>)}</tbody></table></div></section>

    <section className="space-y-1 rounded border border-caution bg-caution-subtle p-3">
      <p className="text-sm text-ink">Modelled bad-rate delta: <span className="tabular-nums">{percent(report.modelled_bad_rate_delta)}</span></p>
      <p className="text-sm text-ink">Expected-loss delta: <span className="tabular-nums">{percent(report.expected_loss_delta)}</span></p>
      <p className="mt-2 flex items-start gap-1.5 text-sm font-medium text-caution"><span className="mt-0.5 shrink-0"><Icon name="alert" size={14} /></span>{report.caveats?.[0]}</p>
    </section>

    <section><h3 className="mb-1 eyebrow">Largest flips</h3><ol className="list-decimal space-y-1 pl-5 text-sm">{report.largest_flips?.map((flip) => <li key={flip.application_id}><Link className="text-accent underline decoration-dotted underline-offset-2 hover:decoration-solid" to={`/cases/${flip.application_id}`}>{flip.from} → {flip.to}</Link></li>)}</ol></section>
  </aside>;
}

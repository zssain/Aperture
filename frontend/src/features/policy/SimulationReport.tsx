import { Link } from "react-router-dom";
import type { SimulationReport as Report } from "./usePolicy";

const percent = (value?: number) => value === undefined ? "—" : `${(value * 100).toFixed(2)} pp`;
export function SimulationReport({ report }: { report: Report }) {
  if (report.status !== "SUCCEEDED") return <aside aria-live="polite" className="w-full border-l border-border p-5 lg:w-[560px]">Simulation {report.status.toLowerCase()}…</aside>;
  return <aside className="w-full space-y-5 border-l border-border bg-surface p-5 lg:w-[560px]" aria-label="Simulation report">
    <div><h2 className="text-heading font-semibold">Delta report</h2><p>{report.n_snapshots} snapshots</p><p>Approval delta: {percent(report.approval_delta)}</p></div>
    <section><h3 className="font-semibold">Cohorts</h3><table className="w-full text-sm"><thead><tr><th>Cohort</th><th>n</th><th>Approval delta</th></tr></thead><tbody>{Object.entries(report.cohort_deltas ?? {}).map(([name, value]) => <tr key={name}><th>{name}</th><td>{value.n}</td><td>{percent(value.approval_delta)}</td></tr>)}</tbody></table></section>
    <section><h3 className="font-semibold">Transitions</h3><table className="w-full text-sm"><tbody>{Object.entries(report.transition_matrix ?? {}).map(([name, n]) => <tr key={name}><th>{name}</th><td>{n}</td></tr>)}</tbody></table></section>
    <section className="rounded border border-caution p-3"><p>Modelled bad-rate delta: {percent(report.modelled_bad_rate_delta)}</p><p>Expected-loss delta: {percent(report.expected_loss_delta)}</p><p className="mt-2 text-sm font-medium text-caution">{report.caveats?.[0]}</p></section>
    <section><h3 className="font-semibold">Largest flips</h3><ol className="list-decimal pl-5">{report.largest_flips?.map((flip) => <li key={flip.application_id}><Link className="text-accent underline" to={`/cases/${flip.application_id}`}>{flip.from} → {flip.to}</Link></li>)}</ol></section>
  </aside>;
}

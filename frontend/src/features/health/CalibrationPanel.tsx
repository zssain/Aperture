import { Line, LineChart, ResponsiveContainer } from "recharts";

import { GatedMetric, type MetricResult } from "./GatedMetric";

interface ReliabilityPoint { predicted: number; observed: number; n: number }

export function CalibrationPanel({ data, asOf }: { data: { model_a: { brier: MetricResult; reliability: ReliabilityPoint[] }; model_b: MetricResult; discrimination: { auc: MetricResult; ks: MetricResult } }; asOf: string }) {
  return <section id="calibration" className="rounded border border-border bg-surface p-5">
    <h2 className="text-heading font-semibold">Calibration & discrimination</h2><p className="text-xs text-muted">Data as of {asOf}</p>
    <dl className="my-3 grid gap-3 sm:grid-cols-2"><div><dt>Model A Brier score (live)</dt><dd><GatedMetric metric={data.model_a.brier} /></dd></div><div><dt>Model B (challenger)</dt><dd><GatedMetric metric={data.model_b} /></dd></div><div><dt>ROC AUC</dt><dd><GatedMetric metric={data.discrimination.auc} /></dd></div><div><dt>KS statistic</dt><dd><GatedMetric metric={data.discrimination.ks} /></dd></div></dl>
    {data.model_a.reliability.length ? <div role="img" aria-label="Reliability curve: predicted and observed default rates"><ResponsiveContainer width="100%" height={180}><LineChart data={data.model_a.reliability}><Line dataKey="predicted" stroke="#64748B" dot={false} isAnimationActive={false} /><Line dataKey="observed" stroke="#1E4B8F" dot={false} isAnimationActive={false} /></LineChart></ResponsiveContainer></div> : null}
    <details open><summary>Reliability curve data table</summary><div className="overflow-x-auto"><table className="w-full"><thead><tr><th>Predicted</th><th>Observed</th><th>Sample</th></tr></thead><tbody>{data.model_a.reliability.map((row) => <tr key={row.predicted}><td><GatedMetric metric={measured(row.predicted, row.n)} /></td><td><GatedMetric metric={measured(row.observed, row.n)} /></td><td><GatedMetric metric={measured(row.n, row.n)} format={(value) => value.toFixed(0)} /></td></tr>)}</tbody></table></div></details>
  </section>;
}

function measured(value: number, n: number): MetricResult { return { status: "MEASURED", value, ci_low: null, ci_high: null, n, minimum_n: 1, reason: null }; }

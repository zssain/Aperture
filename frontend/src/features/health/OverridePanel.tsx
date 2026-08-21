import { Link } from "react-router-dom";
import { Line, LineChart, ResponsiveContainer } from "recharts";

import { GatedMetric, type MetricResult } from "./GatedMetric";

interface OverrideData { rate: MetricResult; by_reason: Record<string, number>; by_analyst: Record<string, number>; control_chart?: Array<{ period: string; rate: number | null; n: number }>; interpretation: string; policy_studio_url: string }

export function OverridePanel({ data, asOf }: { data: OverrideData; asOf: string }) {
  const chart = data.control_chart ?? [];
  return <section id="overrides" className="rounded border border-border bg-surface p-5">
    <h2 className="text-heading font-semibold">Human overrides</h2><p className="text-xs text-muted">Data as of {asOf}</p>
    <p>Override rate: <GatedMetric metric={data.rate} format={(value) => `${(value * 100).toFixed(1)}%`} /></p>
    <p className="text-sm">{data.interpretation} <Link className="text-accent underline" to={data.policy_studio_url}>Open Policy Studio</Link></p>
    {chart.length ? <div role="img" aria-label="Override-rate control chart"><ResponsiveContainer width="100%" height={180}><LineChart data={chart}><Line dataKey="rate" stroke="#1E4B8F" isAnimationActive={false} /></LineChart></ResponsiveContainer></div> : null}
    <details open><summary>Control chart data table</summary><table className="w-full"><thead><tr><th>Reason</th><th>Overrides</th></tr></thead><tbody>{Object.entries(data.by_reason).map(([reason, n]) => <tr key={reason}><th>{reason}</th><td><GatedMetric metric={measured(n)} format={(value) => value.toFixed(0)} /></td></tr>)}</tbody></table></details>
  </section>;
}

function measured(value: number): MetricResult { return { status: "MEASURED", value, ci_low: null, ci_high: null, n: value, minimum_n: 0, reason: null }; }

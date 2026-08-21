import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatPaise } from "../../lib/format";

export interface CashflowPoint {
  month: string; // e.g. "2026-03"
  inflow_paise: number;
  outflow_paise: number;
}

/** A six-month inflow/outflow timeline. This chart earns its place: irregular income is a
 * *shape* that a table of monthly totals cannot convey. An sr-only table carries the same data
 * for assistive tech, so the shape is a bonus, never the only channel. */
export function CashflowTimeline({ data }: { data: CashflowPoint[] }) {
  if (data.length === 0) {
    return <p className="text-sm text-muted">No cash-flow to chart yet.</p>;
  }
  const rows = data.map((point) => ({
    month: point.month,
    inflow: point.inflow_paise / 100,
    outflow: point.outflow_paise / 100,
  }));

  return (
    <figure
      role="img"
      aria-label="Six-month inflow and outflow timeline"
      className="w-full"
    >
      <div className="h-48 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
            <XAxis dataKey="month" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} width={64} />
            <Tooltip formatter={(value: number) => formatPaise(Math.round(value * 100))} />
            <Line type="monotone" dataKey="inflow" stroke="#16a34a" dot={false} name="Inflow" />
            <Line type="monotone" dataKey="outflow" stroke="#dc2626" dot={false} name="Outflow" />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <table className="sr-only">
        <caption>Monthly inflow and outflow</caption>
        <thead>
          <tr>
            <th scope="col">Month</th>
            <th scope="col">Inflow</th>
            <th scope="col">Outflow</th>
          </tr>
        </thead>
        <tbody>
          {data.map((point) => (
            <tr key={point.month}>
              <th scope="row">{point.month}</th>
              <td>{formatPaise(point.inflow_paise)}</td>
              <td>{formatPaise(point.outflow_paise)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}

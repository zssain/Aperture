import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { chartColors } from "../../lib/chartColors";
import { formatPaise } from "../../lib/format";

export interface CashflowPoint {
  month: string; // e.g. "2026-03"
  inflow_paise: number;
  outflow_paise: number;
}

/** Compact ₹ tick, e.g. 1234500 paise → "₹12.3k". */
function shortRupee(rupees: number): string {
  if (Math.abs(rupees) >= 1_00_000) return `₹${(rupees / 1_00_000).toFixed(1)}L`;
  if (Math.abs(rupees) >= 1_000) return `₹${(rupees / 1_000).toFixed(0)}k`;
  return `₹${rupees}`;
}

/** A six-month inflow/outflow timeline. This chart earns its place: irregular income
 * is a *shape* that a table of monthly totals cannot convey. An sr-only table carries
 * the same data for assistive tech, so the shape is a bonus, never the only channel. */
export function CashflowTimeline({ data }: { data: CashflowPoint[] }) {
  if (data.length === 0) {
    return (
      <p className="rounded border border-dashed border-border-strong bg-surface p-4 text-sm text-muted">
        No cash-flow to chart yet — connect a source with transaction history.
      </p>
    );
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
      className="w-full rounded border border-border bg-surface p-3"
    >
      <div className="h-56 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
            <CartesianGrid stroke={chartColors.grid} vertical={false} />
            <XAxis
              dataKey="month"
              tick={{ fontSize: 11, fill: chartColors.axis }}
              tickLine={false}
              axisLine={{ stroke: chartColors.grid }}
            />
            <YAxis
              tick={{ fontSize: 11, fill: chartColors.axis }}
              tickLine={false}
              axisLine={false}
              width={56}
              tickFormatter={shortRupee}
            />
            <Tooltip
              formatter={(value: number) => formatPaise(Math.round(value * 100))}
              contentStyle={{
                borderRadius: 4,
                border: `1px solid ${chartColors.grid}`,
                fontSize: 12,
              }}
            />
            <Legend iconType="plainline" wrapperStyle={{ fontSize: 12 }} />
            <Line
              type="monotone"
              dataKey="inflow"
              stroke={chartColors.inflow}
              strokeWidth={2}
              dot={false}
              name="Inflow"
            />
            <Line
              type="monotone"
              dataKey="outflow"
              stroke={chartColors.outflow}
              strokeWidth={2}
              dot={false}
              name="Outflow"
            />
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

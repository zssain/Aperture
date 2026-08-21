export interface MetricResult {
  status: "MEASURED" | "INSUFFICIENT_SAMPLE" | "NOT_YET_MEASURABLE";
  value: number | null; ci_low: number | null; ci_high: number | null;
  n: number; minimum_n: number; reason: string | null; projected_date?: string | null;
}

export function GatedMetric({ metric, format = (value) => value.toFixed(3) }: { metric: MetricResult; format?: (value: number) => string }) {
  if (metric.status !== "MEASURED" || metric.value === null) {
    return <span className="text-neutral"><strong>{metric.status.replaceAll("_", " ")}</strong> — {metric.reason}{metric.projected_date ? ` Projected: ${metric.projected_date}.` : ""}</span>;
  }
  return <span><strong>{format(metric.value)}</strong>{metric.ci_low !== null && metric.ci_high !== null ? <small className="ml-2 text-muted">95% CI {format(metric.ci_low)}–{format(metric.ci_high)}</small> : null}</span>;
}

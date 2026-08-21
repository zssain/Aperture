import { useQuery } from "@tanstack/react-query";
import { ErrorState } from "../../components/ui/ErrorState";
import { PageHeader } from "../../components/ui/PageHeader";
import { Skeleton } from "../../components/ui/Skeleton";
import { OfflineBanner } from "../../components/ui/OfflineBanner";
import { cn } from "../../lib/cn";
import { useOnlineStatus } from "../../hooks/useOnlineStatus";
import { api } from "../../lib/api";
import { CalibrationPanel } from "./CalibrationPanel";
import { CoveragePanel } from "./CoveragePanel";
import { DisparityPanel } from "./DisparityPanel";
import { DriftPanel } from "./DriftPanel";
import type { MetricResult } from "./GatedMetric";
import { ModelCardPanel } from "./ModelCardPanel";
import { OverridePanel } from "./OverridePanel";

interface HealthData { data_as_of: string; calibration: Omit<Parameters<typeof CalibrationPanel>[0]["data"], "discrimination">; discrimination: { auc: MetricResult; ks: MetricResult }; drift: Parameters<typeof DriftPanel>[0]["data"]; coverage: Parameters<typeof CoveragePanel>[0]["data"]; overrides: Parameters<typeof OverridePanel>[0]["data"]; disparity: Record<string, Record<string, MetricResult>>; }
const SECTIONS = ["calibration", "drift", "coverage", "overrides", "disparity", "model-card"];

/** Each health metric group, wrapped so the jump links can scroll to it. */
function Panel({ name, children }: { name: string; children: React.ReactNode }) {
  return <div id={`health-${name}`} className="scroll-mt-20">{children}</div>;
}

export function HealthPage() {
  const online = useOnlineStatus();
  const query = useQuery({ queryKey: ["health-metrics"], queryFn: () => api.get<HealthData>("/api/v1/health-metrics") });
  if (query.isLoading) return <><PageHeader eyebrow="Oversight" title="Model & policy health" description="Calibration, drift, coverage, overrides and fairness for the live scorecard and policy." /><div className="grid gap-4 lg:grid-cols-2">{Array.from({ length: 6 }, (_, i) => <Skeleton key={i} className="h-64 w-full" />)}</div></>;
  if (query.error) return <><PageHeader eyebrow="Oversight" title="Model & policy health" /><div className="grid gap-4 lg:grid-cols-2">{SECTIONS.map((name) => <ErrorState key={name} title={`${name.replaceAll("-", " ")} unavailable`} message={query.error.message} onRetry={() => { void query.refetch(); }} />)}</div></>;
  const data = query.data!;
  return <div>
    {!online ? <div className="mb-3"><OfflineBanner /></div> : null}
    <PageHeader
      eyebrow="Oversight"
      title="Model & policy health"
      description={`Calibration, drift, coverage, overrides and fairness — metrics as of ${data.data_as_of}.`}
    >
      <nav aria-label="Health sections" className="flex flex-wrap gap-2">{SECTIONS.map((name) => <a key={name} href={`#health-${name}`} className={cn("rounded-pill border border-border bg-surface px-3 py-1 text-sm text-muted transition-colors duration-fast hover:border-border-strong hover:text-ink")}>{name.replaceAll("-", " ")}</a>)}</nav>
    </PageHeader>
    <div className="grid gap-4 lg:grid-cols-2">
      <Panel name="calibration"><CalibrationPanel data={{ ...data.calibration, discrimination: data.discrimination }} asOf={data.data_as_of} /></Panel>
      <Panel name="drift"><DriftPanel data={data.drift} asOf={data.data_as_of} /></Panel>
      <Panel name="coverage"><CoveragePanel data={data.coverage} asOf={data.data_as_of} /></Panel>
      <Panel name="overrides"><OverridePanel data={data.overrides} asOf={data.data_as_of} /></Panel>
      <Panel name="disparity"><DisparityPanel data={data.disparity} asOf={data.data_as_of} /></Panel>
      <Panel name="model-card"><ModelCardPanel asOf={data.data_as_of} /></Panel>
    </div>
  </div>;
}

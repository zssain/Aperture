import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { ErrorState } from "../../components/ui/ErrorState";
import { Skeleton } from "../../components/ui/Skeleton";
import { OfflineBanner } from "../../components/ui/OfflineBanner";
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
export function HealthPage() {
  const online = useOnlineStatus();
  const query = useQuery({ queryKey: ["health-metrics"], queryFn: () => api.get<HealthData>("/api/v1/health-metrics") }); const [params, setParams] = useSearchParams(); const section = params.get("section") ?? "calibration";
  if (query.isLoading) return <div className="grid gap-4 lg:grid-cols-2">{Array.from({ length: 6 }, (_, i) => <Skeleton key={i} className="h-64 w-full" />)}</div>;
  if (query.error) return <div className="grid gap-4 lg:grid-cols-2">{SECTIONS.map((name) => <ErrorState key={name} title={`${name.replaceAll("-", " ")} unavailable`} message={query.error.message} onRetry={() => { void query.refetch(); }} />)}</div>;
  const data = query.data!;
  return <div>{!online ? <div className="mb-3"><OfflineBanner /></div> : null}<header className="mb-5"><h1 className="text-title font-semibold">Model & policy health</h1><nav aria-label="Health sections" className="mt-3 flex flex-wrap gap-2">{SECTIONS.map((name) => <button key={name} className={section === name ? "text-accent underline" : "text-muted"} onClick={() => setParams({ section: name })}>{name.replaceAll("-", " ")}</button>)}</nav></header><div className="grid gap-4 lg:grid-cols-2"><CalibrationPanel data={{ ...data.calibration, discrimination: data.discrimination }} asOf={data.data_as_of} /><DriftPanel data={data.drift} asOf={data.data_as_of} /><CoveragePanel data={data.coverage} asOf={data.data_as_of} /><OverridePanel data={data.overrides} asOf={data.data_as_of} /><DisparityPanel data={data.disparity} asOf={data.data_as_of} /><ModelCardPanel asOf={data.data_as_of} /></div></div>;
}

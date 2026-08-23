import { useEffect, useMemo, useState } from "react";
import { Button } from "../../components/ui/Button";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { PageHeader } from "../../components/ui/PageHeader";
import { Skeleton } from "../../components/ui/Skeleton";
import { OfflineBanner } from "../../components/ui/OfflineBanner";
import { StaleDataBanner } from "../../components/ui/StaleDataBanner";
import { useOnlineStatus } from "../../hooks/useOnlineStatus";
import { PublishModal } from "./PublishModal";
import { RuleEditor } from "./RuleEditor";
import { SimulationReport } from "./SimulationReport";
import { VersionList } from "./VersionList";
import { useCreateDraft, usePolicies, usePublish, useSaveDraft, useSimulation, useStartSimulation, type PolicyRules } from "./usePolicy";

export function PolicyStudioPage() {
  const policies = usePolicies(); const create = useCreateDraft(); const save = useSaveDraft(); const simulate = useStartSimulation(); const publish = usePublish();
  const online = useOnlineStatus();
  const [selectedId, setSelectedId] = useState<string>(); const [rules, setRules] = useState<PolicyRules>(); const [jobId, setJobId] = useState<string>(); const [modal, setModal] = useState(false);
  const selected = policies.data?.find((item) => item.id === selectedId) ?? policies.data?.find((item) => item.status === "DRAFT");
  const live = policies.data?.find((item) => item.status === "LIVE"); const report = useSimulation(selected?.id, jobId);
  useEffect(() => { if (selected) { setSelectedId(selected.id); setRules(selected.rules); } }, [selected]);
  const exactSimulation = report.data?.status === "SUCCEEDED" && report.data.draft_hash === selected?.draft_hash;
  const errors = selected?.validation.errors ?? [];
  const title = !exactSimulation ? "Simulate the exact current draft before publishing" : "Publish policy";
  const dirty = useMemo(() => rules && selected && JSON.stringify(rules) !== JSON.stringify(selected.rules), [rules, selected]);
  if (policies.isLoading) return <div className="space-y-3"><Skeleton className="h-10 w-48" /><Skeleton className="h-96 w-full" /></div>;
  if (policies.error) return <ErrorState title="Policy Studio unavailable" message={policies.error.message} onRetry={() => { void policies.refetch(); }} />;
  return <>
    {!online ? <div className="mb-3"><OfflineBanner detail="Draft input remains visible, but save, simulate, and publish are blocked." /></div> : null}
    {dirty && report.data ? <div className="mb-3"><StaleDataBanner message="The draft changed since this simulation. Re-simulate before publishing." actionLabel="Clear old report" onAction={() => setJobId(undefined)} /></div> : null}
    <PageHeader
      eyebrow="Oversight"
      title="Policy Studio"
      description="Structured rules only — live policies are immutable."
      actions={selected?.status === "DRAFT" ? <>
        <Button variant="secondary" loading={save.isPending} disabled={!rules || !dirty || !online} onClick={() => rules && save.mutate({ id: selected.id, rules }, { onSuccess: () => { setJobId(undefined); } })}>Save draft</Button>
        <Button variant="secondary" icon="replay" loading={simulate.isPending} disabled={!selected.validation.ok || Boolean(dirty) || !online} onClick={() => simulate.mutate(selected.id, { onSuccess: (result) => setJobId(result.job_id) })}>Simulate</Button>
        <span title={title}><Button disabled={!exactSimulation || !online} onClick={() => setModal(true)}>Publish</Button></span>
      </> : undefined}
    />
    <div className="lg:hidden"><EmptyState icon="alert" title="Desktop required" description="Policy changes require a screen at least 1024px wide so the rules and simulation remain visible together." /></div>
    <div className="hidden min-h-[650px] overflow-hidden rounded border border-border bg-surface lg:flex">
      <VersionList versions={policies.data ?? []} selected={selected?.id} onSelect={setSelectedId} onCreate={() => { if (online) create.mutate(undefined, { onSuccess: (draft) => setSelectedId(draft.id) }); }} creating={create.isPending} />
      <section aria-label="Policy editor" className="min-w-0 flex-1">
        {!selected ? <div className="p-4"><EmptyState icon="document" title="No policy selected" description="Pick a version on the left, or create a draft from the live policy to begin editing." /></div>
          : selected.status !== "DRAFT" ? <div>
            <p className="border-b border-border bg-canvas px-5 py-2 text-xs text-muted">{selected.status === "LIVE" ? "Live policy — read-only. Create a draft to change it." : "Archived policy — read-only."} These are its exact thresholds and terms.</p>
            <RuleEditor rules={selected.rules} errors={[]} onChange={() => undefined} readOnly />
          </div>
          : rules ? <RuleEditor rules={rules} live={live?.rules} errors={errors} onChange={(next) => { setRules(next); setJobId(undefined); }} /> : null}
      </section>
      {report.data ? <SimulationReport report={report.data} /> : null}
    </div>
    {selected && rules && jobId ? <PublishModal open={modal} onOpenChange={setModal} live={live?.rules} draft={rules} count={report.data?.n_snapshots ?? 0} onPublish={(note, bulk) => publish.mutate({ id: selected.id, simulationJobId: jobId, changeNote: note, bulk }, { onSuccess: () => setModal(false) })} /> : null}
  </>;
}

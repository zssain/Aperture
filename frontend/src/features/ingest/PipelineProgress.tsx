import { useEffect, useMemo, useState } from "react";

import { Button } from "../../components/ui/Button";
import { StatusDot } from "../../components/ui/StatusDot";
import type { Tone } from "../../components/ui/tones";
import type { PipelineJob, PipelineStage } from "./useIngest";

interface PipelineProgressProps {
  job: PipelineJob;
  retrying?: boolean;
  onRetry: (stage: string) => void;
}

const TONES: Record<PipelineStage["status"], Tone> = {
  pending: "neutral",
  running: "caution",
  complete: "positive",
  failed: "negative",
};

function elapsed(stage: PipelineStage, now: number): string | null {
  if (!stage.started_at) return null;
  const end = stage.finished_at ? Date.parse(stage.finished_at) : now;
  const seconds = Math.max(0, Math.floor((end - Date.parse(stage.started_at)) / 1000));
  return `${seconds}s`;
}

export function PipelineProgress({ job, retrying = false, onRetry }: PipelineProgressProps) {
  const [now, setNow] = useState(() => Date.now());
  const stages = useMemo(() => job.result?.stages ?? [], [job.result?.stages]);

  useEffect(() => {
    if (!stages.some((stage) => stage.status === "running")) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => window.clearInterval(timer);
  }, [stages]);

  return (
    <section aria-labelledby="pipeline-heading" className="rounded border border-border bg-surface p-5">
      <div className="mb-4">
        <p className="text-xs font-medium uppercase text-muted">Pipeline</p>
        <h2 id="pipeline-heading" className="text-heading font-semibold text-ink">
          Case progress
        </h2>
        <p className="mt-1 text-sm text-muted">
          Job {job.id.slice(0, 8)} · {job.status}. This work continues on the server if you leave.
        </p>
      </div>
      <ol aria-live="polite" className="space-y-1">
        {stages.map((stage) => {
          const canRetry = stage.status === "failed" && job.result?.retryable_stage === stage.key;
          return (
            <li key={stage.key} className="flex gap-3 border-l border-border pb-4 pl-4 last:pb-0">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <StatusDot tone={TONES[stage.status]} label={`${stage.label}: ${stage.status}`} />
                  {elapsed(stage, now) ? <span className="text-xs text-muted">{elapsed(stage, now)}</span> : null}
                  {stage.count !== null && stage.count !== undefined ? (
                    <span className="text-xs text-muted">Count: {stage.count}</span>
                  ) : null}
                </div>
                {stage.message ? <p className="mt-1 text-sm text-muted">{stage.message}</p> : null}
              </div>
              {canRetry ? (
                <Button size="sm" variant="secondary" disabled={retrying} onClick={() => onRetry(stage.key)}>
                  Retry {stage.label.toLowerCase()}
                </Button>
              ) : null}
            </li>
          );
        })}
      </ol>
      {(job.result?.sources ?? []).length > 0 ? (
        <div className="mt-4 border-t border-border pt-3">
          <h3 className="text-sm font-medium text-ink">Sources</h3>
          <ul className="mt-2 space-y-1 text-sm text-muted">
            {job.result?.sources?.map((source) => (
              <li key={source.connection_id}>
                {source.source_type ?? "Source"}: {source.status}
                {source.status === "UNAVAILABLE" ? " — retrying" : ""}
                {source.message ? ` · ${source.message}` : ""}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {job.error ? <p role="alert" className="mt-3 text-sm text-negative">{job.error}</p> : null}
    </section>
  );
}

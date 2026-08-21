import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { cn } from "../../lib/cn";
import type { PolicyVersion } from "./usePolicy";

const STATUS_TONE: Record<string, "positive" | "accent" | "neutral"> = {
  LIVE: "positive",
  DRAFT: "accent",
};

export function VersionList({ versions, selected, onSelect, onCreate, creating = false }: { versions: PolicyVersion[]; selected?: string; onSelect: (id: string) => void; onCreate: () => void; creating?: boolean }) {
  return <aside className="w-full border-r border-border bg-surface p-4 lg:w-[280px] lg:flex-none">
    <Button className="mb-4 w-full" icon="plus" loading={creating} onClick={onCreate}>Create draft</Button>
    <h2 className="mb-2 eyebrow">Versions</h2>
    <ul className="space-y-2">{versions.map((version) => <li key={version.id}>
      <button className={cn("w-full rounded border p-3 text-left transition-colors duration-fast", selected === version.id ? "border-accent bg-accent-subtle" : "border-border hover:border-border-strong hover:bg-surface-subtle")} onClick={() => onSelect(version.id)}>
        <span className="flex items-center justify-between gap-2"><strong className="text-ink">v{version.version}</strong><Badge tone={STATUS_TONE[version.status] ?? "neutral"}>{version.status}</Badge></span>
        <span className="mt-1 block text-xs text-muted">{version.author ?? "System"}</span>
        <span className="block truncate text-xs text-muted">{version.change_note ?? "No change note"}</span>
      </button>
    </li>)}</ul>
  </aside>;
}

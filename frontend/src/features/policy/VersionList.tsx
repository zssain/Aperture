import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import type { PolicyVersion } from "./usePolicy";

export function VersionList({ versions, selected, onSelect, onCreate }: { versions: PolicyVersion[]; selected?: string; onSelect: (id: string) => void; onCreate: () => void }) {
  return <aside className="w-full border-r border-border bg-surface p-4 lg:w-[280px] lg:flex-none">
    <Button className="mb-4 w-full" onClick={onCreate}>Create draft</Button>
    <h2 className="mb-2 text-sm font-semibold">Versions</h2>
    <ul className="space-y-2">{versions.map((version) => <li key={version.id}>
      <button className={`w-full rounded border p-3 text-left ${selected === version.id ? "border-accent" : "border-border"}`} onClick={() => onSelect(version.id)}>
        <span className="flex justify-between"><strong>v{version.version}</strong><Badge>{version.status}</Badge></span>
        <span className="mt-1 block text-xs text-muted">{version.author ?? "System"}</span>
        <span className="block text-xs text-muted">{version.change_note ?? "No change note"}</span>
      </button>
    </li>)}</ul>
  </aside>;
}

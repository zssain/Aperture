import { useState } from "react";
import { Button } from "../../components/ui/Button";
import { Modal } from "../../components/ui/Modal";
import type { PolicyRules } from "./usePolicy";
import { PolicyDiff } from "./PolicyDiff";

export function PublishModal({ open, onOpenChange, live, draft, count, onPublish }: { open: boolean; onOpenChange: (open: boolean) => void; live?: PolicyRules; draft: PolicyRules; count: number; onPublish: (note: string, bulk: boolean) => void }) {
  const [note, setNote] = useState(""); const [bulk, setBulk] = useState(false);
  return <Modal open={open} onOpenChange={onOpenChange} title="Publish policy" description="This changes lending policy for every new decision." footer={<><Button variant="secondary" onClick={() => onOpenChange(false)}>Cancel</Button><Button disabled={note.trim().length < 20} onClick={() => onPublish(note, bulk)}>Publish</Button></>}>
    <div className="space-y-4"><PolicyDiff live={live} draft={draft} /><label className="block text-sm">Change note (minimum 20 characters)<textarea className="mt-1 min-h-24 w-full rounded border border-border-strong p-2" value={note} onChange={(event) => setNote(event.target.value)} /></label><label className="flex gap-2"><input type="checkbox" checked={bulk} onChange={(event) => setBulk(event.target.checked)} />Bulk re-decide {count} cases asynchronously</label></div>
  </Modal>;
}

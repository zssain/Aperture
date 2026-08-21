import type { ReactNode } from "react";
export function PartialDataNotice({ children }: { children: ReactNode }) { return <div role="status" className="rounded border border-caution bg-surface px-3 py-2 text-sm text-ink"><strong>Partial data.</strong> {children}</div>; }

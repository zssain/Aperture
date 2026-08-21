import type { PolicyRules } from "./usePolicy";

export function PolicyDiff({ live, draft }: { live?: PolicyRules; draft: PolicyRules }) {
  if (!live) return null;
  const changed = Object.keys(draft).filter((key) => JSON.stringify(draft[key as keyof PolicyRules]) !== JSON.stringify(live[key as keyof PolicyRules]));
  return <div><strong>{changed.length} changed sections</strong><ul className="list-disc pl-5 text-sm">{changed.map((key) => <li key={key}>{key.replaceAll("_", " ")}</li>)}</ul></div>;
}

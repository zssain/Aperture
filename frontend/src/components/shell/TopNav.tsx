import { NavLink } from "react-router-dom";

import type { Role } from "../../features/auth/useSession";
import { useSession } from "../../features/auth/useSession";
import { cn } from "../../lib/cn";
import { UserMenu } from "./UserMenu";

interface NavItem {
  to: string;
  label: string;
  roles: Role[];
}

const ALL_ROLES: Role[] = [
  "CREDIT_ANALYST",
  "FRAUD_REVIEWER",
  "CREDIT_POLICY_OWNER",
  "AUDITOR",
];

const NAV_ITEMS: NavItem[] = [
  { to: "/queue", label: "Queue", roles: ALL_ROLES },
  { to: "/policy", label: "Policy", roles: ["CREDIT_POLICY_OWNER"] },
  { to: "/health", label: "Health", roles: ["CREDIT_POLICY_OWNER", "AUDITOR"] },
];

const NEW_CASE_ROLES: Role[] = ["CREDIT_ANALYST", "CREDIT_POLICY_OWNER"];

function linkClasses({ isActive }: { isActive: boolean }): string {
  return cn(
    "rounded px-3 py-2 text-sm font-medium",
    isActive ? "bg-sunken text-ink" : "text-muted hover:text-ink",
  );
}

export function TopNav() {
  const { data: session } = useSession();
  if (!session) return null;

  const items = NAV_ITEMS.filter((item) => item.roles.includes(session.role));
  const canCreateCase = NEW_CASE_ROLES.includes(session.role);

  return (
    <header className="border-b border-border bg-surface">
      <div className="mx-auto flex h-14 max-w-content items-center justify-between gap-4 px-6">
        <nav aria-label="Primary" className="flex items-center gap-1">
          <NavLink
            to="/queue"
            aria-label="Aperture home"
            className="mr-3 shrink-0 rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
          >
            <picture>
              <source media="(max-width: 639px)" srcSet="/brand/aperture-icon.svg" />
              <img
                src="/brand/aperture-logo.svg"
                alt=""
                className="h-7 w-auto sm:h-8"
                width="140"
                height="32"
              />
            </picture>
            <span className="sr-only">APERTURE</span>
          </NavLink>
          {items.map((item) => (
            <NavLink key={item.to} to={item.to} className={linkClasses}>
              {item.label}
            </NavLink>
          ))}
          {canCreateCase ? (
            <NavLink
              to="/ingest"
              className={({ isActive }) =>
                cn(
                  "rounded px-3 py-2 text-sm font-medium",
                  isActive ? "bg-sunken text-ink" : "text-accent hover:bg-sunken",
                )
              }
            >
              + New case
            </NavLink>
          ) : null}
        </nav>
        <UserMenu />
      </div>
    </header>
  );
}

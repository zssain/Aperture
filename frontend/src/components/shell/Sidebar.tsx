import { NavLink, useNavigate } from "react-router-dom";

import { roleLabel, useSession, useSignOut } from "../../features/auth/useSession";
import { cn } from "../../lib/cn";
import { Icon } from "../ui/Icon";
import { navGroupsForRole } from "./nav";

interface SidebarProps {
  /** Fired after a nav item is chosen — used by the mobile drawer to close itself. */
  onNavigate?: () => void;
}

/**
 * The navy navigation rail. One implementation, shared by the persistent desktop
 * rail and the mobile drawer. Active items carry a teal rail (a shape cue), not
 * colour alone.
 */
export function Sidebar({ onNavigate }: SidebarProps) {
  const { data: session } = useSession();
  const signOut = useSignOut();
  const navigate = useNavigate();

  if (!session) return null;

  const groups = navGroupsForRole(session.role);

  function onSignOut(): void {
    signOut.mutate(undefined, {
      onSuccess: () => navigate("/signin", { replace: true }),
    });
  }

  return (
    <div className="flex h-full w-sidebar flex-col bg-nav text-nav-fg">
      <div className="flex h-16 items-center px-5">
        <NavLink
          to="/queue"
          aria-label="Aperture home"
          onClick={onNavigate}
          className="rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-nav"
        >
          <img
            src="/brand/aperture-logo-light.svg"
            alt=""
            className="h-7 w-auto"
            width="140"
            height="32"
          />
          <span className="sr-only">APERTURE</span>
        </NavLink>
      </div>

      <nav aria-label="Primary" className="flex-1 overflow-y-auto px-3 py-2">
        {groups.map((group) => (
          <div key={group.heading} className="mb-5">
            <p className="eyebrow px-2 pb-1.5 text-nav-muted">{group.heading}</p>
            <ul className="space-y-0.5">
              {group.items.map((item) => (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    onClick={onNavigate}
                    className={({ isActive }) =>
                      cn(
                        "relative flex items-center gap-3 rounded px-3 py-2 text-sm font-medium transition-colors duration-fast",
                        isActive
                          ? "bg-nav-raised text-nav-fg"
                          : "text-nav-muted hover:bg-nav-raised/60 hover:text-nav-fg",
                      )
                    }
                  >
                    {({ isActive }) => (
                      <>
                        <span
                          aria-hidden="true"
                          className={cn(
                            "absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-pill bg-brand transition-opacity duration-fast",
                            isActive ? "opacity-100" : "opacity-0",
                          )}
                        />
                        <Icon name={item.icon} size={18} />
                        <span>{item.label}</span>
                      </>
                    )}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>

      <div className="border-t border-nav-border p-3">
        <div className="px-2 pb-2">
          <p className="truncate text-sm font-medium text-nav-fg">
            {session.fullName}
          </p>
          <p className="truncate text-xs text-nav-muted">
            {roleLabel(session.role)} · {session.tenantName}
          </p>
        </div>
        <button
          type="button"
          onClick={onSignOut}
          disabled={signOut.isPending}
          className="flex w-full items-center gap-2 rounded px-3 py-2 text-sm font-medium text-nav-muted transition-colors duration-fast hover:bg-nav-raised hover:text-nav-fg disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Icon name="sign-out" size={18} />
          <span>Sign out</span>
        </button>
      </div>
    </div>
  );
}

import type { ReactNode } from "react";

import type { Role } from "../../features/auth/useSession";
import { roleLabel, useSession } from "../../features/auth/useSession";
import { PermissionDenied } from "../ui/PermissionDenied";

export interface RequireRoleProps {
  roles: Role[];
  children: ReactNode;
}

/** Gate that shows a purpose-built screen (not a blank page) for the wrong role. */
export function RequireRole({ roles, children }: RequireRoleProps) {
  const { data: session } = useSession();

  // RequireAuth handles the unauthenticated case; render nothing here.
  if (!session) return null;

  if (!roles.includes(session.role)) {
    const allowed = roles.map(roleLabel).join(", ");
    return <PermissionDenied reason={`This area is restricted to: ${allowed}. Your role is ${roleLabel(session.role)}.`} />;
  }

  return <>{children}</>;
}

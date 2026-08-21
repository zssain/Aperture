import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { useSession } from "../../features/auth/useSession";
import { Skeleton } from "../ui/Skeleton";

export interface RequireAuthProps {
  children: ReactNode;
}

/** Gate that redirects to sign-in (preserving the return URL) when unauthenticated. */
export function RequireAuth({ children }: RequireAuthProps) {
  const { data: session, isLoading } = useSession();
  const location = useLocation();

  if (isLoading) {
    return (
      <div className="flex items-center gap-3 p-6" aria-busy="true" aria-label="Loading Aperture">
        <img
          src="/brand/aperture-icon.svg"
          alt=""
          className="h-8 w-8 shrink-0"
          width="32"
          height="32"
        />
        <Skeleton className="h-4 w-48" />
      </div>
    );
  }

  if (!session) {
    const returnTo = `${location.pathname}${location.search}`;
    return <Navigate to="/signin" replace state={{ returnTo }} />;
  }

  return <>{children}</>;
}

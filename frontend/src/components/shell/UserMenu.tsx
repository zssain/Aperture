import { useNavigate } from "react-router-dom";

import { roleLabel, useSession, useSignOut } from "../../features/auth/useSession";
import { Button } from "../ui/Button";
import { Popover } from "../ui/Popover";

export function UserMenu() {
  const { data: session } = useSession();
  const signOut = useSignOut();
  const navigate = useNavigate();

  if (!session) return null;

  function onSignOut(): void {
    signOut.mutate(undefined, {
      onSuccess: () => navigate("/signin", { replace: true }),
    });
  }

  return (
    <Popover
      trigger={
        <button
          type="button"
          className="rounded px-3 py-2 text-sm font-medium text-ink hover:bg-sunken"
        >
          {session.fullName}
        </button>
      }
    >
      <div className="min-w-menu p-3">
        <p className="text-sm font-medium text-ink">{session.fullName}</p>
        <p className="text-xs text-muted">{roleLabel(session.role)}</p>
        <p className="text-xs text-muted">{session.tenantName}</p>
        <div className="mt-3 border-t border-border pt-3">
          <Button
            variant="secondary"
            size="sm"
            className="w-full"
            onClick={onSignOut}
            disabled={signOut.isPending}
          >
            Sign out
          </Button>
        </div>
      </div>
    </Popover>
  );
}

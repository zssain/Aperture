import * as Dialog from "@radix-ui/react-dialog";
import { useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";

import { Icon } from "../ui/Icon";
import { Sidebar } from "./Sidebar";

/**
 * Authenticated shell: a persistent navy rail at >=1024px beside a light, max-width
 * workspace. Below 1024px the rail collapses into a drawer behind a menu button in a
 * compact top bar. The drawer is driven off `location`, so it closes on any route
 * change including browser back/forward.
 */
export function AppShell() {
  const location = useLocation();
  const [drawerOpen, setDrawerOpen] = useState(false);

  useEffect(() => {
    setDrawerOpen(false);
  }, [location.pathname, location.search]);

  return (
    <div className="min-h-screen bg-sunken">
      <a
        href="#main-content"
        className="sr-only z-50 rounded bg-surface p-3 focus:not-sr-only focus:fixed focus:left-3 focus:top-3"
      >
        Skip to content
      </a>

      {/* Persistent desktop rail. */}
      <div className="fixed inset-y-0 left-0 z-30 hidden lg:block">
        <Sidebar />
      </div>

      {/* Compact top bar for < lg: icon mark + menu button only (no second nav). */}
      <div className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-border bg-surface px-4 lg:hidden">
        <Dialog.Root open={drawerOpen} onOpenChange={setDrawerOpen}>
          <Dialog.Trigger asChild>
            <button
              type="button"
              aria-label="Open navigation menu"
              className="inline-flex h-10 w-10 items-center justify-center rounded text-ink transition-colors duration-fast hover:bg-sunken"
            >
              <Icon name="menu" />
            </button>
          </Dialog.Trigger>
          <Dialog.Portal>
            <Dialog.Overlay className="fixed inset-0 z-40 bg-ink/40 animate-fade-in" />
            <Dialog.Content
              className="fixed inset-y-0 left-0 z-50 animate-drawer-in shadow-drawer focus:outline-none"
            >
              <Dialog.Title className="sr-only">Navigation</Dialog.Title>
              <Sidebar onNavigate={() => setDrawerOpen(false)} />
            </Dialog.Content>
          </Dialog.Portal>
        </Dialog.Root>
        <img
          src="/brand/aperture-icon.svg"
          alt=""
          aria-hidden="true"
          className="h-7 w-7"
          width="28"
          height="28"
        />
      </div>

      <div className="lg:pl-sidebar">
        <main
          id="main-content"
          tabIndex={-1}
          className="mx-auto max-w-content px-4 py-6 sm:px-6 lg:px-8"
        >
          <Outlet />
        </main>
      </div>
    </div>
  );
}

import { Outlet } from "react-router-dom";

import { TopNav } from "./TopNav";

/** Authenticated shell: top nav, no sidebar, content fluid to 1600px. */
export function AppShell() {
  return (
    <div className="min-h-screen bg-sunken">
      <a href="#main-content" className="sr-only z-50 rounded bg-surface p-3 focus:not-sr-only focus:fixed focus:left-3 focus:top-3">Skip to content</a>
      <TopNav />
      <main id="main-content" tabIndex={-1} className="mx-auto max-w-content p-4 sm:p-6">
        <Outlet />
      </main>
    </div>
  );
}

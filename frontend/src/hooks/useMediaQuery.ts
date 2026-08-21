import { useEffect, useState } from "react";

/**
 * Subscribe to a CSS media query. Mount exactly one layout branch off this instead
 * of rendering both and hiding one with CSS (which doubles what a screen reader
 * announces).
 *
 * When `matchMedia` is unavailable (jsdom, older SSR) it returns `defaultMatches`,
 * so callers should default the query that mounts the desktop branch to `true`.
 */
export function useMediaQuery(query: string, defaultMatches = false): boolean {
  const read = (): boolean =>
    typeof window !== "undefined" && typeof window.matchMedia === "function"
      ? window.matchMedia(query).matches
      : defaultMatches;

  const [matches, setMatches] = useState<boolean>(read);

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return;
    }
    const list = window.matchMedia(query);
    const onChange = (): void => setMatches(list.matches);
    // Sync immediately in case the query changed between render and effect.
    onChange();
    list.addEventListener("change", onChange);
    return () => list.removeEventListener("change", onChange);
  }, [query]);

  return matches;
}

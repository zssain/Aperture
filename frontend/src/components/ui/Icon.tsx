import type { SVGProps } from "react";

import { cn } from "../../lib/cn";

/**
 * The single icon set. Inline SVG on a 24×24 grid, 1.5px stroke, round caps/joins.
 * No icon library — every glyph lives here so the stroke weight and grid stay
 * consistent. Decorative by default (aria-hidden); pass `title` for the rare
 * icon-only control that needs an accessible name.
 */
export type IconName =
  | "menu"
  | "search"
  | "filter"
  | "close"
  | "check"
  | "alert"
  | "info"
  | "clock"
  | "bank"
  | "upload"
  | "document"
  | "shield"
  | "replay"
  | "audit"
  | "sign-out"
  | "queue"
  | "plus"
  | "external"
  | "chevron-up"
  | "chevron-down"
  | "chevron-left"
  | "chevron-right"
  | "arrow-right"
  | "eye"
  | "eye-off";

/** Path/element markup per glyph, drawn on the shared 24×24 grid. */
const PATHS: Record<IconName, JSX.Element> = {
  menu: <path d="M4 6h16M4 12h16M4 18h16" />,
  search: (
    <>
      <circle cx="11" cy="11" r="6" />
      <path d="M20 20l-3.5-3.5" />
    </>
  ),
  filter: <path d="M4 5h16l-6 8v5l-4 2v-7L4 5z" />,
  close: <path d="M6 6l12 12M18 6L6 18" />,
  check: <path d="M5 12.5l4.5 4.5L19 7" />,
  alert: (
    <>
      <path d="M12 4l9 16H3L12 4z" />
      <path d="M12 10v4" />
      <path d="M12 17.5v.5" />
    </>
  ),
  info: (
    <>
      <circle cx="12" cy="12" r="8" />
      <path d="M12 11v5" />
      <path d="M12 8v.5" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="8" />
      <path d="M12 8v4l3 2" />
    </>
  ),
  bank: (
    <>
      <path d="M4 9l8-4 8 4" />
      <path d="M5 9v9M10 9v9M14 9v9M19 9v9" />
      <path d="M3 21h18" />
    </>
  ),
  upload: (
    <>
      <path d="M12 16V5" />
      <path d="M7.5 9.5L12 5l4.5 4.5" />
      <path d="M5 19h14" />
    </>
  ),
  document: (
    <>
      <path d="M6 3h8l4 4v14H6V3z" />
      <path d="M14 3v4h4" />
      <path d="M9 13h6M9 16.5h6" />
    </>
  ),
  shield: (
    <>
      <path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6l7-3z" />
      <path d="M9 12l2 2 4-4" />
    </>
  ),
  replay: (
    <>
      <path d="M4 12a8 8 0 1 0 2.5-5.8" />
      <path d="M4 4v3h3" />
    </>
  ),
  audit: (
    <>
      <path d="M6 3h8l4 4v14H6V3z" />
      <path d="M14 3v4h4" />
      <path d="M9 11.5l1.5 1.5L13 10.5" />
      <path d="M9 16h6" />
    </>
  ),
  "sign-out": (
    <>
      <path d="M14 4H6v16h8" />
      <path d="M18 12H10" />
      <path d="M15 9l3 3-3 3" />
    </>
  ),
  queue: (
    <>
      <path d="M4 6h16M4 12h16M4 18h10" />
      <circle cx="19" cy="18" r="1.5" />
    </>
  ),
  plus: <path d="M12 5v14M5 12h14" />,
  external: (
    <>
      <path d="M14 5h5v5" />
      <path d="M19 5l-8 8" />
      <path d="M17 13v6H5V7h6" />
    </>
  ),
  "chevron-up": <path d="M6 15l6-6 6 6" />,
  "chevron-down": <path d="M6 9l6 6 6-6" />,
  "chevron-left": <path d="M15 6l-6 6 6 6" />,
  "chevron-right": <path d="M9 6l6 6-6 6" />,
  "arrow-right": <path d="M5 12h14M13 6l6 6-6 6" />,
  eye: (
    <>
      <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z" />
      <circle cx="12" cy="12" r="3" />
    </>
  ),
  "eye-off": (
    <>
      <path d="M4 4l16 16" />
      <path d="M9.5 5.4A9.6 9.6 0 0 1 12 5c6.5 0 10 7 10 7a17 17 0 0 1-3.2 3.9" />
      <path d="M6.2 7.2A17 17 0 0 0 2 12s3.5 7 10 7a9.5 9.5 0 0 0 3.3-.6" />
      <path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" />
    </>
  ),
};

export interface IconProps extends Omit<SVGProps<SVGSVGElement>, "name"> {
  name: IconName;
  /** Pixel size (width and height). Defaults to 20. */
  size?: number;
  /** When set, the icon is exposed to assistive tech with this accessible name. */
  title?: string;
}

export function Icon({ name, size = 20, title, className, ...props }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
      className={cn("shrink-0", className)}
      {...props}
    >
      {title ? <title>{title}</title> : null}
      {PATHS[name]}
    </svg>
  );
}

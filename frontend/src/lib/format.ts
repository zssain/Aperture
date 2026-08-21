/**
 * Display formatting. Money is integer paise everywhere (invariant 6); it is only
 * divided by 100 at the very edge, here, for display.
 */

const RUPEE = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** Integer paise → ₹ string, e.g. 500000 → "₹5,000.00". */
export function formatPaise(paise: number): string {
  return RUPEE.format(paise / 100);
}

const DATE = new Intl.DateTimeFormat("en-IN", {
  year: "numeric",
  month: "short",
  day: "2-digit",
});

const DATE_TIME = new Intl.DateTimeFormat("en-IN", {
  year: "numeric",
  month: "short",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

export function formatDate(iso: string | Date): string {
  const date = typeof iso === "string" ? new Date(iso) : iso;
  return DATE.format(date);
}

export function formatDateTime(iso: string | Date): string {
  const date = typeof iso === "string" ? new Date(iso) : iso;
  return DATE_TIME.format(date);
}

/** A ratio in [0,1] → percent string, e.g. formatPercent(0.1234, 1) → "12.3%". */
export function formatPercent(ratio: number, precision = 1): string {
  return `${(ratio * 100).toFixed(precision)}%`;
}

/** A plain number to fixed precision with grouping, e.g. 1234.5 → "1,234.50". */
export function formatNumber(value: number, precision = 0): string {
  return new Intl.NumberFormat("en-IN", {
    minimumFractionDigits: precision,
    maximumFractionDigits: precision,
  }).format(value);
}

/** Join class names, dropping falsy values. Small local helper — no dependency. */
export type ClassValue = string | false | null | undefined;

export function cn(...values: ClassValue[]): string {
  return values.filter(Boolean).join(" ");
}

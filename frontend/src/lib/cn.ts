import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Merge Tailwind classes so a caller's `className` can *override* a
 * component's defaults rather than merely appending and losing to whichever
 * class the compiler emitted last.
 *
 * `tailwind-merge` was already a dependency but had never been imported, which
 * is why every hand-rolled card duplicates its padding inline instead of
 * overriding a shared default.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

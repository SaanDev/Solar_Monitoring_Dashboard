// NOAA R/S/G scale display helpers shared by the forecast components.

/** Numeric level of a NOAA scale value ("0".."5", null) — 0 when absent. */
export function scaleLevel(scale: string | null | undefined): number {
  const n = scale != null ? parseInt(scale, 10) : NaN;
  return Number.isFinite(n) ? Math.max(0, Math.min(5, n)) : 0;
}

/** Badge classes for a NOAA scale level (0 = quiet … 5 = extreme). */
export function scaleBadgeClass(level: number): string {
  if (level >= 4) return "bg-red-500/20 text-red-400 border-red-500/40";
  if (level === 3) return "bg-orange-500/20 text-orange-400 border-orange-500/40";
  if (level === 2) return "bg-amber-500/20 text-amber-400 border-amber-500/40";
  if (level === 1) return "bg-yellow-500/20 text-yellow-500 border-yellow-500/40";
  return "bg-surface-muted text-slate-500 border-surface-border";
}

/** "in 14 h" / "12 h ago" / "now" for an ISO timestamp vs. the current time. */
export function relativeTime(iso: string): string {
  const deltaMin = Math.round((new Date(iso).getTime() - Date.now()) / 60000);
  const abs = Math.abs(deltaMin);
  const span =
    abs >= 2880
      ? `${Math.round(abs / 1440)} d`
      : abs >= 60
        ? `${Math.round(abs / 60)} h`
        : `${abs} min`;
  if (abs < 5) return "now";
  return deltaMin > 0 ? `in ${span}` : `${span} ago`;
}

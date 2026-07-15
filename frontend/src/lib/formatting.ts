/**
 * Convert an ISO timestamp to a naive UTC wall-clock string ("YYYY-MM-DD HH:MM:SS").
 * Plotly renders Date objects in the browser's local timezone; passing the UTC
 * wall-clock as a tz-less string makes Plotly display the exact UTC values.
 */
export function toPlotlyUtc(iso: string): string {
  return new Date(iso).toISOString().slice(0, 19).replace("T", " ");
}

export function formatUtc(iso: string): string {
  return new Date(iso).toUTCString().replace("GMT", "UTC");
}

export function formatUtcShort(iso: string): string {
  const d = new Date(iso);
  return d.toISOString().slice(0, 19).replace("T", " ") + " UTC";
}

/**
 * A rolling UTC [start, end] window ending "now", `hours` wide, as ISO strings.
 * Computed at call time so the window advances on each SWR refresh.
 */
export function windowFor(hours: number): { start: string; end: string } {
  const now = Date.now();
  const iso = (ms: number) => new Date(ms).toISOString().slice(0, 19) + "Z";
  return { start: iso(now - hours * 3600 * 1000), end: iso(now) };
}

/**
 * Parse a backend ISO timestamp to epoch **seconds**, treating a bare
 * (offset-less) timestamp as UTC. Backend `datetime.isoformat()` may or may not
 * carry an offset: naive → "2024-01-01T00:00:00", aware → "…+00:00". Blindly
 * appending "Z" turns the aware form into "…+00:00Z", an invalid date whose
 * `getTime()` is NaN — which then crashes `new Date(NaN).toISOString()`.
 * Returns NaN for null/blank/unparseable input so callers can filter it out.
 */
export function parseUtcSeconds(iso: string | null | undefined): number {
  if (!iso) return NaN;
  // Add "Z" only when the string has no timezone designator already.
  const hasTz = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(iso);
  const ms = new Date(hasTz ? iso : iso + "Z").getTime();
  return Number.isNaN(ms) ? NaN : ms / 1000;
}

/** Format epoch seconds as a UTC "HH:MM" clock label; "" for NaN/invalid. */
export function formatClockUtc(sec: number): string {
  if (!Number.isFinite(sec)) return "";
  return new Date(sec * 1000).toISOString().slice(11, 16);
}

export function flareClass(flux: number | null): string {
  if (flux === null) return "—";
  if (flux >= 1e-4) return "X" + (flux / 1e-4).toFixed(1);
  if (flux >= 1e-5) return "M" + (flux / 1e-5).toFixed(1);
  if (flux >= 1e-6) return "C" + (flux / 1e-6).toFixed(1);
  if (flux >= 1e-7) return "B" + (flux / 1e-7).toFixed(1);
  return "A" + (flux / 1e-8).toFixed(1);
}

export function kpStormLevel(kp: number): string {
  if (kp >= 9) return "G5";
  if (kp >= 8) return "G4";
  if (kp >= 7) return "G3";
  if (kp >= 6) return "G2";
  if (kp >= 5) return "G1";
  return "—";
}

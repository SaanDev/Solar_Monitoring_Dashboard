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

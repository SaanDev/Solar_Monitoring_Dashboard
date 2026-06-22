// Build + download a plain-text report of a single UTC day's space-weather
// events, grouped into the four event categories (X-ray flares, radio bursts,
// SEP/proton events, geomagnetic storms). Shared by the Events ("Alerts") page
// and the Burst Predictor page so both produce an identically-formatted file.
import type { Alert, BurstPredictionResult } from "./types";
import { alertLabel, categoryOf, type AlertCategoryKey } from "./alerts";

/** A normalized event row for the report. */
export interface ReportEvent {
  category: AlertCategoryKey;
  time: string; // ISO timestamp
  title: string; // e.g. "X-Ray Flare", "Radio Burst (model prediction)"
  severity: string; // free text, e.g. "warning", "High-confidence burst"
  detail: string; // human-readable description
}

// Report section order + headings (matches the requested grouping order:
// X-ray flares, radio bursts, SEP events, geomagnetic storms).
const SECTIONS: { key: AlertCategoryKey; heading: string }[] = [
  { key: "xray_flare", heading: "X-RAY FLARES" },
  { key: "radio_burst", heading: "RADIO BURSTS" },
  { key: "proton_event", heading: "SEP EVENTS (Solar Energetic Particle / proton events)" },
  { key: "geomagnetic_storm", heading: "GEOMAGNETIC STORMS" },
];

/** UTC calendar day (YYYY-MM-DD) of an ISO timestamp. */
export function utcDay(iso: string): string {
  return new Date(iso).toISOString().slice(0, 10);
}

/** "YYYY-MM-DD HH:MM:SS UTC" from an ISO timestamp. */
function fmtUtc(iso: string): string {
  return new Date(iso).toISOString().slice(0, 19).replace("T", " ") + " UTC";
}

/** Categorized alerts → report rows (uncategorized alerts are dropped). */
export function alertsToReportEvents(alerts: Alert[]): ReportEvent[] {
  const out: ReportEvent[] = [];
  for (const a of alerts) {
    const category = categoryOf(a.type);
    if (!category) continue;
    out.push({
      category,
      time: a.timestamp,
      title: alertLabel(a.type),
      severity: a.severity,
      detail: a.message,
    });
  }
  return out;
}

/** Predicted burst-prediction events → radio-burst report rows. */
export function predictedToReportEvents(result: BurstPredictionResult): ReportEvent[] {
  return result.events.map((ev) => ({
    category: "radio_burst" as const,
    // ev.start is HH:MM UTC on the result's day; anchor it as a UTC instant.
    time: `${result.date}T${ev.start.length === 5 ? `${ev.start}:00` : ev.start}Z`,
    title: "Radio Burst (model prediction)",
    severity: ev.alert_level || "—",
    detail:
      `${ev.start}–${ev.end} UTC · ${ev.n_stations} station(s) · ` +
      `${ev.n_detections} detection(s) · peak p=${ev.max_probability.toFixed(3)}` +
      (ev.matched_official ? " · matches official burst list" : ""),
  }));
}

/** Number of report rows that fall on the given UTC day. */
export function countEventsForDay(day: string, events: ReportEvent[]): number {
  return events.filter((e) => utcDay(e.time) === day).length;
}

/** Build the plain-text report for one UTC day from pre-assembled rows. */
export function buildEventReport(day: string, events: ReportEvent[]): string {
  const dayEvents = events
    .filter((e) => utcDay(e.time) === day)
    .sort((a, b) => a.time.localeCompare(b.time));

  const rule = "=".repeat(64);
  const thin = "-".repeat(64);
  const L: string[] = [];
  L.push(rule);
  L.push(" SPACE WEATHER EVENT REPORT");
  L.push(` UTC Day:      ${day}`);
  L.push(` Generated:    ${fmtUtc(new Date().toISOString())}`);
  L.push(` Total events: ${dayEvents.length}`);
  L.push(rule);
  L.push("");

  for (const sec of SECTIONS) {
    const items = dayEvents.filter((e) => e.category === sec.key);
    L.push(`### ${sec.heading} (${items.length})`);
    L.push(thin);
    if (items.length === 0) {
      L.push("  (no events)");
    } else {
      for (const e of items) {
        L.push(`  ${fmtUtc(e.time)}  [${e.severity.toUpperCase()}]  ${e.title}`);
        if (e.detail) L.push(`      ${e.detail}`);
      }
    }
    L.push("");
  }
  L.push("— End of report —");
  return L.join("\n");
}

/** Trigger a browser download of `text` as a .txt file. */
export function downloadTextFile(filename: string, text: string): void {
  const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/** Build + download the day report. Returns the number of events exported. */
export function exportEventReport(day: string, events: ReportEvent[]): number {
  downloadTextFile(`space-weather-events_${day}.txt`, buildEventReport(day, events));
  return countEventsForDay(day, events);
}

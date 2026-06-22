// Shared alert/event taxonomy: which dedicated area each type belongs to, its
// friendly label, and where clicking it should visualize the underlying data.
// Used by the overview alerts panel, the events-page alert feed, and the event
// timeline so all three stay consistent.
import { Activity, Compass, Radio, Zap } from "lucide-react";
import type { LucideIcon } from "lucide-react";

export type AlertCategoryKey =
  | "xray_flare"
  | "radio_burst"
  | "geomagnetic_storm"
  | "proton_event";

export interface AlertCategory {
  key: AlertCategoryKey;
  /** Header of the dedicated alerts area for this category. */
  title: string;
  icon: LucideIcon;
  /** Tailwind text-color for the area's icon. */
  accent: string;
}

// Render order of the dedicated areas.
export const ALERT_CATEGORIES: AlertCategory[] = [
  { key: "xray_flare", title: "Flare Alerts", icon: Zap, accent: "text-accent-orange" },
  { key: "radio_burst", title: "Radio Bursts Alerts", icon: Radio, accent: "text-accent-green" },
  {
    key: "geomagnetic_storm",
    title: "Geomagnetic Storm Alerts",
    icon: Compass,
    accent: "text-accent-purple",
  },
  { key: "proton_event", title: "Proton Event Alerts", icon: Activity, accent: "text-accent-red" },
];

// Friendly per-alert label for a machine event-type key.
const TYPE_LABEL: Record<string, string> = {
  xray_flare: "X-Ray Flare",
  radio_burst: "Radio Bursts",
  proton_event: "Proton Event",
  geomagnetic_storm_kp: "Geomagnetic Storm",
  geomagnetic_storm_dst: "Geomagnetic Storm",
};

export function alertLabel(type: string): string {
  return TYPE_LABEL[type] ?? type.replace(/_/g, " ");
}

/** The dedicated area an alert/event type belongs to (null = uncategorized). */
export function categoryOf(type: string): AlertCategoryKey | null {
  if (type === "xray_flare") return "xray_flare";
  if (type === "radio_burst") return "radio_burst";
  if (type === "proton_event") return "proton_event";
  if (type.startsWith("geomagnetic_storm")) return "geomagnetic_storm";
  return null;
}

/** UTC day (YYYY-MM-DD) of an ISO timestamp. */
function utcDay(iso: string): string {
  return new Date(iso).toISOString().slice(0, 10);
}

/**
 * Deep-link to the visualization for an alert/event, anchored on its UTC day.
 *  - radio bursts → the Burst Predictor (stored detections + dynamic spectrum)
 *  - X-ray flares / proton events → the Archive's X-ray/Proton charts
 *  - geomagnetic storms → the Archive's Kp/Dst charts
 */
export function alertHref(type: string, timestamp: string): string {
  const date = utcDay(timestamp);
  switch (categoryOf(type)) {
    case "radio_burst":
      return `/burst-predictor?date=${date}`;
    case "xray_flare":
    case "proton_event":
      return `/archive?instrument=xray&date=${date}`;
    case "geomagnetic_storm":
      return `/archive?instrument=geomag&date=${date}`;
    default:
      return "/events";
  }
}

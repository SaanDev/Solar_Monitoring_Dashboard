import { Notification } from "electron";
import log from "electron-log/main";

import { assetPath } from "./paths";
import { saveState, state } from "./state";

const POLL_MS = 60_000;
const NOTIFY_SEVERITIES = new Set(["warning", "critical"]);
const MAX_TOASTS_PER_POLL = 3;
const MAX_SEEN_IDS = 500;

interface Alert {
  id: string;
  type: string;
  severity: string;
  message: string;
}

// Notifications are garbage-collected with their click handler unless held.
const live = new Set<Notification>();

function title(alert: Alert): string {
  const kind = alert.type.replace(/_/g, " ");
  const sev = alert.severity.charAt(0).toUpperCase() + alert.severity.slice(1);
  return `${sev}: ${kind}`;
}

/**
<<<<<<< HEAD
 * Windows toasts for new warning/critical alerts from /api/alerts/latest.
=======
 * Desktop notifications (Windows toasts, Linux notifications) for new
 * warning/critical alerts from /api/alerts/latest.
>>>>>>> d325f0ffea140b14d8efde51c7c0cf3c0712f39b
 *
 * The very first poll on a fresh install only records what's already there, so
 * installing the app doesn't replay a backlog. After that, every alert id not
 * seen before is shown (capped per poll), including ones raised while the app
 * was closed.
 */
export function startAlertPolling(origin: string, onOpen: (pathname: string) => void): void {
  let seeded = state.seenAlertIds.length > 0;

  const poll = async (): Promise<void> => {
    let alerts: Alert[];
    try {
      const res = await fetch(`${origin}/api/alerts/latest`, { signal: AbortSignal.timeout(15_000) });
      if (!res.ok) return;
      alerts = (await res.json()) as Alert[];
    } catch (err) {
      log.debug("alert poll failed", err);
      return;
    }
    const seen = new Set(state.seenAlertIds);
    const fresh = alerts.filter((a) => !seen.has(a.id));
    if (fresh.length === 0) {
      seeded = true;
      return;
    }

    if (seeded && state.notifications && Notification.isSupported()) {
      for (const alert of fresh.filter((a) => NOTIFY_SEVERITIES.has(a.severity)).slice(0, MAX_TOASTS_PER_POLL)) {
        const toast = new Notification({ title: title(alert), body: alert.message, icon: assetPath("icon.png") });
        live.add(toast);
        toast.on("click", () => onOpen("/events/"));
        toast.on("close", () => live.delete(toast));
        toast.show();
      }
    }
    state.seenAlertIds = [...fresh.map((a) => a.id), ...state.seenAlertIds].slice(0, MAX_SEEN_IDS);
    saveState();
    seeded = true;
  };

  void poll();
  setInterval(() => void poll(), POLL_MS);
}

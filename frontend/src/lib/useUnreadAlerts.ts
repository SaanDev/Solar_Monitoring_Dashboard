"use client";

// Unread-alert tracking for the bell icon and the sidebar "Alerts" badge.
//
// There is no per-user auth, so "read" state lives client-side: the provider
// persists the timestamp of the newest alert the user has seen, and an alert is
// "unread" when it is newer than that marker. Viewing the Alerts/Events page
// marks the feed read (badge clears); a newly-detected event is newer than the
// marker, so the badge reappears.
import useSWR from "swr";

import { api } from "@/lib/api";
import { useApp } from "@/components/providers";

export interface UnreadAlerts {
  /** Number of alerts newer than the last-seen marker. */
  unreadCount: number;
  /** Timestamp of the newest alert in the feed ("" when the feed is empty). */
  newest: string;
  /** Mark the whole current feed as read. */
  markRead: () => void;
}

export function useUnreadAlerts(): UnreadAlerts {
  const { lastSeenAlertAt, markAlertsRead } = useApp();
  const { data } = useSWR("alerts-latest", api.alertsLatest, {
    refreshInterval: 30000,
  });

  const alerts = data ?? [];
  const seenMs = lastSeenAlertAt ? new Date(lastSeenAlertAt).getTime() : 0;

  let newest = "";
  let newestMs = -Infinity;
  let unreadCount = 0;
  for (const a of alerts) {
    const ms = new Date(a.timestamp).getTime();
    if (ms > newestMs) {
      newestMs = ms;
      newest = a.timestamp;
    }
    if (ms > seenMs) unreadCount += 1;
  }

  return { unreadCount, newest, markRead: () => markAlertsRead(newest) };
}

/** Badge text, capped so a long backlog doesn't blow out the badge width. */
export function unreadBadgeText(count: number): string {
  return count > 99 ? "99+" : String(count);
}

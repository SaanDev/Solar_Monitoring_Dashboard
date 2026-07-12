"use client";

import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";
import { clsx } from "clsx";
import { Link2 } from "lucide-react";
import { api } from "@/lib/api";
import { useApp } from "@/components/providers";
import { windowFor } from "@/lib/formatting";
import { alertsToReportEvents } from "@/lib/exportEvents";
import { AlertFeed } from "@/components/alerts/AlertFeed";
import { EventTimeline } from "@/components/events/EventTimeline";
import { ActivityHistograms } from "@/components/events/ActivityHistograms";
import { ExportEventsButton } from "@/components/events/ExportEventsButton";

const RANGES = [
  { key: "1d", label: "1 day", hours: 24 },
  { key: "7d", label: "7 days", hours: 168 },
  { key: "30d", label: "30 days", hours: 720 },
  { key: "90d", label: "90 days", hours: 2160 },
  // "All": a window wide enough to cover the entire event record.
  { key: "all", label: "All", hours: 24 * 366 * 30 },
] as const;

type RangeKey = (typeof RANGES)[number]["key"];

export function EventsClient() {
  const [range, setRange] = useState<RangeKey>("7d");
  const [grouped, setGrouped] = useState(false);
  const hours = RANGES.find((r) => r.key === range)!.hours;
  const { start, end } = windowFor(hours);

  const { markAlertsRead } = useApp();
  const { data: alerts } = useSWR("alerts-latest", api.alertsLatest, {
    refreshInterval: 30000,
  });
  // Categorized rows for the per-day .txt export (across the full alert history).
  const reportEvents = useMemo(() => alertsToReportEvents(alerts ?? []), [alerts]);

  // Viewing this page is what "sees" the alerts: clear the unread badge by
  // advancing the seen-marker to the newest alert, and keep it cleared as fresh
  // alerts arrive while the page stays open.
  const newestAlertAt = useMemo(
    () =>
      (alerts ?? []).reduce(
        (max, a) =>
          new Date(a.timestamp).getTime() > new Date(max || 0).getTime() ? a.timestamp : max,
        ""
      ),
    [alerts]
  );
  useEffect(() => {
    if (newestAlertAt) markAlertsRead(newestAlertAt);
  }, [newestAlertAt, markAlertsRead]);

  const {
    data: events,
    isLoading,
    error,
  } = useSWR(["events", range], () => api.events(start, end), {
    refreshInterval: 60000,
  });

  return (
    <div className="space-y-4">
    <div className="grid gap-4 lg:grid-cols-3">
      {/* Active alerts */}
      <aside className="rounded-lg border border-surface-border bg-surface-card p-4 lg:col-span-1">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <h2 className="text-xs uppercase tracking-wider text-slate-500">Alerts</h2>
            {alerts && alerts.length > 0 && (
              <span className="rounded bg-surface-muted px-2 py-0.5 text-xs font-semibold text-slate-400">
                {alerts.length}
              </span>
            )}
          </div>
          <ExportEventsButton events={reportEvents} />
        </div>
        <div className="max-h-[36rem] overflow-y-auto">
          <AlertFeed alerts={alerts ?? []} />
        </div>
        <p className="mt-3 text-[11px] leading-relaxed text-slate-600">
          Full history, newest first. Derived from GOES X-ray &amp; proton flux,
          Kp/Dst geomagnetic indices, and e-CALLISTO radio bursts. Times are UTC.
        </p>
      </aside>

      {/* Event timeline */}
      <section className="rounded-lg border border-surface-border bg-surface-card p-4 lg:col-span-2">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-xs uppercase tracking-wider text-slate-500">
            Event Timeline
            {events && (
              <span className="ml-2 font-mono text-slate-400">{events.length}</span>
            )}
          </h2>
          <div className="flex flex-wrap items-center gap-1">
            <button
              onClick={() => setGrouped((g) => !g)}
              title="Merge related events (e.g. a flare and its radio burst) into one cluster"
              className={clsx(
                "mr-2 flex items-center gap-1.5 rounded px-3 py-1 text-xs transition-colors",
                grouped
                  ? "bg-accent-blue/20 text-accent-blue"
                  : "text-slate-500 hover:bg-surface-muted hover:text-slate-300"
              )}
            >
              <Link2 className="h-3.5 w-3.5" />
              Group related
            </button>
            {RANGES.map((r) => (
              <button
                key={r.key}
                onClick={() => setRange(r.key)}
                className={clsx(
                  "rounded px-3 py-1 text-xs transition-colors",
                  range === r.key
                    ? "bg-accent-blue/20 text-accent-blue"
                    : "text-slate-500 hover:bg-surface-muted hover:text-slate-300"
                )}
              >
                {r.label}
              </button>
            ))}
          </div>
        </div>

        {/* Cap the list height (like the alerts feed) so a long event record
            doesn't push the histograms far down the page — scroll within instead. */}
        <div className="max-h-[36rem] overflow-y-auto pr-1">
          {error ? (
            <div className="flex h-48 items-center justify-center text-sm text-accent-red">
              Failed to load events
            </div>
          ) : isLoading ? (
            <div className="flex h-48 items-center justify-center text-sm text-slate-600">
              Loading events…
            </div>
          ) : (
            <EventTimeline events={events ?? []} grouped={grouped} />
          )}
        </div>
      </section>
    </div>

      {/* Per-parameter activity histograms for visual correlation */}
      <ActivityHistograms />
    </div>
  );
}

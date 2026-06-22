"use client";

import { useMemo, useState } from "react";
import useSWR from "swr";
import { clsx } from "clsx";
import { api } from "@/lib/api";
import { windowFor } from "@/lib/formatting";
import { alertsToReportEvents } from "@/lib/exportEvents";
import { AlertFeed } from "@/components/alerts/AlertFeed";
import { EventTimeline } from "@/components/events/EventTimeline";
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
  const hours = RANGES.find((r) => r.key === range)!.hours;
  const { start, end } = windowFor(hours);

  const { data: alerts } = useSWR("alerts-latest", api.alertsLatest, {
    refreshInterval: 30000,
  });
  // Categorized rows for the per-day .txt export (across the full alert history).
  const reportEvents = useMemo(() => alertsToReportEvents(alerts ?? []), [alerts]);

  const {
    data: events,
    isLoading,
    error,
  } = useSWR(["events", range], () => api.events(start, end), {
    refreshInterval: 60000,
  });

  return (
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
          <div className="flex gap-1">
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

        {error ? (
          <div className="flex h-48 items-center justify-center text-sm text-accent-red">
            Failed to load events
          </div>
        ) : isLoading ? (
          <div className="flex h-48 items-center justify-center text-sm text-slate-600">
            Loading events…
          </div>
        ) : (
          <EventTimeline events={events ?? []} />
        )}
      </section>
    </div>
  );
}

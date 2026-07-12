"use client";

import { useState } from "react";
import useSWR from "swr";
import { clsx } from "clsx";
import { History } from "lucide-react";

import { api } from "@/lib/api";
import { relativeTime, scaleBadgeClass } from "@/lib/scales";
import type { CmeItem } from "@/lib/types";

/** YYYY-MM-DD for a Date, in the browser's local zone (matches <input type=date>). */
function isoDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

/** N days before today (today = offset 0), as YYYY-MM-DD. */
function daysAgo(n: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - n);
  return isoDate(d);
}

const PRESETS = [
  { label: "7 days", days: 7 },
  { label: "14 days", days: 14 },
  { label: "30 days", days: 30 },
];

/** Arrival cell for the history view: emphasises whether the CME has arrived. */
function PastArrival({ cme }: { cme: CmeItem }) {
  if (!cme.is_earth_directed || !cme.predicted_arrival_time) {
    return <span className="text-slate-600">—</span>;
  }
  const arrived = new Date(cme.predicted_arrival_time).getTime() < Date.now();
  const stamp = cme.predicted_arrival_time.slice(5, 16).replace("T", " ");
  return (
    <span className={clsx("font-mono", arrived ? "text-slate-400" : "text-accent-orange")}>
      {stamp} UTC{" "}
      <span className="text-[10px]">
        {arrived ? "· arrived" : `(${relativeTime(cme.predicted_arrival_time)})`}
      </span>
    </span>
  );
}

/**
 * Past CMEs from the NASA DONKI catalog over a user-chosen window. Unlike the
 * upcoming CmeList (which leads with inbound Earth-directed events), this is a
 * historical log of every catalogued eruption — Earth-directed or not — with
 * whether its predicted Earth arrival has already passed. Windows older than
 * the retained rolling catalog are fetched on demand by the backend.
 */
export function PastCmeList() {
  // Default to the last 7 days ending today (UTC).
  const [start, setStart] = useState(() => daysAgo(7));
  const [end, setEnd] = useState(() => daysAgo(0));

  const { data, isLoading, error } = useSWR(
    ["forecast-cmes-history", start, end],
    () => api.forecastCmesHistory(start, end),
    { refreshInterval: 300000, keepPreviousData: true }
  );

  const cmes = data?.cmes ?? [];
  const earthDirected = cmes.filter((c) => c.is_earth_directed).length;
  const activePreset = PRESETS.find((p) => start === daysAgo(p.days) && end === daysAgo(0));

  return (
    <div className="flex h-full flex-col rounded-lg border border-surface-border bg-surface-card p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h3 className="flex items-center gap-1.5 text-xs uppercase tracking-wider text-slate-500">
          <History className="h-3.5 w-3.5" />
          Past Coronal Mass Ejections
        </h3>
        <span className="text-[10px] text-slate-600">NASA DONKI catalog</span>
      </div>

      {/* Range controls: quick presets + custom start/end dates. */}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="flex gap-1">
          {PRESETS.map((p) => (
            <button
              key={p.days}
              type="button"
              onClick={() => {
                setStart(daysAgo(p.days));
                setEnd(daysAgo(0));
              }}
              className={clsx(
                "rounded border px-2 py-1 text-[11px] transition-colors",
                activePreset?.days === p.days
                  ? "border-accent-blue/50 bg-accent-blue/10 text-accent-blue"
                  : "border-surface-border text-slate-400 hover:text-slate-200"
              )}
            >
              {p.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1.5 text-[11px] text-slate-500">
          <input
            type="date"
            value={start}
            max={end}
            onChange={(e) => setStart(e.target.value)}
            className="rounded border border-surface-border bg-surface-muted px-1.5 py-1 text-slate-300 [color-scheme:dark]"
            aria-label="Start date"
          />
          <span>→</span>
          <input
            type="date"
            value={end}
            min={start}
            max={daysAgo(0)}
            onChange={(e) => setEnd(e.target.value)}
            className="rounded border border-surface-border bg-surface-muted px-1.5 py-1 text-slate-300 [color-scheme:dark]"
            aria-label="End date"
          />
        </div>
        {!isLoading && cmes.length > 0 && (
          <span className="ml-auto text-[10px] text-slate-600">
            {cmes.length} CMEs · {earthDirected} Earth-directed
          </span>
        )}
      </div>

      {error ? (
        <p className="py-6 text-center text-xs text-red-400">
          Could not load CME history for this window
        </p>
      ) : isLoading ? (
        <div className="h-24 animate-pulse rounded bg-surface-muted" />
      ) : cmes.length === 0 ? (
        <p className="py-6 text-center text-xs text-slate-600">
          No CMEs catalogued in this window
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-surface-border text-[10px] uppercase tracking-wider text-slate-600">
                <th className="py-1.5 pr-3 font-medium">Start (UTC)</th>
                <th className="py-1.5 pr-3 font-medium">Source</th>
                <th className="py-1.5 pr-3 font-medium">Speed</th>
                <th className="py-1.5 pr-3 font-medium">Width</th>
                <th className="py-1.5 pr-3 font-medium">Earth</th>
                <th className="py-1.5 pr-3 font-medium">Arrival</th>
                <th className="py-1.5 pr-3 font-medium">Max Kp</th>
              </tr>
            </thead>
            <tbody>
              {cmes.map((c) => (
                <tr
                  key={c.activity_id}
                  className={clsx(
                    "border-b border-surface-border/50",
                    c.is_earth_directed && "bg-accent-orange/5"
                  )}
                >
                  <td className="py-1.5 pr-3 font-mono text-slate-300">
                    {c.catalog_link ? (
                      <a
                        href={c.catalog_link}
                        target="_blank"
                        rel="noreferrer"
                        className="hover:text-accent-blue hover:underline"
                        title="Open in the DONKI catalog"
                      >
                        {c.start_time.slice(5, 16).replace("T", " ")}
                      </a>
                    ) : (
                      c.start_time.slice(5, 16).replace("T", " ")
                    )}
                  </td>
                  <td className="py-1.5 pr-3 text-slate-400">
                    {c.source_location ?? "—"}
                    {c.active_region != null && (
                      <span className="text-slate-600"> · AR{c.active_region}</span>
                    )}
                  </td>
                  <td className="py-1.5 pr-3 font-mono text-slate-300">
                    {c.speed != null ? `${c.speed.toFixed(0)} km/s` : "—"}
                  </td>
                  <td className="py-1.5 pr-3 font-mono text-slate-400">
                    {c.half_angle != null ? `±${c.half_angle.toFixed(0)}°` : "—"}
                  </td>
                  <td className="py-1.5 pr-3">
                    {c.is_earth_directed ? (
                      <span className="text-accent-orange">yes</span>
                    ) : (
                      <span className="text-slate-600">no</span>
                    )}
                  </td>
                  <td className="py-1.5 pr-3">
                    <PastArrival cme={c} />
                  </td>
                  <td className="py-1.5 pr-3">
                    {c.predicted_kp != null ? (
                      <span
                        className={clsx(
                          "rounded border px-1 py-0.5 font-mono text-[10px] font-bold",
                          scaleBadgeClass(Math.max(0, Math.round(c.predicted_kp) - 4))
                        )}
                      >
                        {c.predicted_kp.toFixed(0)}
                      </span>
                    ) : (
                      <span className="text-slate-600">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

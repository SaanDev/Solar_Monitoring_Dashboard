"use client";

import useSWR from "swr";
import { clsx } from "clsx";
import { Globe } from "lucide-react";

import { api } from "@/lib/api";
import { relativeTime, scaleBadgeClass } from "@/lib/scales";
import type { CmeItem } from "@/lib/types";

interface Props {
  days?: number;
  /** Compact embed (e.g. Coronagraph page): fewer columns, capped rows. */
  compact?: boolean;
  limit?: number;
}

function Arrival({ cme }: { cme: CmeItem }) {
  if (!cme.predicted_arrival_time) {
    return <span className="text-slate-600">—</span>;
  }
  const arrived = new Date(cme.predicted_arrival_time).getTime() < Date.now();
  return (
    <span className={clsx("font-mono", arrived ? "text-slate-500" : "text-accent-orange")}>
      {cme.predicted_arrival_time.slice(5, 16).replace("T", " ")} UTC{" "}
      <span className="text-[10px]">({relativeTime(cme.predicted_arrival_time)})</span>
    </span>
  );
}

/**
 * Recent CMEs from the NASA DONKI catalog. Earth-directed entries (an
 * ENLIL-predicted Earth arrival) are flagged and show the arrival countdown.
 */
export function CmeList({ days = 7, compact = false, limit }: Props) {
  const { data, isLoading } = useSWR(["forecast-cmes", days], () => api.forecastCmes(days), {
    refreshInterval: 300000,
  });

  const cmes = (data?.cmes ?? []).slice(0, limit);
  // Soonest predicted arrival first (list order is newest *launch* first).
  const inbound = cmes
    .filter(
      (c) =>
        c.is_earth_directed &&
        c.predicted_arrival_time &&
        new Date(c.predicted_arrival_time).getTime() > Date.now()
    )
    .sort(
      (a, b) =>
        new Date(a.predicted_arrival_time!).getTime() -
        new Date(b.predicted_arrival_time!).getTime()
    );

  return (
    <div className="flex h-full flex-col rounded-lg border border-surface-border bg-surface-card p-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-xs uppercase tracking-wider text-slate-500">
          Coronal Mass Ejections — last {days} days
        </h3>
        <span className="text-[10px] text-slate-600">NASA DONKI · WSA-ENLIL arrivals</span>
      </div>

      {inbound.length > 0 && (
        <div className="mb-2 flex items-center gap-2 rounded border border-accent-orange/40 bg-accent-orange/10 px-2 py-1.5 text-xs text-accent-orange">
          <Globe className="h-3.5 w-3.5 shrink-0" />
          {inbound.length === 1
            ? `1 Earth-directed CME inbound — predicted arrival ${relativeTime(
                inbound[0].predicted_arrival_time!
              )}`
            : `${inbound.length} Earth-directed CMEs inbound — next arrival ${relativeTime(
                inbound[0].predicted_arrival_time!
              )}`}
        </div>
      )}

      {isLoading ? (
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
                {!compact && <th className="py-1.5 pr-3 font-medium">Width</th>}
                <th className="py-1.5 pr-3 font-medium">Earth</th>
                <th className="py-1.5 pr-3 font-medium">Predicted Arrival</th>
                {!compact && <th className="py-1.5 pr-3 font-medium">Max Kp</th>}
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
                  {!compact && (
                    <td className="py-1.5 pr-3 font-mono text-slate-400">
                      {c.half_angle != null ? `±${c.half_angle.toFixed(0)}°` : "—"}
                    </td>
                  )}
                  <td className="py-1.5 pr-3">
                    {c.is_earth_directed ? (
                      <span className="text-accent-orange">yes</span>
                    ) : (
                      <span className="text-slate-600">no</span>
                    )}
                  </td>
                  <td className="py-1.5 pr-3">
                    <Arrival cme={c} />
                  </td>
                  {!compact && (
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
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

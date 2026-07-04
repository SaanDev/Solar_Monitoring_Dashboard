"use client";

import { useState } from "react";
import useSWR from "swr";
import { clsx } from "clsx";

import { api } from "@/lib/api";
import { scaleBadgeClass, scaleLevel } from "@/lib/scales";
import { KpForecastChart } from "@/components/charts/KpForecastChart";
import { RangeSelector, type RangeOption } from "@/components/charts/RangeSelector";

const RANGES: readonly RangeOption[] = [
  { key: "6-hour", label: "6H", hours: 6 },
  { key: "1-day", label: "1D", hours: 24 },
  { key: "3-day", label: "3D", hours: 72 },
  { key: "7-day", label: "7D", hours: 168 },
];

/**
 * Predicted Kp from real-time solar-wind coupling (Newell), computed by the
 * backend from L1 speed/density/IMF — a ~1-3 h lead on the measured Kp.
 */
export function KpForecastPanel() {
  const [range, setRange] = useState("1-day");
  const { data, isLoading } = useSWR(
    ["forecast-kp", range],
    () => api.forecastKp(range),
    { refreshInterval: 60000 }
  );

  const latest = data?.latest;
  const kp = latest?.kp;
  const g = latest?.g_scale;

  return (
    <div className="flex h-full flex-col rounded-lg border border-surface-border bg-surface-card p-4">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-xs uppercase tracking-wider text-slate-500">
          Predicted Kp — Solar-Wind Coupling
        </h3>
        <RangeSelector options={RANGES} value={range} onChange={setRange} />
      </div>

      <div className="mb-3 flex items-baseline gap-3">
        <span
          className={clsx(
            "font-mono text-3xl font-bold",
            kp != null && kp >= 5
              ? "text-accent-red"
              : kp != null && kp >= 4
                ? "text-accent-orange"
                : "text-accent-purple"
          )}
        >
          {kp != null ? kp.toFixed(1) : "—"}
        </span>
        <span
          className={clsx(
            "rounded border px-1.5 py-0.5 font-mono text-xs font-bold",
            scaleBadgeClass(g ? scaleLevel(g.slice(1)) : 0)
          )}
        >
          {g ?? "quiet"}
        </span>
        <span className="text-xs text-slate-500">
          next ~1–3 h · Newell coupling, trailing-hour mean
          {latest?.time && (
            <span className="text-slate-600">
              {" "}
              · {latest.time.slice(0, 16).replace("T", " ")} UTC
            </span>
          )}
        </span>
      </div>

      <div className="min-h-[16rem] flex-1">
        <KpForecastChart data={data?.data ?? []} loading={isLoading} />
      </div>
    </div>
  );
}

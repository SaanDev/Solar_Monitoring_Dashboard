"use client";

import { useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import { SolarWindSpeedChart } from "@/components/charts/SolarWindSpeedChart";
import { ImfChart } from "@/components/charts/ImfChart";
import { clsx } from "clsx";

// Window keys the backend slices from NOAA's 7-day propagated feed.
const RANGES = [
  { key: "2-hour", label: "2 hours" },
  { key: "6-hour", label: "6 hours" },
  { key: "1-day", label: "1 day" },
  { key: "3-day", label: "3 days" },
  { key: "7-day", label: "7 days" },
] as const;

type RangeKey = (typeof RANGES)[number]["key"];

export function SolarWindClient() {
  const [range, setRange] = useState<RangeKey>("1-day");

  const { data: series, isLoading } = useSWR(
    ["solar-wind-series", range],
    () => api.solarWindSeries(range),
    { refreshInterval: 60000 }
  );

  const { data: latest } = useSWR("solar-wind-latest", api.solarWindLatest, {
    refreshInterval: 60000,
  });

  const num = (v: number | null | undefined, digits: number) =>
    v != null ? v.toFixed(digits) : "—";

  return (
    <div className="space-y-4">
      {/* Header: live readings + range toggle */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-surface-border bg-surface-card p-4">
        <div className="flex flex-wrap items-center gap-6">
          <div>
            <p className="text-xs uppercase tracking-wider text-slate-500">Wind Speed</p>
            <p className="font-mono text-2xl font-bold text-accent-cyan">
              {num(latest?.speed, 0)}
              <span className="ml-1 text-sm font-normal text-slate-500">km/s</span>
            </p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-wider text-slate-500">IMF Bt</p>
            <p className="font-mono text-2xl font-bold text-slate-300">
              {num(latest?.bt, 1)}
              <span className="ml-1 text-sm font-normal text-slate-500">nT</span>
            </p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-wider text-slate-500">IMF Bz</p>
            <p
              className={clsx(
                "font-mono text-2xl font-bold",
                // Southward (negative) Bz couples with the magnetosphere — flag it.
                latest?.bz != null && latest.bz < 0 ? "text-accent-red" : "text-accent-green"
              )}
            >
              {num(latest?.bz, 1)}
              <span className="ml-1 text-sm font-normal text-slate-500">nT</span>
            </p>
          </div>
          <div className="text-xs text-slate-500">
            <p>Source: NOAA SWPC · real-time L1 solar wind</p>
            {latest?.time && (
              <p className="text-slate-600">
                Updated {latest.time.slice(0, 19).replace("T", " ")} UTC
              </p>
            )}
          </div>
        </div>

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

      <div className="rounded-lg border border-surface-border bg-surface-card p-4">
        <h2 className="mb-3 text-xs uppercase tracking-wider text-slate-500">
          Solar Wind Speed
        </h2>
        <div className="h-72">
          <SolarWindSpeedChart data={series?.data ?? []} loading={isLoading} />
        </div>
      </div>

      <div className="rounded-lg border border-surface-border bg-surface-card p-4">
        <h2 className="mb-3 text-xs uppercase tracking-wider text-slate-500">
          IMF Bt &amp; Bz
        </h2>
        <div className="h-72">
          <ImfChart data={series?.data ?? []} loading={isLoading} />
        </div>
      </div>
    </div>
  );
}

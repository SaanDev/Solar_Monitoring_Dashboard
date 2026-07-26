"use client";

import { useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { api } from "@/lib/api";
import { windowFor } from "@/lib/formatting";
import { KpChart } from "@/components/charts/KpChart";
import { DstChart } from "@/components/charts/DstChart";
import { clsx } from "clsx";

const RANGES = [
  { key: "6h", label: "6 hours", hours: 6 },
  { key: "1d", label: "1 day", hours: 24 },
  { key: "3d", label: "3 days", hours: 72 },
  { key: "7d", label: "7 days", hours: 168 },
] as const;

type RangeKey = (typeof RANGES)[number]["key"];

export function GeomagneticClient() {
  const [range, setRange] = useState<RangeKey>("3d");
  const hours = RANGES.find((r) => r.key === range)!.hours;
  const { start, end } = windowFor(hours);

  const { data: kpData, isLoading: kpLoading } = useSWR(
    ["kp", range],
    () => api.kp(start, end),
    { refreshInterval: 180000, keepPreviousData: true }
  );
  const { data: dstData, isLoading: dstLoading } = useSWR(
    ["dst", range],
    () => api.dst(start, end),
    { refreshInterval: 600000, keepPreviousData: true }
  );
  const { data: kpLatest } = useSWR("kp-latest", api.kpLatest, { refreshInterval: 180000 });
  const { data: dstLatest } = useSWR("dst-latest", api.dstLatest, { refreshInterval: 600000 });
  // Forward-looking counterpart to the measured Kp (Newell coupling forecast).
  const { data: kpForecast } = useSWR(
    "forecast-kp-geomag",
    () => api.forecastKp("2-hour"),
    { refreshInterval: 60000 }
  );
  const predictedKp = kpForecast?.latest?.kp;

  return (
    <div className="space-y-4">
      {/* Header: live values + range toggle */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-surface-border bg-surface-card p-4">
        <div className="flex items-center gap-6">
          <div>
            <p className="text-xs uppercase tracking-wider text-slate-500">Current Kp</p>
            <p className="font-mono text-2xl font-bold text-accent-cyan">
              {kpLatest?.kp != null ? kpLatest.kp.toFixed(2) : "—"}
              {kpLatest?.g_scale && (
                <span className="ml-2 rounded bg-accent-orange/20 px-2 py-0.5 text-sm text-accent-orange">
                  {kpLatest.g_scale}
                </span>
              )}
            </p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-wider text-slate-500">Current Dst</p>
            <p className="font-mono text-2xl font-bold text-accent-cyan">
              {dstLatest?.dst != null ? `${dstLatest.dst.toFixed(0)} nT` : "—"}
              {dstLatest?.storm_level && (
                <span className="ml-2 rounded bg-accent-red/20 px-2 py-0.5 text-sm text-accent-red">
                  {dstLatest.storm_level}
                </span>
              )}
            </p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-wider text-slate-500">
              Predicted Kp (~1–3 h)
            </p>
            <p
              className={clsx(
                "font-mono text-2xl font-bold",
                predictedKp != null && predictedKp >= 5
                  ? "text-accent-red"
                  : "text-accent-purple"
              )}
            >
              {predictedKp != null ? predictedKp.toFixed(1) : "—"}
              {kpForecast?.latest?.g_scale && (
                <span className="ml-2 rounded bg-accent-red/20 px-2 py-0.5 text-sm text-accent-red">
                  {kpForecast.latest.g_scale}
                </span>
              )}
            </p>
            <Link href="/forecast" className="text-[10px] text-accent-blue hover:underline">
              solar-wind coupling forecast →
            </Link>
          </div>
          <div className="text-xs text-slate-600">
            <p>Kp source: NOAA SWPC</p>
            <p>Dst source: WDC Kyoto (quicklook)</p>
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
          Planetary K-index (Kp)
        </h2>
        <div className="h-60">
          <KpChart data={kpData ?? []} loading={kpLoading} />
        </div>
      </div>

      <div className="rounded-lg border border-surface-border bg-surface-card p-4">
        <h2 className="mb-3 text-xs uppercase tracking-wider text-slate-500">Dst Index</h2>
        <div className="h-60">
          <DstChart data={dstData ?? []} loading={dstLoading} />
        </div>
      </div>
    </div>
  );
}

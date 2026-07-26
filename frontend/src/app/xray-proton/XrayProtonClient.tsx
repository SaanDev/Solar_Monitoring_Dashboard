"use client";

import { useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import { windowFor } from "@/lib/formatting";
import { GoesXrsChart } from "@/components/charts/GoesXrsChart";
import { ProtonFluxChart } from "@/components/charts/ProtonFluxChart";
import { clsx } from "clsx";

const RANGES = [
  { key: "6h", label: "6 hours", hours: 6 },
  { key: "1d", label: "1 day", hours: 24 },
  { key: "3d", label: "3 days", hours: 72 },
  { key: "7d", label: "7 days", hours: 168 },
] as const;

type RangeKey = (typeof RANGES)[number]["key"];

export function XrayProtonClient() {
  const [range, setRange] = useState<RangeKey>("6h");
  const hours = RANGES.find((r) => r.key === range)!.hours;
  const { start, end } = windowFor(hours);

  const { data: xrs, isLoading: xrsLoading } = useSWR(
    ["goes-xrs", range],
    () => api.goesXrs(start, end),
    { refreshInterval: 60000, keepPreviousData: true }
  );

  const { data: latest } = useSWR("goes-xrs-latest", api.goesXrsLatest, {
    refreshInterval: 60000,
  });

  const { data: proton, isLoading: protonLoading } = useSWR(
    ["goes-proton", range],
    () => api.goesProton(start, end),
    { refreshInterval: 60000, keepPreviousData: true }
  );

  const { data: protonLatest } = useSWR("goes-proton-latest", api.goesProtonLatest, {
    refreshInterval: 60000,
  });

  const satellite = xrs?.satellite ?? latest?.satellite;

  return (
    <div className="space-y-4">
      {/* Header: live flare class + range toggle */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-surface-border bg-surface-card p-4">
        <div className="flex items-center gap-6">
          <div>
            <p className="text-xs uppercase tracking-wider text-slate-500">Current X-ray Class</p>
            <p className="font-mono text-2xl font-bold text-accent-orange">
              {latest?.flare_class ?? "—"}
            </p>
          </div>
          <div className="text-xs text-slate-500">
            <p>Source: NOAA SWPC{satellite ? ` · GOES-${satellite}` : ""}</p>
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
          GOES X-ray Flux
        </h2>
        <div className="h-72">
          <GoesXrsChart data={xrs?.data ?? []} loading={xrsLoading} />
        </div>
      </div>

      <div className="rounded-lg border border-surface-border bg-surface-card p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-xs uppercase tracking-wider text-slate-500">GOES Proton Flux</h2>
          <div className="flex items-center gap-4 text-xs">
            <span className="text-slate-500">
              &ge;10 MeV:{" "}
              <span className="font-mono text-slate-200">
                {protonLatest?.flux_gt10 != null ? protonLatest.flux_gt10.toFixed(3) : "—"} pfu
              </span>
            </span>
            <span
              className={clsx(
                "rounded px-2 py-0.5 font-mono",
                protonLatest?.event_in_progress
                  ? "bg-accent-red/20 text-accent-red"
                  : "bg-accent-green/10 text-accent-green"
              )}
            >
              {protonLatest?.storm_scale ?? "No storm (S0)"}
            </span>
          </div>
        </div>
        <div className="h-64">
          <ProtonFluxChart data={proton?.data ?? []} loading={protonLoading} />
        </div>
      </div>
    </div>
  );
}

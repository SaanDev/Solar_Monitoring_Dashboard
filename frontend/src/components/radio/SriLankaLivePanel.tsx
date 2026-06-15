"use client";

import useSWR from "swr";
import { api } from "@/lib/api";
import { formatUtcShort } from "@/lib/formatting";

const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function SriLankaLivePanel({
  heightClass = "min-h-[600px] flex-1",
}: {
  heightClass?: string;
}) {
  const { data, isLoading, error } = useSWR("sri-lanka-live", api.sriLankaLive, {
    refreshInterval: 300000, // 5 min
  });

  return (
    <div className="flex flex-1 flex-col rounded-lg border border-accent-cyan/30 bg-surface-card p-4">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-accent-cyan">
          <span className="h-2 w-2 animate-pulse rounded-full bg-accent-cyan" />
          Sri Lanka (ACCIMT) — Live Dynamic Spectrum
        </h2>
        {data && (
          <span className="text-xs text-slate-500">
            {data.start_time ? formatUtcShort(data.start_time) : "—"} ·{" "}
            {data.freq_min_mhz.toFixed(0)}–{data.freq_max_mhz.toFixed(0)} MHz
          </span>
        )}
      </div>

      <div className={heightClass}>
        {isLoading ? (
          <div className="h-full w-full animate-pulse rounded bg-surface-muted" />
        ) : error || !data ? (
          <div className="flex h-full items-center justify-center text-xs text-slate-600">
            No recent Sri Lanka data available
          </div>
        ) : (
          <img
            src={`${apiBase}${data.image_url}`}
            alt="Sri Lanka dynamic spectrum"
            className="h-full w-full rounded object-contain"
          />
        )}
      </div>
    </div>
  );
}

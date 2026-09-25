"use client";

import useSWR from "swr";
import { API_BASE, api } from "@/lib/api";
import { formatUtcShort } from "@/lib/formatting";
import { EmptyState } from "@/components/ui/EmptyState";

const apiBase = API_BASE;

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
        ) : error ? (
          // Previously collapsed into the "no recent data" message below, so a
          // 500 from the station read as a quiet Sun.
          <EmptyState
            tone="error"
            message="Could not reach the Sri Lanka (ACCIMT) feed."
          />
        ) : !data ? (
          <EmptyState message="No recent Sri Lanka data available." />
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

"use client";

import { useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import { SolarWindSpeedChart } from "@/components/charts/SolarWindSpeedChart";
import { ImfChart } from "@/components/charts/ImfChart";
import { RangeSelector, type RangeOption } from "@/components/charts/RangeSelector";

// Window keys the backend slices from NOAA's 7-day propagated feed; `hours`
// is unused for fetching but keeps the shared RangeOption shape.
const RANGES: readonly RangeOption[] = [
  { key: "2-hour", label: "2H", hours: 2 },
  { key: "6-hour", label: "6H", hours: 6 },
  { key: "1-day", label: "1D", hours: 24 },
  { key: "3-day", label: "3D", hours: 72 },
];

// Both cards share the SWR key, so with matching ranges they share one fetch.
function useSolarWindSeries(range: string) {
  return useSWR(["overview-solar-wind", range], () => api.solarWindSeries(range), {
    refreshInterval: 60000,
  });
}

export function OverviewSolarWindChart() {
  const [range, setRange] = useState("6-hour");
  const { data, isLoading } = useSolarWindSeries(range);

  return (
    <div className="flex h-full min-h-[20rem] flex-col rounded-lg border border-surface-border bg-surface-card p-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-xs uppercase tracking-wider text-slate-500">
          Solar Wind Speed
        </h3>
        <RangeSelector options={RANGES} value={range} onChange={setRange} />
      </div>
      <div className="flex-1">
        <SolarWindSpeedChart data={data?.data ?? []} loading={isLoading} />
      </div>
    </div>
  );
}

export function OverviewImfChart() {
  const [range, setRange] = useState("6-hour");
  const { data, isLoading } = useSolarWindSeries(range);

  return (
    <div className="flex h-full min-h-[20rem] flex-col rounded-lg border border-surface-border bg-surface-card p-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-xs uppercase tracking-wider text-slate-500">
          IMF Bt &amp; Bz
        </h3>
        <RangeSelector options={RANGES} value={range} onChange={setRange} />
      </div>
      <div className="flex-1">
        <ImfChart data={data?.data ?? []} loading={isLoading} />
      </div>
    </div>
  );
}

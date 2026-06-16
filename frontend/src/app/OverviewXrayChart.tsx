"use client";

import { useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import { GoesXrsChart } from "@/components/charts/GoesXrsChart";
import { RangeSelector, type RangeOption } from "@/components/charts/RangeSelector";
import { windowFor } from "@/lib/formatting";

const RANGES: readonly RangeOption[] = [
  { key: "6h", label: "6H", hours: 6 },
  { key: "12h", label: "12H", hours: 12 },
  { key: "3d", label: "3D", hours: 72 },
  { key: "7d", label: "7D", hours: 168 },
];

export function OverviewXrayChart() {
  const [range, setRange] = useState("6h");
  const hours = RANGES.find((r) => r.key === range)!.hours;
  const { start, end } = windowFor(hours);

  const { data, isLoading } = useSWR(
    ["overview-goes-xrs", range],
    () => api.goesXrs(start, end),
    { refreshInterval: 60000 }
  );

  return (
    <div className="flex h-full min-h-[20rem] flex-col rounded-lg border border-surface-border bg-surface-card p-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-xs uppercase tracking-wider text-slate-500">GOES X-ray Flux</h3>
        <RangeSelector options={RANGES} value={range} onChange={setRange} />
      </div>
      <div className="flex-1">
        <GoesXrsChart data={data?.data ?? []} loading={isLoading} />
      </div>
    </div>
  );
}

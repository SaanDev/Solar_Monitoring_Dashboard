"use client";

import { useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import { ElectronFluxChart } from "@/components/charts/ElectronFluxChart";
import { RangeSelector, type RangeOption } from "@/components/charts/RangeSelector";
import { UpdatingPill } from "@/components/ui/UpdatingPill";
import { windowFor } from "@/lib/formatting";

const RANGES: readonly RangeOption[] = [
  { key: "6h", label: "6H", hours: 6 },
  { key: "12h", label: "12H", hours: 12 },
  { key: "3d", label: "3D", hours: 72 },
  { key: "7d", label: "7D", hours: 168 },
];

export function OverviewElectronChart() {
  const [range, setRange] = useState("12h");
  const hours = RANGES.find((r) => r.key === range)!.hours;
  const { start, end } = windowFor(hours);

  const { data, isLoading, isValidating } = useSWR(
    ["overview-goes-electrons", range],
    () => api.goesElectrons(start, end),
    { refreshInterval: 60000, keepPreviousData: true }
  );

  return (
    <div className="flex h-full min-h-[20rem] flex-col rounded-lg border border-surface-border bg-surface-card p-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-xs uppercase tracking-wider text-slate-500">
          GOES Electron Flux (≥2 MeV)
        </h3>
        <div className="flex items-center gap-2">
          <UpdatingPill show={isValidating && !!data} inline />
          <RangeSelector options={RANGES} value={range} onChange={setRange} />
        </div>
      </div>
      <div className="flex-1">
        <ElectronFluxChart data={data?.data ?? []} loading={isLoading} />
      </div>
    </div>
  );
}

"use client";

import { useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import { KpChart } from "@/components/charts/KpChart";
import { DstChart } from "@/components/charts/DstChart";
import { RangeSelector, type RangeOption } from "@/components/charts/RangeSelector";
import { UpdatingPill } from "@/components/ui/UpdatingPill";
import { windowFor } from "@/lib/formatting";

// Geomagnetic indices change slowly, so offer longer "time-extended" windows.
const RANGES: readonly RangeOption[] = [
  { key: "1d", label: "1D", hours: 24 },
  { key: "3d", label: "3D", hours: 72 },
  { key: "7d", label: "7D", hours: 168 },
  { key: "30d", label: "30D", hours: 720 },
];

export function OverviewKpChart() {
  const [range, setRange] = useState("3d");
  const hours = RANGES.find((r) => r.key === range)!.hours;
  const { start, end } = windowFor(hours);

  const { data, isLoading, isValidating } = useSWR(["overview-kp", range], () => api.kp(start, end), {
    refreshInterval: 180000,
    keepPreviousData: true,
  });

  return (
    <div className="flex h-full min-h-[16rem] flex-col rounded-lg border border-surface-border bg-surface-card p-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-xs uppercase tracking-wider text-slate-500">Kp Index</h3>
        <div className="flex items-center gap-2">
          <UpdatingPill show={isValidating && !!data} inline />
          <RangeSelector options={RANGES} value={range} onChange={setRange} />
        </div>
      </div>
      <div className="flex-1">
        <KpChart data={data ?? []} loading={isLoading} />
      </div>
    </div>
  );
}

export function OverviewDstChart() {
  const [range, setRange] = useState("3d");
  const hours = RANGES.find((r) => r.key === range)!.hours;
  const { start, end } = windowFor(hours);

  const { data, isLoading, isValidating } = useSWR(["overview-dst", range], () => api.dst(start, end), {
    refreshInterval: 600000,
    keepPreviousData: true,
  });

  return (
    <div className="flex h-full min-h-[16rem] flex-col rounded-lg border border-surface-border bg-surface-card p-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-xs uppercase tracking-wider text-slate-500">Dst Index</h3>
        <div className="flex items-center gap-2">
          <UpdatingPill show={isValidating && !!data} inline />
          <RangeSelector options={RANGES} value={range} onChange={setRange} />
        </div>
      </div>
      <div className="flex-1">
        <DstChart data={data ?? []} loading={isLoading} />
      </div>
    </div>
  );
}

"use client";

import { useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import { SunspotChart } from "@/components/charts/SunspotChart";
import { RangeSelector, type RangeOption } from "@/components/charts/RangeSelector";

// Reuse RangeSelector purely as a two-way toggle (hours is unused here).
const SCOPES: readonly RangeOption[] = [
  { key: "cycle", label: "Cycle", hours: 0 },
  { key: "recent", label: "Recent", hours: 0 },
];

export function OverviewSunspotChart() {
  const [scope, setScope] = useState<"cycle" | "recent">("cycle");

  const { data, isLoading } = useSWR(
    ["overview-sunspot", scope],
    () => api.sunspotSeries(scope),
    { refreshInterval: 300000 }
  );

  return (
    <div className="flex h-full min-h-[20rem] flex-col rounded-lg border border-surface-border bg-surface-card p-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-xs uppercase tracking-wider text-slate-500">
          Sunspot Number Progression
        </h3>
        <RangeSelector
          options={SCOPES}
          value={scope}
          onChange={(k) => setScope(k as "cycle" | "recent")}
        />
      </div>
      <div className="flex-1">
        <SunspotChart data={data?.data ?? []} scope={scope} loading={isLoading} />
      </div>
    </div>
  );
}

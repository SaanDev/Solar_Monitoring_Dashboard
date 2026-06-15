"use client";

import useSWR from "swr";
import { api } from "@/lib/api";
import { GoesXrsChart } from "@/components/charts/GoesXrsChart";

const now = new Date();
const end = now.toISOString().slice(0, 19) + "Z";
const start = new Date(now.getTime() - 6 * 3600 * 1000).toISOString().slice(0, 19) + "Z";

export function OverviewXrayChart() {
  const { data, isLoading } = useSWR(
    "overview-goes-xrs",
    () => api.goesXrs(start, end),
    { refreshInterval: 60000 }
  );

  return (
    <div className="h-96 rounded-lg border border-surface-border bg-surface-card p-4 flex flex-col">
      <h3 className="mb-2 text-xs uppercase tracking-wider text-slate-500">
        GOES X-ray Flux (6h)
      </h3>
      <div className="flex-1">
        <GoesXrsChart data={data?.data ?? []} loading={isLoading} />
      </div>
    </div>
  );
}

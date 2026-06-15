"use client";

import useSWR from "swr";
import { api } from "@/lib/api";
import { KpChart } from "@/components/charts/KpChart";
import { DstChart } from "@/components/charts/DstChart";

const now = new Date();
const end = now.toISOString().slice(0, 19) + "Z";
const start = new Date(now.getTime() - 3 * 24 * 3600 * 1000).toISOString().slice(0, 19) + "Z";

export function OverviewKpChart() {
  const { data, isLoading } = useSWR("overview-kp", () => api.kp(start, end), {
    refreshInterval: 180000,
  });
  return (
    <div className="h-96 rounded-lg border border-surface-border bg-surface-card p-4 flex flex-col">
      <h3 className="mb-2 text-xs uppercase tracking-wider text-slate-500">Kp Index (3d)</h3>
      <div className="flex-1">
        <KpChart data={data ?? []} loading={isLoading} />
      </div>
    </div>
  );
}

export function OverviewDstChart() {
  const { data, isLoading } = useSWR("overview-dst", () => api.dst(start, end), {
    refreshInterval: 600000,
  });
  return (
    <div className="h-96 rounded-lg border border-surface-border bg-surface-card p-4 flex flex-col">
      <h3 className="mb-2 text-xs uppercase tracking-wider text-slate-500">Dst Index (3d)</h3>
      <div className="flex-1">
        <DstChart data={data ?? []} loading={isLoading} />
      </div>
    </div>
  );
}

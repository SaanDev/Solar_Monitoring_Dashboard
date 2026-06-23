"use client";

import useSWR from "swr";
import { api } from "@/lib/api";
import { RadioFluxChart } from "@/components/charts/RadioFluxChart";

export function OverviewRadioFlux() {
  const { data, isLoading } = useSWR("overview-f107", api.f107, {
    refreshInterval: 300000,
  });

  const latest = data?.data?.length ? data.data[data.data.length - 1].flux : null;

  return (
    <div className="flex h-full min-h-[20rem] flex-col rounded-lg border border-surface-border bg-surface-card p-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-xs uppercase tracking-wider text-slate-500">
          F10.7 Radio Flux
        </h3>
        <span className="font-mono text-xs text-slate-400">
          {latest != null ? `${latest.toFixed(0)} sfu` : "— sfu"}
          <span className="ml-1 text-slate-600">· 30d</span>
        </span>
      </div>
      <div className="flex-1">
        <RadioFluxChart data={data?.data ?? []} loading={isLoading} />
      </div>
    </div>
  );
}

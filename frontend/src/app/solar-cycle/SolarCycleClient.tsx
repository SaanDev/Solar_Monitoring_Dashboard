"use client";

import useSWR from "swr";

import { api } from "@/lib/api";
import { SolarCycleChart } from "@/components/charts/SolarCycleChart";

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-surface-border bg-surface-card p-4">
      <p className="text-xs uppercase tracking-wider text-slate-500">{label}</p>
      <p className="font-mono text-2xl font-bold text-accent-cyan">{value}</p>
      {hint && <p className="text-xs text-slate-600">{hint}</p>}
    </div>
  );
}

export function SolarCycleClient() {
  const { data, isLoading } = useSWR("solar-cycle", api.solarCycle, {
    refreshInterval: 6 * 3600 * 1000,
  });

  const observed = data?.observed ?? [];
  const predicted = data?.predicted ?? [];

  const latest = [...observed].reverse().find((p) => p.ssn != null);
  const latestSmoothed = [...observed].reverse().find((p) => p.smoothed_ssn != null);
  const peak = predicted.reduce(
    (best, p) => (p.ssn != null && (best == null || p.ssn > (best.ssn ?? 0)) ? p : best),
    null as (typeof predicted)[number] | null
  );
  const monthsSinceStart = data
    ? Math.round(
        (Date.now() - new Date(`${data.cycle25_start}-01T00:00:00Z`).getTime()) /
          (30.44 * 86400_000)
      )
    : null;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat
          label="Latest Monthly SSN"
          value={latest?.ssn != null ? latest.ssn.toFixed(0) : "—"}
          hint={latest?.month}
        />
        <Stat
          label="Latest Smoothed SSN"
          value={latestSmoothed?.smoothed_ssn != null ? latestSmoothed.smoothed_ssn.toFixed(0) : "—"}
          hint={`${latestSmoothed?.month ?? "—"} · trails ~6 months`}
        />
        <Stat
          label="Predicted Remaining Peak"
          value={peak?.ssn != null ? peak.ssn.toFixed(0) : "—"}
          hint={peak ? `${peak.month} (NOAA panel)` : undefined}
        />
        <Stat
          label="Cycle 25 Age"
          value={monthsSinceStart != null ? `${monthsSinceStart} mo` : "—"}
          hint={`since minimum ${data?.cycle25_start ?? ""}`}
        />
      </div>

      <div className="rounded-lg border border-surface-border bg-surface-card p-4">
        <h2 className="mb-3 text-xs uppercase tracking-wider text-slate-500">
          Sunspot Number — Cycle 24 &amp; 25 observed vs. Cycle 25 prediction
        </h2>
        <div className="h-80">
          <SolarCycleChart
            observed={observed}
            predicted={predicted}
            metric="ssn"
            loading={isLoading}
          />
        </div>
      </div>

      <div className="rounded-lg border border-surface-border bg-surface-card p-4">
        <h2 className="mb-3 text-xs uppercase tracking-wider text-slate-500">
          F10.7 Radio Flux — observed vs. prediction
        </h2>
        <div className="h-80">
          <SolarCycleChart
            observed={observed}
            predicted={predicted}
            metric="f107"
            loading={isLoading}
          />
        </div>
      </div>

      <p className="text-[10px] text-slate-600">
        Observed: SILSO monthly mean sunspot number + Penticton F10.7 via NOAA SWPC.
        Prediction: official NOAA/NASA Solar Cycle 25 panel, with the shaded band as
        the stated uncertainty range.
      </p>
    </div>
  );
}

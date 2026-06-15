"use client";

import useSWR from "swr";
import { api } from "@/lib/api";
import { MetricCard } from "@/components/cards/MetricCard";
import { Activity, Zap, Compass, Wind, Bell } from "lucide-react";

export function OverviewMetrics() {
  const { data, isLoading } = useSWR("summary-latest", api.summaryLatest, {
    refreshInterval: 60000,
  });

  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 xl:grid-cols-6">
      <MetricCard
        label="X-ray Class"
        value={data?.goes_xray_class ?? null}
        icon={Zap}
        severity={xraySeverity(data?.goes_xray_class)}
        loading={isLoading}
      />
      <MetricCard
        label="Proton >10 MeV"
        value={data?.proton_flux_10mev != null ? data.proton_flux_10mev.toFixed(4) : null}
        unit="pfu"
        icon={Activity}
        loading={isLoading}
      />
      <MetricCard
        label="Kp Index"
        value={data?.kp_index ?? null}
        icon={Compass}
        loading={isLoading}
      />
      <MetricCard
        label="Dst Index"
        value={data?.dst_index ?? null}
        unit="nT"
        icon={Compass}
        loading={isLoading}
      />
      <MetricCard
        label="Solar Wind"
        value={data?.solar_wind_speed ?? null}
        unit="km/s"
        icon={Wind}
        loading={isLoading}
      />
      <MetricCard
        label="Active Alerts"
        value={data?.active_alerts ?? 0}
        icon={Bell}
        severity={data && data.active_alerts > 0 ? "warning" : "ok"}
        loading={isLoading}
      />
    </div>
  );
}

function xraySeverity(cls: string | null | undefined): "ok" | "watch" | "warning" | "critical" {
  if (!cls) return "ok";
  const band = cls[0];
  if (band === "X") return "critical";
  if (band === "M") return "warning";
  if (band === "C") return "watch";
  return "ok";
}

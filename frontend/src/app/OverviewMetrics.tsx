"use client";

import useSWR from "swr";
import { api } from "@/lib/api";
import { MetricCard } from "@/components/cards/MetricCard";
import { Activity, Zap, Compass, Wind, Bell } from "lucide-react";

export function OverviewMetrics() {
  const { data, isLoading, error } = useSWR("summary-latest", api.summaryLatest, {
    refreshInterval: 60000,
  });

  // No reading available: the fetch failed, or it resolved with nothing. Every
  // card below defaults to the green "ok" severity, so without this the whole
  // headline strip renders reassuringly green while the backend is down.
  const unavailable = Boolean(error) || (!isLoading && !data);
  const sev = <T extends "ok" | "watch" | "warning" | "critical">(s: T) =>
    unavailable ? ("unknown" as const) : s;

  return (
    // lg: added so 1280–1439px renders the intended single strip; previously it
    // jumped straight from 3-up to 6-up at xl and showed 3×2 in between.
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
      <MetricCard
        label="X-ray Class"
        value={data?.goes_xray_class ?? null}
        icon={Zap}
        severity={sev(xraySeverity(data?.goes_xray_class))}
        loading={isLoading}
      />
      <MetricCard
        label="Proton >10 MeV"
        value={data?.proton_flux_10mev != null ? data.proton_flux_10mev.toFixed(4) : null}
        unit="pfu"
        icon={Activity}
        severity={sev("ok")}
        loading={isLoading}
      />
      <MetricCard
        label="Kp Index"
        value={data?.kp_index ?? null}
        icon={Compass}
        severity={sev("ok")}
        loading={isLoading}
      />
      <MetricCard
        label="Dst Index"
        value={data?.dst_index ?? null}
        unit="nT"
        icon={Compass}
        severity={sev("ok")}
        loading={isLoading}
      />
      <MetricCard
        label="Solar Wind"
        value={data?.solar_wind_speed ?? null}
        unit="km/s"
        icon={Wind}
        severity={sev("ok")}
        loading={isLoading}
      />
      <MetricCard
        label="Active Alerts"
        // `?? 0` here would assert "zero active alerts" during an outage.
        value={data?.active_alerts ?? null}
        icon={Bell}
        severity={sev(data && data.active_alerts > 0 ? "warning" : "ok")}
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

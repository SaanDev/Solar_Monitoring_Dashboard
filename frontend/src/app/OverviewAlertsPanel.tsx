"use client";

import useSWR from "swr";
import Link from "next/link";
import { Activity, Bell, Compass, Radio, Sun, Wind, Zap } from "lucide-react";
import { clsx } from "clsx";

import { api } from "@/lib/api";
import { formatUtcShort } from "@/lib/formatting";
import type { Alert } from "@/lib/types";

const sevColor = {
  info: "text-accent-blue",
  watch: "text-accent-yellow",
  warning: "text-accent-orange",
  critical: "text-accent-red",
} as const;

function iconFor(a: Alert) {
  const t = `${a.type} ${a.message}`.toLowerCase();
  if (t.includes("radio")) return Radio;
  if (t.includes("flare") || t.includes("x-ray") || t.includes("xray")) return Zap;
  if (t.includes("cme") || t.includes("lasco") || t.includes("coronal")) return Sun;
  if (t.includes("geomag") || t.includes("kp") || t.includes("dst")) return Compass;
  if (t.includes("proton")) return Activity;
  if (t.includes("wind")) return Wind;
  return Bell;
}

export function OverviewAlertsPanel({ className }: { className?: string }) {
  const { data, isLoading } = useSWR("alerts-latest", api.alertsLatest, {
    refreshInterval: 60000,
  });
  const alerts = data ?? [];

  return (
    <div
      className={clsx(
        "flex flex-col rounded-lg border border-surface-border bg-surface-card p-4",
        className
      )}
    >
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-xs uppercase tracking-wider text-slate-500">Alerts &amp; Event Feed</h3>
        <Link href="/events" className="text-xs text-accent-blue hover:underline">
          View All →
        </Link>
      </div>

      <div className="min-h-[16rem] flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="h-12 animate-pulse rounded bg-surface-muted" />
            ))}
          </div>
        ) : alerts.length === 0 ? (
          <div className="flex h-32 items-center justify-center text-xs text-slate-600">
            No active alerts
          </div>
        ) : (
          <ul className="space-y-1">
            {alerts.map((a) => {
              const Icon = iconFor(a);
              return (
                <li
                  key={a.id}
                  className="flex items-start gap-2 rounded px-2 py-2 hover:bg-surface-muted"
                >
                  <Icon className={clsx("mt-0.5 h-4 w-4 shrink-0", sevColor[a.severity])} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <span className={clsx("truncate text-xs font-semibold", sevColor[a.severity])}>
                        {a.type}
                      </span>
                      <span className="shrink-0 text-[10px] text-slate-600">
                        {formatUtcShort(a.timestamp).slice(11)}
                      </span>
                    </div>
                    <p className="truncate text-xs text-slate-400">{a.message}</p>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}

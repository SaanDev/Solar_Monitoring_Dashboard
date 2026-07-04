"use client";

import Link from "next/link";
import useSWR from "swr";
import { clsx } from "clsx";
import { ArrowRight, Globe, TrendingUp } from "lucide-react";

import { api } from "@/lib/api";
import { relativeTime, scaleBadgeClass, scaleLevel } from "@/lib/scales";

/**
 * Compact forecast strip for the Overview: predicted Kp (solar-wind coupling),
 * the next Earth-directed CME arrival, and NOAA's 3-day G outlook, linking to
 * the full Forecast page.
 */
export function OverviewForecast() {
  const { data: kp } = useSWR("forecast-kp-overview", () => api.forecastKp("2-hour"), {
    refreshInterval: 60000,
  });
  const { data: cmes } = useSWR(["forecast-cmes", 7], () => api.forecastCmes(7), {
    refreshInterval: 300000,
  });
  const { data: scales } = useSWR("forecast-noaa-scales", api.forecastNoaaScales, {
    refreshInterval: 600000,
  });

  const predicted = kp?.latest?.kp;
  const inbound = (cmes?.cmes ?? [])
    .filter(
      (c) =>
        c.is_earth_directed &&
        c.predicted_arrival_time &&
        new Date(c.predicted_arrival_time).getTime() > Date.now()
    )
    .sort(
      (a, b) =>
        new Date(a.predicted_arrival_time!).getTime() -
        new Date(b.predicted_arrival_time!).getTime()
    );
  const next = inbound[0];

  return (
    <div className="flex flex-wrap items-center gap-x-8 gap-y-3 rounded-lg border border-surface-border bg-surface-card px-4 py-3">
      <div className="flex items-center gap-2">
        <TrendingUp className="h-4 w-4 shrink-0 text-accent-purple" />
        <div>
          <p className="text-[10px] uppercase tracking-widest text-slate-500">
            Predicted Kp (next ~1–3 h)
          </p>
          <p className="font-mono text-lg font-bold leading-tight">
            <span
              className={clsx(
                predicted != null && predicted >= 5
                  ? "text-accent-red"
                  : predicted != null && predicted >= 4
                    ? "text-accent-orange"
                    : "text-slate-200"
              )}
            >
              {predicted != null ? predicted.toFixed(1) : "—"}
            </span>
            {kp?.latest?.g_scale && (
              <span className="ml-2 rounded bg-accent-red/20 px-1.5 py-0.5 text-xs text-accent-red">
                {kp.latest.g_scale}
              </span>
            )}
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <Globe
          className={clsx(
            "h-4 w-4 shrink-0",
            next ? "text-accent-orange" : "text-slate-600"
          )}
        />
        <div>
          <p className="text-[10px] uppercase tracking-widest text-slate-500">
            Earth-Directed CME
          </p>
          {next ? (
            <p className="text-sm leading-tight text-accent-orange">
              arrival {relativeTime(next.predicted_arrival_time!)}
              <span className="ml-1 font-mono text-xs text-slate-500">
                ({next.predicted_arrival_time!.slice(5, 16).replace("T", " ")} UTC)
              </span>
            </p>
          ) : (
            <p className="text-sm leading-tight text-slate-500">none inbound</p>
          )}
        </div>
      </div>

      <div>
        <p className="mb-0.5 text-[10px] uppercase tracking-widest text-slate-500">
          NOAA 3-Day G Outlook
        </p>
        <div className="flex items-center gap-1.5">
          {(scales?.forecast ?? []).map((d, i) => (
            <span
              key={d.date ?? i}
              className={clsx(
                "rounded border px-1.5 py-0.5 font-mono text-xs font-bold",
                scaleBadgeClass(scaleLevel(d.g_scale))
              )}
              title={d.date ?? undefined}
            >
              G{scaleLevel(d.g_scale)}
            </span>
          ))}
          {!scales?.forecast?.length && <span className="text-sm text-slate-600">—</span>}
        </div>
      </div>

      <Link
        href="/forecast"
        className="ml-auto flex items-center gap-1 text-xs text-accent-blue hover:underline"
      >
        Full forecast <ArrowRight className="h-3 w-3" />
      </Link>
    </div>
  );
}

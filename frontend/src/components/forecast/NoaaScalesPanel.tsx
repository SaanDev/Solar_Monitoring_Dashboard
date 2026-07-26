"use client";

import useSWR from "swr";
import { clsx } from "clsx";

import { api } from "@/lib/api";
import { scaleBadgeClass, scaleLevel } from "@/lib/scales";
import type { NoaaScaleDay } from "@/lib/types";

function Badge({ prefix, scale }: { prefix: string; scale: string | null }) {
  const level = scaleLevel(scale);
  return (
    <span
      className={clsx(
        "inline-flex min-w-9 justify-center rounded border px-1.5 py-0.5 font-mono text-xs font-bold",
        scaleBadgeClass(level)
      )}
    >
      {prefix}
      {level}
    </span>
  );
}

function Prob({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="flex items-center justify-between text-[11px]">
      <span className="text-slate-500">{label}</span>
      <span
        className={clsx(
          "font-mono",
          value != null && value >= 50
            ? "text-accent-orange"
            : value != null && value >= 25
              ? "text-amber-500"
              : "text-slate-400"
        )}
      >
        {value != null ? `${value}%` : "—"}
      </span>
    </div>
  );
}

function dayName(date: string | null, index: number): string {
  if (index === 0) return "Today";
  if (!date) return `Day ${index + 1}`;
  return new Date(`${date}T00:00:00Z`).toLocaleDateString("en-US", {
    weekday: "short",
    timeZone: "UTC",
  });
}

/**
 * NOAA SWPC 3-day outlook: predicted G level plus flare (R) and radiation
 * storm (S) probabilities per day, with yesterday/today's observed maxima.
 */
export function NoaaScalesPanel() {
  const { data, isLoading } = useSWR("forecast-noaa-scales", api.forecastNoaaScales, {
    refreshInterval: 600000,
  });

  const days: NoaaScaleDay[] = data?.forecast ?? [];

  return (
    <div className="flex h-full flex-col rounded-lg border border-surface-border bg-surface-card p-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-xs uppercase tracking-wider text-slate-500">
          NOAA 3-Day Outlook
        </h3>
        {data?.issued && (
          <span className="text-[10px] text-slate-600">
            issued {data.issued.slice(0, 16).replace("T", " ")} UTC
          </span>
        )}
      </div>

      {isLoading ? (
        <div className="h-40 animate-pulse rounded bg-surface-muted" />
      ) : days.length === 0 ? (
        <p className="py-6 text-center text-xs text-slate-600">Forecast unavailable</p>
      ) : (
        <>
          {/* Three day-cards, each holding a badge, a text line and 3 probability
            rows, squeezed to ~100px on a phone. Stack them below sm. */}
        <div className="grid flex-1 grid-cols-1 gap-2 sm:grid-cols-3">
            {days.map((d, i) => (
              <div
                key={d.date ?? i}
                className="flex flex-col gap-2 rounded border border-surface-border bg-surface-muted/40 p-2"
              >
                <div className="text-center">
                  <p className="text-[11px] font-medium text-slate-300">
                    {dayName(d.date, i)}
                  </p>
                  <p className="text-[10px] text-slate-600">{d.date ?? "—"}</p>
                </div>
                <div className="flex justify-center">
                  <Badge prefix="G" scale={d.g_scale} />
                </div>
                <p className="text-center text-[10px] capitalize text-slate-500">
                  {d.g_text ?? "none"}
                </p>
                <div className="mt-auto space-y-1 border-t border-surface-border pt-1.5">
                  <Prob label="R1–R2" value={d.r_minor_prob} />
                  <Prob label="R3+" value={d.r_major_prob} />
                  <Prob label="S1+" value={d.s_prob} />
                </div>
              </div>
            ))}
          </div>

          {(data?.current || data?.observed) && (
            <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-surface-border pt-2 text-[11px] text-slate-500">
              {data?.current && (
                <span className="flex items-center gap-1.5">
                  Today so far: <Badge prefix="R" scale={data.current.r_scale} />
                  <Badge prefix="S" scale={data.current.s_scale} />
                  <Badge prefix="G" scale={data.current.g_scale} />
                </span>
              )}
              {data?.observed && (
                <span className="flex items-center gap-1.5">
                  Yesterday: <Badge prefix="R" scale={data.observed.r_scale} />
                  <Badge prefix="S" scale={data.observed.s_scale} />
                  <Badge prefix="G" scale={data.observed.g_scale} />
                </span>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

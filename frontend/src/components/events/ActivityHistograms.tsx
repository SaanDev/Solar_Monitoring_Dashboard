"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import useSWR from "swr";
import { clsx } from "clsx";
import { GitCompareArrows } from "lucide-react";

import { api } from "@/lib/api";
import { usePlotlyTheme } from "@/components/charts/plotlyTheme";
import type { ActivityHistogramResponse, ActivityHistogramSeries } from "@/lib/types";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

const DAY_MS = 86_400_000;

/** N days before today (today = offset 0), as YYYY-MM-DD (UTC). */
function daysAgo(n: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - n);
  return d.toISOString().slice(0, 10);
}

const PERIODS = [
  { label: "30 d", days: 30 },
  { label: "90 d", days: 90 },
  { label: "180 d", days: 180 },
  { label: "1 yr", days: 365 },
];

const INTERVALS = [
  { label: "Daily", days: 1 },
  { label: "3-day", days: 3 },
  { label: "Weekly", days: 7 },
  { label: "14-day", days: 14 },
];

// Severity ramp, cool (low) → hot (high). Categories are colored by their
// position so darker/redder always reads as more severe across every panel.
const RAMP = ["#60a5fa", "#facc15", "#fb923c", "#f87171", "#dc2626"];
function catColor(i: number, n: number): string {
  if (n <= 1) return "#fb923c";
  return RAMP[Math.round((i / (n - 1)) * (RAMP.length - 1))];
}

/** One parameter's stacked bar panel, sharing the caller's x-range for alignment. */
function SeriesPanel({
  series,
  binStarts,
  intervalDays,
  xRange,
  showXLabels,
}: {
  series: ActivityHistogramSeries;
  binStarts: string[];
  intervalDays: number;
  xRange: [string, string];
  showXLabels: boolean;
}) {
  const theme = usePlotlyTheme();

  // Center bars over their bin so multi-day bins sit above their span.
  const x = binStarts.map((b) =>
    new Date(new Date(b).getTime() + (intervalDays * DAY_MS) / 2).toISOString()
  );
  const barWidth = intervalDays * DAY_MS * 0.85;
  const n = series.categories.length;

  const header = (
    <div className="mb-1 flex items-baseline justify-between gap-2">
      <span className="text-[11px] font-medium text-slate-300">{series.label}</span>
      <span className="text-[10px] text-slate-600">{series.total}</span>
    </div>
  );

  if (n === 0) {
    return (
      <div>
        {header}
        <div className="flex h-[120px] items-center justify-center rounded bg-surface-muted/40 text-[10px] text-slate-600">
          No events in this period
        </div>
      </div>
    );
  }

  return (
    <div>
      {header}
      <div className="h-[130px]">
        <Plot
          data={series.categories.map((cat, ci) => ({
            x,
            y: series.counts.map((row) => row[ci]),
            type: "bar",
            name: cat,
            marker: { color: catColor(ci, n) },
            width: barWidth,
            hovertemplate: `%{y} · ${cat}<br>%{x|%Y-%m-%d}<extra></extra>`,
          }))}
          layout={
            {
              ...theme.layout,
              barmode: "stack",
              bargap: 0.05,
              xaxis: {
                ...theme.axis,
                type: "date",
                range: xRange,
                showticklabels: showXLabels,
              },
              yaxis: { ...theme.axis, rangemode: "tozero", nticks: 3, fixedrange: true },
              margin: { t: 4, r: 8, b: showXLabels ? 28 : 6, l: 30 },
              legend: {
                orientation: "h",
                y: 1.02,
                x: 1,
                xanchor: "right",
                yanchor: "bottom",
                font: { size: 9 },
              },
              showlegend: true,
            } as Plotly.Layout
          }
          config={{ displayModeBar: false, responsive: true }}
          style={{ width: "100%", height: "100%" }}
          useResizeHandler
        />
      </div>
    </div>
  );
}

/**
 * Stacked, time-aligned histograms of each space-weather parameter (solar
 * flares, radio bursts — official & model, CMEs, geomagnetic storms) so their
 * activity peaks can be visually correlated. Shares the CME-histogram period /
 * bin controls; all panels use one aligned time axis.
 */
export function ActivityHistograms() {
  const [periodDays, setPeriodDays] = useState(90);
  const [intervalDays, setIntervalDays] = useState(1);

  const start = daysAgo(periodDays);
  const end = daysAgo(0);

  const { data, isLoading, error } = useSWR<ActivityHistogramResponse>(
    ["activity-histogram", start, end, intervalDays],
    () => api.activityHistogram(start, end, intervalDays),
    { refreshInterval: 300000, keepPreviousData: true }
  );

  const binStarts = data?.bin_starts ?? [];
  const series = data?.series ?? [];

  // A single x-range shared by every panel so the bars line up vertically.
  const xRange: [string, string] | null =
    binStarts.length > 0
      ? [
          new Date(new Date(binStarts[0]).getTime() - intervalDays * DAY_MS * 0.5).toISOString(),
          new Date(
            new Date(binStarts[binStarts.length - 1]).getTime() + intervalDays * DAY_MS * 1.5
          ).toISOString(),
        ]
      : null;

  return (
    <section className="rounded-lg border border-surface-border bg-surface-card p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-1.5 text-xs uppercase tracking-wider text-slate-500">
          <GitCompareArrows className="h-3.5 w-3.5" />
          Activity Correlation
        </h2>
        <span className="text-[10px] text-slate-600">
          stacked by severity · aligned time axis
        </span>
      </div>

      {/* Shared period + bin controls. */}
      <div className="mb-4 flex flex-wrap items-center gap-3 text-[11px]">
        <div className="flex items-center gap-1">
          <span className="text-slate-600">Period</span>
          {PERIODS.map((p) => (
            <button
              key={p.days}
              type="button"
              onClick={() => setPeriodDays(p.days)}
              className={clsx(
                "rounded border px-2 py-1 transition-colors",
                periodDays === p.days
                  ? "border-accent-blue/50 bg-accent-blue/10 text-accent-blue"
                  : "border-surface-border text-slate-400 hover:text-slate-200"
              )}
            >
              {p.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1">
          <span className="text-slate-600">Bin</span>
          {INTERVALS.map((iv) => (
            <button
              key={iv.days}
              type="button"
              onClick={() => setIntervalDays(iv.days)}
              className={clsx(
                "rounded border px-2 py-1 transition-colors",
                intervalDays === iv.days
                  ? "border-accent-blue/50 bg-accent-blue/10 text-accent-blue"
                  : "border-surface-border text-slate-400 hover:text-slate-200"
              )}
            >
              {iv.label}
            </button>
          ))}
        </div>
      </div>

      {error ? (
        <div className="flex h-40 items-center justify-center text-xs text-accent-red">
          Failed to load activity histograms
        </div>
      ) : isLoading && series.length === 0 ? (
        <div className="h-64 animate-pulse rounded bg-surface-muted" />
      ) : xRange ? (
        <div className="space-y-3">
          {series.map((s, i) => (
            <SeriesPanel
              key={s.key}
              series={s}
              binStarts={binStarts}
              intervalDays={intervalDays}
              xRange={xRange}
              showXLabels={i === series.length - 1}
            />
          ))}
        </div>
      ) : (
        <div className="flex h-40 items-center justify-center text-xs text-slate-600">
          No activity in this period
        </div>
      )}

      <p className="mt-3 text-[11px] leading-relaxed text-slate-600">
        Counts per bin from GOES X-ray flares, e-CALLISTO radio bursts (official
        list &amp; the detection model), the NASA DONKI CME catalog, and Kp/Dst
        geomagnetic storms. Derived-event panels only cover the period since
        detection began. Times are UTC.
      </p>
    </section>
  );
}

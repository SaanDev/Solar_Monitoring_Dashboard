"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import useSWR from "swr";
import { BarChart3 } from "lucide-react";

import { api } from "@/lib/api";
import { Segmented } from "@/components/ui/Segmented";
import { usePlotlyTheme } from "@/components/charts/plotlyTheme";
import type { CmeHistogramBin } from "@/lib/types";

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

const EARTH_COLOR = "#f97316"; // orange-500 — Earth-directed
const OTHER_COLOR = "#64748b"; // slate-500 — not Earth-directed

/** Bar chart of CME counts per bin; Earth-directed stacked over the rest. */
function HistogramChart({
  bins,
  intervalDays,
  loading,
}: {
  bins: CmeHistogramBin[];
  intervalDays: number;
  loading?: boolean;
}) {
  const theme = usePlotlyTheme();
  if (loading) return <div className="h-full animate-pulse rounded bg-surface-muted" />;
  if (!bins.length) {
    return (
      <div className="flex h-full items-center justify-center text-xs text-slate-700">
        No data
      </div>
    );
  }

  // Center each bar over its bin so multi-day bins sit above their span.
  const x = bins.map((b) =>
    new Date(new Date(b.bin_start).getTime() + (intervalDays * DAY_MS) / 2).toISOString()
  );
  const other = bins.map((b) => b.count - b.earth_directed);
  const earth = bins.map((b) => b.earth_directed);
  const barWidth = intervalDays * DAY_MS * 0.85;
  const spanLabel = intervalDays === 1 ? "" : ` (+${intervalDays - 1}d)`;

  return (
    <Plot
      data={[
        {
          x,
          y: other,
          type: "bar",
          name: "Not Earth-directed",
          marker: { color: OTHER_COLOR },
          width: barWidth,
          hovertemplate: `%{y} CMEs<br>%{x|%Y-%m-%d}${spanLabel}<extra></extra>`,
        },
        {
          x,
          y: earth,
          type: "bar",
          name: "Earth-directed",
          marker: { color: EARTH_COLOR },
          width: barWidth,
          hovertemplate: `%{y} Earth-directed<br>%{x|%Y-%m-%d}${spanLabel}<extra></extra>`,
        },
      ]}
      layout={
        {
          ...theme.layout,
          barmode: "stack",
          bargap: 0.05,
          xaxis: {
            ...theme.axis,
            type: "date",
            title: { text: "Date (UTC)", font: { size: 10 } },
          },
          yaxis: {
            ...theme.axis,
            title: {
              text: intervalDays === 1 ? "CMEs / day" : `CMEs / ${intervalDays} days`,
              font: { size: 10 },
            },
            rangemode: "tozero",
            dtick: 1,
          },
          margin: { t: 10, r: 16, b: 40, l: 44 },
          legend: {
            orientation: "h",
            y: 1.12,
            x: 1,
            xanchor: "right",
            font: { size: 10 },
          },
        } as Plotly.Layout
      }
      config={{ displayModeBar: false, responsive: true }}
      style={{ width: "100%", height: "100%" }}
      useResizeHandler
    />
  );
}

/**
 * Histogram of CME counts over time from the NASA DONKI catalog — a research
 * overview of eruption cadence. The period (30 d … 1 yr) and bin interval
 * (daily … 14-day) are user-adjustable; old periods are fetched on demand.
 */
export function CmeHistogram() {
  const [periodDays, setPeriodDays] = useState(90);
  const [intervalDays, setIntervalDays] = useState(1);

  const start = daysAgo(periodDays);
  const end = daysAgo(0);

  const { data, isLoading, error } = useSWR(
    ["forecast-cmes-histogram", start, end, intervalDays],
    () => api.forecastCmesHistogram(start, end, intervalDays),
    { refreshInterval: 300000, keepPreviousData: true }
  );

  const bins = data?.bins ?? [];
  const total = bins.reduce((s, b) => s + b.count, 0);
  const earthTotal = bins.reduce((s, b) => s + b.earth_directed, 0);

  return (
    <div className="flex h-full flex-col rounded-lg border border-surface-border bg-surface-card p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h3 className="flex items-center gap-1.5 text-xs uppercase tracking-wider text-slate-500">
          <BarChart3 className="h-3.5 w-3.5" />
          CME Frequency
        </h3>
        {!isLoading && total > 0 && (
          <span className="text-[10px] text-slate-600">
            {total} CMEs · {earthTotal} Earth-directed
          </span>
        )}
      </div>

      {/* Controls: period + bin interval. Rendered through the shared Segmented
          control so the Forecast page's four range pickers stop each looking
          different. State stays per-picker — only the appearance is unified. */}
      <div className="mb-3 flex flex-wrap items-center gap-3 text-[11px]">
        <div className="flex items-center gap-1">
          <span className="text-slate-600">Period</span>
          <Segmented
            ariaLabel="Period"
            value={String(periodDays)}
            onChange={(v) => setPeriodDays(Number(v))}
            options={PERIODS.map((p) => ({ value: String(p.days), label: p.label }))}
          />
        </div>
        <div className="flex items-center gap-1">
          <span className="text-slate-600">Bin</span>
          <Segmented
            ariaLabel="Bin interval"
            value={String(intervalDays)}
            onChange={(v) => setIntervalDays(Number(v))}
            options={INTERVALS.map((iv) => ({ value: String(iv.days), label: iv.label }))}
          />
        </div>
      </div>

      <div className="h-64">
        {error ? (
          <div className="flex h-full items-center justify-center text-xs text-red-400">
            Could not load CME histogram for this period
          </div>
        ) : (
          <HistogramChart bins={bins} intervalDays={intervalDays} loading={isLoading} />
        )}
      </div>
    </div>
  );
}

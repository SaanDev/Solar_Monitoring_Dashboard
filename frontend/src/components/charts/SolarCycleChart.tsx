"use client";

import dynamic from "next/dynamic";
import type { SolarCycleObservedPoint, SolarCyclePredictedPoint } from "@/lib/types";
import { usePlotlyTheme } from "./plotlyTheme";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

interface Props {
  observed: SolarCycleObservedPoint[];
  predicted: SolarCyclePredictedPoint[];
  metric: "ssn" | "f107";
  loading?: boolean;
}

const LABEL = {
  ssn: "Sunspot Number",
  f107: "F10.7 (sfu)",
};

/**
 * Monthly observed values + 13-month smoothed line against the official
 * NOAA/NASA Cycle 25 prediction with its uncertainty band.
 */
export function SolarCycleChart({ observed, predicted, metric, loading }: Props) {
  const theme = usePlotlyTheme();
  // Keep the previous series on screen while a new range loads (paired with
  // keepPreviousData at the call site). Without data this is still just
  // `if (loading)`, so the first load is unchanged.
  if (loading && !observed.length && !predicted.length) {
    return <div className="h-full animate-pulse rounded bg-surface-muted" />;
  }
  if (!observed.length && !predicted.length) {
    return (
      <div className="flex h-full items-center justify-center text-xs text-slate-700">
        No data
      </div>
    );
  }

  const month = (m: string) => `${m}-01`;
  const obsX = observed.map((p) => month(p.month));
  const smoothKey = metric === "ssn" ? "smoothed_ssn" : "smoothed_f107";
  const predX = predicted.map((p) => month(p.month));
  const hi = predicted.map((p) => p[`${metric}_high` as const]);
  const lo = predicted.map((p) => p[`${metric}_low` as const]);

  return (
    <Plot
      data={[
        // Uncertainty band: high bound then low bound filled back.
        {
          x: [...predX, ...[...predX].reverse()],
          y: [...hi, ...[...lo].reverse()],
          type: "scatter",
          mode: "lines",
          name: "Prediction range",
          line: { width: 0 },
          fill: "toself",
          fillcolor: "rgba(168,85,247,0.15)",
          hoverinfo: "skip",
        },
        {
          x: obsX,
          y: observed.map((p) => p[metric]),
          type: "scatter",
          mode: "lines",
          name: "Monthly observed",
          line: { color: theme.dark ? "#475569" : "#94a3b8", width: 1 },
        },
        {
          x: obsX,
          y: observed.map((p) => p[smoothKey]),
          type: "scatter",
          mode: "lines",
          name: "13-month smoothed",
          line: { color: "#f59e0b", width: 2 },
          connectgaps: false,
        },
        {
          x: predX,
          y: predicted.map((p) => p[metric]),
          type: "scatter",
          mode: "lines",
          name: "Cycle 25 prediction",
          line: { color: "#a855f7", width: 2, dash: "dash" },
        },
      ]}
      layout={
        {
          ...theme.layout,
          xaxis: { ...theme.axis, hoverformat: "%Y-%m" },
          yaxis: {
            ...theme.axis,
            title: { text: LABEL[metric], font: { size: 10 } },
            rangemode: "tozero",
          },
          legend: { orientation: "h", y: 1.12, font: { size: 10 } },
          margin: { t: 10, r: 20, b: 40, l: 55 },
        } as Plotly.Layout
      }
      config={{ displayModeBar: false, responsive: true }}
      style={{ width: "100%", height: "100%" }}
      useResizeHandler
    />
  );
}

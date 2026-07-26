"use client";

import dynamic from "next/dynamic";
import type { F107Point } from "@/lib/types";
import { toPlotlyUtc } from "@/lib/formatting";
import { usePlotlyTheme } from "./plotlyTheme";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

interface Props {
  data: F107Point[];
  loading?: boolean;
}

export function RadioFluxChart({ data, loading }: Props) {
  const theme = usePlotlyTheme();
  // Keep the previous series on screen while a new range loads (paired with
  // keepPreviousData at the call site). Without data this is still just
  // `if (loading)`, so the first load is unchanged.
  if (loading && !data.length) {
    return <div className="h-full animate-pulse rounded bg-surface-muted" />;
  }
  if (!data.length) {
    return (
      <div className="flex h-full items-center justify-center text-xs text-slate-700">
        No data
      </div>
    );
  }

  return (
    <Plot
      data={[
        {
          x: data.map((d) => toPlotlyUtc(d.time)),
          y: data.map((d) => d.flux),
          type: "scatter",
          mode: "lines+markers",
          name: "F10.7",
          line: { color: "#f59e0b", width: 1.5 },
          marker: { size: 4, color: "#f59e0b" },
          fill: "tozeroy",
          fillcolor: "rgba(245,158,11,0.08)",
        },
      ]}
      layout={
        {
          ...theme.layout,
          xaxis: {
            ...theme.axis,
            title: { text: "Date (UTC)", font: { size: 10 } },
            hoverformat: "%Y-%m-%d",
          },
          yaxis: {
            ...theme.axis,
            title: { text: "F10.7 (sfu)", font: { size: 10 } },
            rangemode: "tozero" as const,
          },
          margin: { t: 20, r: 20, b: 40, l: 55 },
        } as Plotly.Layout
      }
      config={{ displayModeBar: false, responsive: true }}
      style={{ width: "100%", height: "100%" }}
      useResizeHandler
    />
  );
}

"use client";

import dynamic from "next/dynamic";
import type { SolarWindPoint } from "@/lib/types";
import { toPlotlyUtc } from "@/lib/formatting";
import { usePlotlyTheme } from "./plotlyTheme";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

interface Props {
  data: SolarWindPoint[];
  loading?: boolean;
}

export function SolarWindSpeedChart({ data, loading }: Props) {
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
          y: data.map((d) => d.speed),
          type: "scatter",
          mode: "lines",
          name: "Speed",
          line: { color: "#f59e0b", width: 1.5 },
        },
      ]}
      layout={
        {
          ...theme.layout,
          xaxis: {
            ...theme.axis,
            title: { text: "Time (UTC)", font: { size: 10 } },
            hoverformat: "%Y-%m-%d %H:%M UTC",
          },
          yaxis: {
            ...theme.axis,
            title: { text: "Speed (km/s)", font: { size: 10 } },
          },
          margin: { t: 20, r: 20, b: 40, l: 60 },
          showlegend: false,
        } as Plotly.Layout
      }
      config={{ displayModeBar: false, responsive: true }}
      style={{ width: "100%", height: "100%" }}
      useResizeHandler
    />
  );
}

"use client";

import dynamic from "next/dynamic";
import type { SunspotSeriesPoint } from "@/lib/types";
import { usePlotlyTheme } from "./plotlyTheme";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

interface Props {
  data: SunspotSeriesPoint[];
  scope: "cycle" | "recent";
  loading?: boolean;
}

export function SunspotChart({ data, scope, loading }: Props) {
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

  const dates = data.map((d) => d.date);
  const observed: Partial<Plotly.PlotData> = {
    x: dates,
    y: data.map((d) => d.number),
    type: "scatter",
    mode: "lines",
    name: scope === "cycle" ? "Monthly SSN" : "Daily SSN",
    line: { color: scope === "cycle" ? "#64748b" : "#06b6d4", width: 1.25 },
  };

  const traces: Partial<Plotly.PlotData>[] = [observed];
  if (scope === "cycle" && data.some((d) => d.smoothed != null)) {
    traces.push({
      x: dates,
      y: data.map((d) => d.smoothed),
      type: "scatter",
      mode: "lines",
      name: "13-month smoothed",
      line: { color: "#f97316", width: 2 },
      connectgaps: false,
    });
  }

  return (
    <Plot
      data={traces}
      layout={
        {
          ...theme.layout,
          xaxis: {
            ...theme.axis,
            title: { text: "Date (UTC)", font: { size: 10 } },
            hoverformat: scope === "cycle" ? "%Y-%m" : "%Y-%m-%d",
          },
          yaxis: {
            ...theme.axis,
            title: { text: "Sunspot number", font: { size: 10 } },
            rangemode: "tozero" as const,
          },
          margin: { t: 20, r: 20, b: 40, l: 55 },
          legend: { x: 0, y: 1, bgcolor: "transparent", font: { size: 10 } },
        } as Plotly.Layout
      }
      config={{ displayModeBar: false, responsive: true }}
      style={{ width: "100%", height: "100%" }}
      useResizeHandler
    />
  );
}

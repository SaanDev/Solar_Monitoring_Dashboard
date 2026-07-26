"use client";

import dynamic from "next/dynamic";
import type { GoesMagnetometerPoint } from "@/lib/types";
import { toPlotlyUtc } from "@/lib/formatting";
import { usePlotlyTheme } from "./plotlyTheme";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

interface Props {
  data: GoesMagnetometerPoint[];
  loading?: boolean;
}

export function MagnetometerChart({ data, loading }: Props) {
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

  const times = data.map((d) => toPlotlyUtc(d.time));
  const trace = (
    key: "hp" | "he" | "hn" | "total",
    name: string,
    color: string
  ): Partial<Plotly.PlotData> => ({
    x: times,
    y: data.map((d) => d[key]),
    type: "scatter",
    mode: "lines",
    name,
    line: { color, width: 1.5 },
  });

  return (
    <Plot
      data={[
        trace("hp", "Hp (north)", "#3b82f6"),
        trace("he", "He (earth)", "#06b6d4"),
        trace("hn", "Hn (east)", "#a855f7"),
        // Near-white reads on the dark plot only; flip to dark slate on light.
        trace("total", "Total", theme.dark ? "#e2e8f0" : "#334155"),
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
            title: { text: "Field (nT)", font: { size: 10 } },
          },
          margin: { t: 20, r: 20, b: 40, l: 60 },
          legend: { x: 0, y: 1, bgcolor: "transparent", font: { size: 10 } },
        } as Plotly.Layout
      }
      config={{ displayModeBar: false, responsive: true }}
      style={{ width: "100%", height: "100%" }}
      useResizeHandler
    />
  );
}

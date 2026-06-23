"use client";

import dynamic from "next/dynamic";
import type { GoesMagnetometerPoint } from "@/lib/types";
import { toPlotlyUtc } from "@/lib/formatting";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

interface Props {
  data: GoesMagnetometerPoint[];
  loading?: boolean;
}

export function MagnetometerChart({ data, loading }: Props) {
  if (loading) return <div className="h-full animate-pulse rounded bg-surface-muted" />;
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
        trace("total", "Total", "#e2e8f0"),
      ]}
      layout={
        {
          paper_bgcolor: "transparent",
          plot_bgcolor: "#0a0d14",
          font: { color: "#94a3b8", size: 11 },
          xaxis: {
            color: "#475569",
            gridcolor: "#1e2535",
            title: { text: "Time (UTC)", font: { size: 10 } },
            hoverformat: "%Y-%m-%d %H:%M UTC",
          },
          yaxis: {
            color: "#475569",
            gridcolor: "#1e2535",
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

"use client";

import dynamic from "next/dynamic";
import type { GoesProtonPoint } from "@/lib/types";
import { toPlotlyUtc } from "@/lib/formatting";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

interface Props {
  data: GoesProtonPoint[];
  loading?: boolean;
}

export function ProtonFluxChart({ data, loading }: Props) {
  if (loading) return <div className="h-full animate-pulse rounded bg-surface-muted" />;
  if (!data.length) {
    return (
      <div className="flex h-full items-center justify-center text-xs text-slate-700">No data</div>
    );
  }

  const times = data.map((d) => toPlotlyUtc(d.time));

  return (
    <Plot
      data={[
        { x: times, y: data.map((d) => d.flux_gt10), type: "scatter", mode: "lines", name: ">10 MeV", line: { color: "#f97316", width: 1.5 } },
        { x: times, y: data.map((d) => d.flux_gt50), type: "scatter", mode: "lines", name: ">50 MeV", line: { color: "#a855f7", width: 1.5 } },
        { x: times, y: data.map((d) => d.flux_gt100), type: "scatter", mode: "lines", name: ">100 MeV", line: { color: "#ef4444", width: 1.5 } },
      ]}
      layout={{
        paper_bgcolor: "transparent",
        plot_bgcolor: "#0a0d14",
        font: { color: "#94a3b8", size: 11 },
        xaxis: { color: "#475569", gridcolor: "#1e2535", title: { text: "Time (UTC)", font: { size: 10 } }, hoverformat: "%Y-%m-%d %H:%M UTC" },
        yaxis: { type: "log", color: "#475569", gridcolor: "#1e2535", range: [-2, 4], dtick: 1, title: { text: "Particles / (cm² s sr)", font: { size: 10 } } },
        margin: { t: 20, r: 20, b: 40, l: 70 },
        legend: { x: 0, y: 1, bgcolor: "transparent", font: { size: 10 } },
        shapes: [{ type: "line", xref: "paper", yref: "y", x0: 0, x1: 1, y0: 10, y1: 10, line: { color: "#ef4444", dash: "dot", width: 1 } }],
      } as Plotly.Layout}
      config={{ displayModeBar: false, responsive: true }}
      style={{ width: "100%", height: "100%" }}
      useResizeHandler
    />
  );
}
